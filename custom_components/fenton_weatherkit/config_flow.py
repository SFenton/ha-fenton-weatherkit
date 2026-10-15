"""Config flow: paste the WeatherKit key and IDs; they are checked with Apple before they are saved."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import WeatherKitClient, WeatherKitError
from .const import (
    CONF_AIR_QUALITY,
    CONF_FORECAST_INTERVAL,
    CONF_HOURLY_HOURS,
    CONF_INTERVAL,
    CONF_KEY_ID,
    CONF_KEY_PEM,
    CONF_MONTHLY_BUDGET,
    CONF_SERVICE_ID,
    CONF_TEAM_ID,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_HOURLY_HOURS,
    DEFAULT_INTERVAL,
    DEFAULT_MONTHLY_BUDGET,
    DOMAIN,
    MAX_HOURLY_HOURS,
    MIN_INTERVAL,
)

KEY_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))
TEXT = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
CREDENTIALS = (CONF_KEY_ID, CONF_TEAM_ID, CONF_SERVICE_ID, CONF_KEY_PEM)


def _number(minimum: float, maximum: float, step: float | str = 1, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _credentials_schema(defaults: Mapping[str, Any]) -> dict:
    return {
        vol.Required(CONF_KEY_ID, default=defaults.get(CONF_KEY_ID, "")): TEXT,
        vol.Required(CONF_TEAM_ID, default=defaults.get(CONF_TEAM_ID, "")): TEXT,
        vol.Required(CONF_SERVICE_ID, default=defaults.get(CONF_SERVICE_ID, "")): TEXT,
        vol.Required(CONF_KEY_PEM): KEY_SELECTOR,
    }


class FentonWeatherKitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one location with the owner's WeatherKit key."""

    VERSION = 1

    async def _verify(self, data: Mapping[str, Any], latitude: float, longitude: float) -> str | None:
        """Return an error key, or None when Apple accepts the key at this location."""
        try:
            client = WeatherKitClient(async_get_clientsession(self.hass), data[CONF_KEY_ID], data[CONF_TEAM_ID],
                                      data[CONF_SERVICE_ID], data[CONF_KEY_PEM])
            available = await client.availability(latitude, longitude, self.hass.config.country)
        except WeatherKitError as err:
            return err.code if err.code in ("invalid_key", "invalid_auth", "over_quota") else "cannot_connect"
        return None if available else "no_data"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            latitude, longitude = float(user_input[CONF_LATITUDE]), float(user_input[CONF_LONGITUDE])
            await self.async_set_unique_id(f"{latitude:.3f},{longitude:.3f}")
            self._abort_if_unique_id_configured()
            credentials = {key: str(user_input[key]).strip() for key in CREDENTIALS}
            error = await self._verify(credentials, latitude, longitude)
            if error is None:
                return self.async_create_entry(
                    title="Apple Weather",
                    data={**credentials, CONF_LATITUDE: latitude, CONF_LONGITUDE: longitude},
                )
            errors["base"] = error
        schema = vol.Schema({
            **_credentials_schema(user_input or {}),
            vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): _number(-90, 90, "any"),
            vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): _number(-180, 180, "any"),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Apple rejected the saved key (revoked, or WeatherKit unticked)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {key: str(user_input[key]).strip() for key in CREDENTIALS}
            error = await self._verify(credentials, entry.data[CONF_LATITUDE], entry.data[CONF_LONGITUDE])
            if error is None:
                return self.async_update_reload_and_abort(entry, data_updates=credentials)
            errors["base"] = error
        return self.async_show_form(step_id="reauth_confirm",
                                    data_schema=vol.Schema(_credentials_schema(user_input or entry.data)),
                                    errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FentonWeatherKitOptionsFlow()


class FentonWeatherKitOptionsFlow(OptionsFlow):
    """Polling interval, forecast length, call budget and the AQI source."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={
                CONF_INTERVAL: int(user_input[CONF_INTERVAL]),
                CONF_FORECAST_INTERVAL: int(user_input[CONF_FORECAST_INTERVAL]),
                CONF_HOURLY_HOURS: int(user_input[CONF_HOURLY_HOURS]),
                CONF_MONTHLY_BUDGET: int(user_input[CONF_MONTHLY_BUDGET]),
                CONF_AIR_QUALITY: bool(user_input[CONF_AIR_QUALITY]),
            })
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required(CONF_INTERVAL, default=options.get(CONF_INTERVAL, DEFAULT_INTERVAL)):
                _number(MIN_INTERVAL, 3600, 1, "s"),
            vol.Required(CONF_FORECAST_INTERVAL, default=options.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)):
                _number(1, 60, 1, "min"),
            vol.Required(CONF_HOURLY_HOURS, default=options.get(CONF_HOURLY_HOURS, DEFAULT_HOURLY_HOURS)):
                _number(24, MAX_HOURLY_HOURS, 1, "h"),
            vol.Required(CONF_MONTHLY_BUDGET, default=options.get(CONF_MONTHLY_BUDGET, DEFAULT_MONTHLY_BUDGET)):
                _number(1000, 10_000_000, 1000, "calls"),
            vol.Required(CONF_AIR_QUALITY, default=options.get(CONF_AIR_QUALITY, True)): BooleanSelector(),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
