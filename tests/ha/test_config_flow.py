"""Config, reauth and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fenton_weatherkit.api import WeatherKitError
from custom_components.fenton_weatherkit.const import (
    CONF_AIR_QUALITY,
    CONF_FORECAST_INTERVAL,
    CONF_HOURLY_HOURS,
    CONF_INTERVAL,
    CONF_KEY_ID,
    CONF_KEY_PEM,
    CONF_MONTHLY_BUDGET,
    CONF_SERVICE_ID,
    CONF_TEAM_ID,
    DOMAIN,
)

from .conftest import AVAILABLE, CLIENT

SETUP = "custom_components.fenton_weatherkit.async_setup_entry"


def form(pem: str, **overrides) -> dict:
    return {CONF_KEY_ID: " ABC123DEFG ", CONF_TEAM_ID: "DEF123GHIJ", CONF_SERVICE_ID: "com.sfenton.home.weatherkit",
            CONF_KEY_PEM: pem, CONF_LATITUDE: 47.61, CONF_LONGITUDE: -122.33, **overrides}


async def test_flow_checks_the_key_with_apple(hass: HomeAssistant, pem) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form("nope"))
    assert result["errors"] == {"base": "invalid_key"}
    with patch(f"{CLIENT}.availability", AsyncMock(side_effect=WeatherKitError("invalid_auth", 401))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form(pem))
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(f"{CLIENT}.availability", AsyncMock(return_value=AVAILABLE)), patch(SETUP, AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form(pem))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Apple Weather"
    assert result["data"][CONF_KEY_ID] == "ABC123DEFG"
    assert result["result"].unique_id == "47.610,-122.330"


async def test_reauth_replaces_the_key(hass: HomeAssistant, entry, pem) -> None:
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    new = {CONF_KEY_ID: "NEWKEY1234", CONF_TEAM_ID: "DEF123GHIJ", CONF_SERVICE_ID: "com.sfenton.home.weatherkit",
           CONF_KEY_PEM: pem}
    with patch(f"{CLIENT}.availability", AsyncMock(return_value=AVAILABLE)), patch(SETUP, AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], new)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data[CONF_KEY_ID] == "NEWKEY1234"


async def test_options(hass: HomeAssistant, entry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(SETUP, AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_configure(result["flow_id"], {
            CONF_INTERVAL: 30, CONF_FORECAST_INTERVAL: 10, CONF_HOURLY_HOURS: 72, CONF_MONTHLY_BUDGET: 450_000,
            CONF_AIR_QUALITY: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_INTERVAL: 30, CONF_FORECAST_INTERVAL: 10, CONF_HOURLY_HOURS: 72,
                             CONF_MONTHLY_BUDGET: 450_000, CONF_AIR_QUALITY: False}
