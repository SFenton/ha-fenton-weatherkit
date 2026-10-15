"""Fenton WeatherKit: Apple WeatherKit (REST) for the Fenton Home web and native apps.

Replaces Pirate Weather. Home Assistant is the only caller: the key stays in the config entry, the apps
read ``weather.apple_weather`` and its sensors over their existing Home Assistant connection.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import WeatherKitClient, WeatherKitError
from .budget import CallBudget
from .const import (
    CONF_AIR_QUALITY,
    CONF_KEY_ID,
    CONF_KEY_PEM,
    CONF_MONTHLY_BUDGET,
    CONF_SERVICE_ID,
    CONF_TEAM_ID,
    DEFAULT_MONTHLY_BUDGET,
    DOMAIN,
)
from .coordinator import STORAGE_VERSION, AirQualityCoordinator, WeatherKitCoordinator, option

PLATFORMS = [Platform.SENSOR, Platform.WEATHER]


@dataclass
class FentonWeatherKitRuntime:
    weather: WeatherKitCoordinator
    air_quality: AirQualityCoordinator | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start polling for this location."""
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    stored = await store.async_load() or {}
    budget = CallBudget(int(option(entry, CONF_MONTHLY_BUDGET, DEFAULT_MONTHLY_BUDGET)), stored.get("budget"))
    coordinator: WeatherKitCoordinator | None = None
    try:
        client = WeatherKitClient(
            async_get_clientsession(hass), entry.data[CONF_KEY_ID], entry.data[CONF_TEAM_ID],
            entry.data[CONF_SERVICE_ID], entry.data[CONF_KEY_PEM], on_call=lambda: coordinator.record_call())
    except WeatherKitError as err:
        raise ConfigEntryAuthFailed(err.code) from err
    coordinator = WeatherKitCoordinator(hass, entry, client, store, budget, stored.get("seen_alerts") or [])
    await coordinator.async_config_entry_first_refresh()

    air_quality = None
    if option(entry, CONF_AIR_QUALITY, True):
        air_quality = AirQualityCoordinator(hass, entry, float(entry.data.get(CONF_LATITUDE, hass.config.latitude)),
                                            float(entry.data.get(CONF_LONGITUDE, hass.config.longitude)))
        # AQI is a side source: its outage must not keep the weather from loading.
        await air_quality.async_refresh()

    entry.runtime_data = FentonWeatherKitRuntime(weather=coordinator, air_quality=air_quality)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop polling; save the call count now rather than after the save delay."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data.weather
        await coordinator.store.async_save(coordinator.storage_payload())
    return unloaded
