"""Polls WeatherKit once a minute in a single call per update.

Every update asks for current conditions, the next-hour forecast and alerts. The hourly and daily forecasts
ride along in the same call every ``forecast_interval`` minutes or once Apple's expiry time for them passes,
so they cost no extra calls and the minute-by-minute payload stays small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import mapping
from .air_quality import fetch_air_quality
from .api import WeatherKitClient, WeatherKitError
from .budget import CallBudget
from .const import (
    AIR_QUALITY_INTERVAL,
    CONF_FORECAST_INTERVAL,
    CONF_HOURLY_HOURS,
    CONF_INTERVAL,
    DATA_ALERTS,
    DATA_CURRENT,
    DATA_DAILY,
    DATA_HOURLY,
    DATA_NEXT_HOUR,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_HOURLY_HOURS,
    DEFAULT_INTERVAL,
    DOMAIN,
    EVENT_ALERT,
    FAST_DATA_SETS,
    FORECAST_DAYS,
    LOGGER,
    MAX_ALERT_DETAILS_PER_UPDATE,
    MAX_BACKOFF,
    METADATA_REFRESH,
    SLOW_DATA_SETS,
    STALE_AFTER,
)

STORAGE_VERSION = 1
SEEN_ALERTS_KEPT = 50


@dataclass
class WeatherKitData:
    """What the entities show, derived from the latest responses."""

    current: dict[str, Any]
    hourly: list[dict[str, Any]]
    daily: list[dict[str, Any]]
    twice_daily: list[dict[str, Any]]
    next_hour: dict[str, Any]
    alerts: list[dict[str, Any]]
    pressure_trend: str | None
    precipitation_intensity: float | None
    moon_phase: str | None
    read_time: str | None
    data_sets: list[str] = field(default_factory=list)


def option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


class WeatherKitCoordinator(DataUpdateCoordinator[WeatherKitData]):
    """One location's WeatherKit data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: WeatherKitClient,
                 store: Store, budget: CallBudget, seen_alerts: list[str]) -> None:
        self.client = client
        self.store = store
        self.budget = budget
        self.interval = float(option(entry, CONF_INTERVAL, DEFAULT_INTERVAL))
        self.forecast_interval = timedelta(minutes=float(option(entry, CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)))
        self.hourly_hours = int(option(entry, CONF_HOURLY_HOURS, DEFAULT_HOURLY_HOURS))
        self.latitude = float(entry.data.get(CONF_LATITUDE, hass.config.latitude))
        self.longitude = float(entry.data.get(CONF_LONGITUDE, hass.config.longitude))
        self.language = (hass.config.language or "en").split("-")[0]
        self.country = hass.config.country
        self.available: list[str] | None = None
        self.attribution: dict[str, str] = {}
        self._metadata_at: datetime | None = None
        self._raw: dict[str, Any] = {}
        self._forecast_at: datetime | None = None
        self._last_success: datetime | None = None
        self._failures = 0
        self._alert_details: dict[str, dict[str, Any]] = {}
        self._seen_alerts = list(seen_alerts)
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=self.interval))

    def storage_payload(self) -> dict[str, Any]:
        """The call count and the alerts already announced, kept across restarts."""
        return {"budget": self.budget.as_dict(), "seen_alerts": self._seen_alerts[-SEEN_ALERTS_KEPT:]}

    def _save(self) -> None:
        self.store.async_delay_save(self.storage_payload, 60)

    def record_call(self) -> None:
        """Count one call (the client calls this before every signed request)."""
        self.budget.record(dt_util.utcnow())
        self._save()

    async def _refresh_metadata(self, now: datetime) -> None:
        """Which data sets the location has, and Apple's attribution logos; once a day."""
        if self._metadata_at is not None and now - self._metadata_at < METADATA_REFRESH:
            return
        self.available = await self.client.availability(self.latitude, self.longitude, self.country)
        try:
            self.attribution = await self.client.attribution(self.language)
        except WeatherKitError as err:
            LOGGER.debug("Attribution unavailable: %s", err)
        self._metadata_at = now
        LOGGER.debug("Data sets at this location: %s", self.available)

    def _forecast_due(self, now: datetime) -> bool:
        if self._forecast_at is None or not self._raw.get(DATA_HOURLY):
            return True
        expiries = [e for key in SLOW_DATA_SETS if (e := mapping.expire_time(self._raw.get(key))) is not None]
        due = self._forecast_at + self.forecast_interval
        return now >= min([due, *expiries])

    async def _fetch_alert_details(self, data: dict[str, Any] | None) -> None:
        """Fetch each new alert's full text once (one call each)."""
        fetched = 0
        for alert in (data or {}).get("alerts") or []:
            alert_id = str(alert.get("id") or "")
            if not alert_id or alert_id in self._alert_details or fetched >= MAX_ALERT_DETAILS_PER_UPDATE:
                continue
            fetched += 1
            try:
                self._alert_details[alert_id] = await self.client.alert(self.language, alert_id)
            except WeatherKitError as err:
                LOGGER.debug("Alert %s text unavailable: %s", alert_id, err)

    def _announce_new_alerts(self, alerts: list[dict[str, Any]]) -> None:
        for alert in alerts:
            if alert["id"] in self._seen_alerts:
                continue
            self._seen_alerts.append(alert["id"])
            self.hass.bus.async_fire(EVENT_ALERT, {"entry_id": self.config_entry.entry_id, **alert})
            self._save()
        current_ids = {a["id"] for a in alerts}
        self._alert_details = {k: v for k, v in self._alert_details.items() if k in current_ids}

    def _derive(self, now: datetime) -> WeatherKitData:
        raw_current = (self._raw.get(DATA_CURRENT) or {})
        hours = (self._raw.get(DATA_HOURLY) or {}).get("hours") or []
        days = (self._raw.get(DATA_DAILY) or {}).get("days") or []
        alerts = mapping.alerts(self._raw.get(DATA_ALERTS), now, self._alert_details)
        self._announce_new_alerts(alerts)
        intensity = raw_current.get("precipitationIntensity")
        return WeatherKitData(
            current=mapping.current(raw_current),
            hourly=mapping.hourly(hours, now, self.hourly_hours),
            daily=mapping.daily(days, hours, now),
            twice_daily=mapping.twice_daily(days, now),
            next_hour=mapping.next_hour(self._raw.get(DATA_NEXT_HOUR), now),
            alerts=alerts,
            pressure_trend=raw_current.get("pressureTrend"),
            precipitation_intensity=intensity if isinstance(intensity, (int, float)) else None,
            moon_phase=mapping.moon_phase(days),
            read_time=((raw_current.get("metadata") or {}).get("readTime")),
            data_sets=[key for key in (*FAST_DATA_SETS, *SLOW_DATA_SETS) if key in self._raw],
        )

    async def _async_update_data(self) -> WeatherKitData:
        now = dt_util.utcnow()
        try:
            await self._refresh_metadata(now)
            wanted = list(FAST_DATA_SETS)
            forecast = self._forecast_due(now)
            if forecast:
                wanted += SLOW_DATA_SETS
            data_sets = [d for d in wanted if self.available is None or d in self.available]
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            response = await self.client.weather(
                self.language, self.latitude, self.longitude, data_sets,
                str(self.hass.config.time_zone), self.country,
                hourly_start=hour_start if forecast else None,
                hourly_end=hour_start + timedelta(days=FORECAST_DAYS) if forecast else None,
            )
            for key in data_sets:
                # A data set Apple leaves out (alerts when there are none) means "nothing", not "unchanged".
                self._raw[key] = response.get(key)
            if forecast:
                self._forecast_at = now
            if DATA_ALERTS in data_sets:
                await self._fetch_alert_details(response.get(DATA_ALERTS))
        except WeatherKitError as err:
            if err.code == "invalid_auth":
                raise ConfigEntryAuthFailed(str(err)) from err
            self._failures += 1
            backoff = min(self.interval * 2 ** self._failures, MAX_BACKOFF.total_seconds())
            self.update_interval = timedelta(seconds=max(backoff, self.budget.interval(self.interval, now)))
            if self.data is None or self._last_success is None or now - self._last_success > STALE_AFTER:
                raise UpdateFailed(str(err)) from err
            LOGGER.debug("Keeping the last data after a failed update: %s", err)
            return self._derive(now)
        self._failures = 0
        self._last_success = now
        self.update_interval = timedelta(seconds=self.budget.interval(self.interval, now))
        return self._derive(now)


class AirQualityCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Open-Meteo US AQI every 15 minutes."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude
        super().__init__(hass, LOGGER, config_entry=entry, name=f"{DOMAIN}_air_quality",
                         update_interval=AIR_QUALITY_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await fetch_air_quality(async_get_clientsession(self.hass), self.latitude, self.longitude)
        except WeatherKitError as err:
            raise UpdateFailed(str(err)) from err
