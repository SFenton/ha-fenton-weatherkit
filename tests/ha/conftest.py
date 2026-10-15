"""Home Assistant fixtures (pytest-homeassistant-custom-component) with Apple and Open-Meteo patched out."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fenton_weatherkit.const import (
    CONF_KEY_ID,
    CONF_KEY_PEM,
    CONF_SERVICE_ID,
    CONF_TEAM_ID,
    DOMAIN,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CLIENT = "custom_components.fenton_weatherkit.api.WeatherKitClient"
NOW = "2026-10-15T18:03:04+00:00"
AVAILABLE = ["currentWeather", "forecastDaily", "forecastHourly", "forecastNextHour", "weatherAlerts"]
AIR = {"time": "2026-10-15T18:00", "us_aqi": 42.4, "pm2_5": 6.1, "pm10": 9.0, "ozone": 51.0,
       "nitrogen_dioxide": 8.2, "carbon_monoxide": 160.0}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/fenton_weatherkit in every test."""
    yield


@pytest.fixture
def pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture
def response() -> dict:
    return json.loads((FIXTURES / "weather.json").read_text())


@pytest.fixture
def alert_detail() -> dict:
    return json.loads((FIXTURES / "alert.json").read_text())


@pytest.fixture
def entry(hass, pem) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Apple Weather", unique_id="47.610,-122.330", data={
        CONF_KEY_ID: "ABC123DEFG", CONF_TEAM_ID: "DEF123GHIJ", CONF_SERVICE_ID: "com.sfenton.home.weatherkit",
        CONF_KEY_PEM: pem, CONF_LATITUDE: 47.61, CONF_LONGITUDE: -122.33})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def apple(response, alert_detail):
    """The patched WeatherKit client; ``weather`` returns only the requested data sets, as Apple does.

    Yields the calls made, by method, as lists of their arguments.
    """
    calls: dict[str, list] = {"weather": [], "availability": [], "alert": [], "attribution": []}
    state = {"error": None}

    async def weather(self, language, latitude, longitude, data_sets, *args, **kwargs):
        calls["weather"].append((list(data_sets), kwargs))
        if self._on_call:
            self._on_call()
        if state["error"] is not None:
            raise state["error"]
        return {key: response[key] for key in data_sets if key in response}

    async def availability(self, *args):
        calls["availability"].append(args)
        if self._on_call:
            self._on_call()
        return AVAILABLE

    async def alert(self, language, alert_id):
        calls["alert"].append(alert_id)
        if self._on_call:
            self._on_call()
        return alert_detail

    async def attribution(self, language):
        calls["attribution"].append(language)
        return {"logoLight@3x": "https://weatherkit.apple.com/assets/l.png",
                "logoDark@3x": "https://weatherkit.apple.com/assets/d.png"}

    with patch(f"{CLIENT}.weather", weather), patch(f"{CLIENT}.availability", availability), \
         patch(f"{CLIENT}.alert", alert), patch(f"{CLIENT}.attribution", attribution), \
         patch("custom_components.fenton_weatherkit.coordinator.fetch_air_quality", AsyncMock(return_value=AIR)):
        yield calls, state
