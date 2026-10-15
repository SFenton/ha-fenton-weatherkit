"""Setup, entities and forecasts inside a real Home Assistant, with Apple patched out."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN, SERVICE_GET_FORECASTS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.fenton_weatherkit.api import WeatherKitError
from custom_components.fenton_weatherkit.const import EVENT_ALERT

from .conftest import NOW

WEATHER = "weather.apple_weather"


@pytest.fixture
async def loaded(hass: HomeAssistant, entry, apple, freezer):
    freezer.move_to(NOW)
    await hass.config.async_update(country="US", time_zone="America/Los_Angeles")
    events = async_capture_events(hass, EVENT_ALERT)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry, apple[0], apple[1], events


async def test_entities(hass: HomeAssistant, loaded) -> None:
    _, calls, _, events = loaded
    weather = hass.states.get(WEATHER)
    assert weather.state == "sunny"
    assert weather.attributes["temperature"] == 14.2
    assert weather.attributes["apparent_temperature"] == 13.1
    assert weather.attributes["humidity"] == 71
    assert weather.attributes["wind_bearing"] == 200
    assert weather.attributes["visibility"] == 24.14
    assert weather.attributes["attribution"].startswith("Data provided by Apple Weather.")
    assert weather.attributes["attribution_logo_dark"] == "https://weatherkit.apple.com/assets/d.png"

    assert hass.states.get("sensor.apple_weather_next_hour").state == \
        "Light rain starting in 12 min, stopping 23 min later"
    alerts = hass.states.get("sensor.apple_weather_alerts")
    assert alerts.state == "1"
    assert alerts.attributes["alerts"][0]["source"] == "National Weather Service"
    assert alerts.attributes["alerts"][0]["text"].startswith("...WIND ADVISORY")
    assert hass.states.get("sensor.apple_weather_pressure_trend").state == "falling"
    assert hass.states.get("sensor.apple_weather_precipitation_intensity").state == "0.0"
    assert hass.states.get("sensor.apple_weather_moon_phase").state == "waxing_crescent"
    aqi = hass.states.get("sensor.outdoor_air_quality_index")
    assert aqi.state == "42" and aqi.attributes["pm2_5_ugm3"] == 6.1

    # One alert, announced once; its text cost one call.
    assert [e.data["title"] for e in events] == ["Wind Advisory"]
    assert len(calls["alert"]) == 1
    # Availability + one weather call + one alert text.
    assert hass.states.get("sensor.apple_weather_api_calls").state == "3"
    data_sets, kwargs = calls["weather"][0]
    assert data_sets == ["currentWeather", "forecastNextHour", "weatherAlerts", "forecastHourly", "forecastDaily"]
    assert kwargs["hourly_end"] - kwargs["hourly_start"] == timedelta(days=10)


async def test_forecasts(hass: HomeAssistant, loaded) -> None:
    async def forecast(kind: str) -> list[dict]:
        result = await hass.services.async_call(WEATHER_DOMAIN, SERVICE_GET_FORECASTS,
                                                {"entity_id": WEATHER, "type": kind}, blocking=True,
                                                return_response=True)
        return result[WEATHER]["forecast"]

    daily = await forecast("daily")
    assert len(daily) == 10
    assert {"temperature", "templow", "precipitation", "precipitation_probability", "wind_speed",
            "wind_gust_speed", "wind_bearing", "uv_index", "condition"} <= set(daily[0])
    hourly = await forecast("hourly")
    assert len(hourly) == 48
    assert hourly[0]["datetime"] == "2026-10-15T18:00:00Z"
    assert {"apparent_temperature", "humidity", "cloud_coverage", "dew_point", "pressure"} <= set(hourly[0])
    twice = await forecast("twice_daily")
    assert twice[0]["is_daytime"] is True


async def test_minute_updates_skip_the_forecasts_until_due(hass: HomeAssistant, loaded, freezer) -> None:
    _, calls, _, events = loaded
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls["weather"][-1][0] == ["currentWeather", "forecastNextHour", "weatherAlerts"]
    assert len(calls["alert"]) == 1 and len(events) == 1  # the same alert isn't fetched or announced again
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert "forecastHourly" in calls["weather"][-1][0]


async def test_outage_keeps_the_last_data(hass: HomeAssistant, loaded, freezer) -> None:
    _, calls, state, _ = loaded
    state["error"] = WeatherKitError("cannot_connect")
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(WEATHER).state == "sunny"
    coordinator = loaded[0].runtime_data.weather
    assert coordinator.update_interval == timedelta(seconds=120)


async def test_rejected_key_asks_for_a_new_one(hass: HomeAssistant, loaded, freezer) -> None:
    entry, _, state, _ = loaded
    state["error"] = WeatherKitError("invalid_auth", 401)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unload_saves_the_call_count(hass: HomeAssistant, loaded, hass_storage) -> None:
    entry = loaded[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    saved = hass_storage[f"fenton_weatherkit.{entry.entry_id}"]["data"]
    assert saved["budget"]["count"] == 3
    assert saved["seen_alerts"] == ["2f6f2e0b-1b1c-4e2e-9a39-6d7c2d4f1a10"]
