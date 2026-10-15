"""WeatherKit responses into Home Assistant weather values."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fenton_weatherkit import mapping

NOW = datetime(2026, 10, 15, 18, 3, 4, tzinfo=timezone.utc)


def test_conditions_split_clear_by_daylight() -> None:
    assert mapping.condition("Clear", True) == "sunny"
    assert mapping.condition("MostlyClear", False) == "clear-night"
    assert mapping.condition("PartlyCloudy", False) == "partlycloudy"
    assert mapping.condition("Thunderstorms", True) == "lightning-rainy"
    assert mapping.condition("ScatteredThunderstorms", True) == "lightning"
    assert mapping.condition("WintryMix", True) == "snowy-rainy"
    assert mapping.condition("heavyRain", True) == "pouring"
    assert mapping.condition("Tornado", True) is None
    assert mapping.condition(None) is None


def test_every_condition_maps_to_a_home_assistant_condition() -> None:
    known = {"sunny", "clear-night", "partlycloudy", "cloudy", "rainy", "pouring", "snowy", "snowy-rainy", "hail",
             "lightning", "lightning-rainy", "fog", "windy", "windy-variant", "exceptional"}
    assert len(mapping.CONDITIONS) == 34
    assert set(mapping.CONDITIONS.values()) <= known


def test_current(response) -> None:
    current = mapping.current(response["currentWeather"])
    assert current == {
        "condition": "sunny", "native_temperature": 14.2, "native_apparent_temperature": 13.1,
        "native_dew_point": 9.0, "humidity": 71.0, "native_pressure": 1016.4, "native_wind_speed": 12.3,
        "native_wind_gust_speed": 24.1, "wind_bearing": 200.0, "native_visibility": 24.14, "uv_index": 3.0,
        "cloud_coverage": 62.0,
    }


def test_hourly_starts_this_hour_and_honours_the_limit(response) -> None:
    hours = mapping.hourly(response["forecastHourly"]["hours"], NOW, 48)
    assert len(hours) == 48
    assert hours[0]["datetime"] == "2026-10-15T18:00:00Z"
    assert set(hours[0]) >= {"condition", "native_temperature", "native_apparent_temperature", "native_dew_point",
                             "native_pressure", "native_wind_speed", "native_wind_gust_speed", "wind_bearing",
                             "humidity", "native_precipitation", "precipitation_probability", "cloud_coverage",
                             "uv_index"}
    night = next(h for h in hours if h["datetime"] == "2026-10-16T05:00:00Z")
    assert night["condition"] == "clear-night"
    assert hours[20]["condition"] == "rainy" and hours[20]["precipitation_probability"] == 80.0


def test_daily_fills_wind_from_the_hours(response) -> None:
    days = mapping.daily(response["forecastDaily"]["days"], response["forecastHourly"]["hours"], NOW)
    assert len(days) == 10
    today = days[0]
    assert today["datetime"] == "2026-10-15T07:00:00Z"
    assert today["native_temperature"] == 17.0 and today["native_templow"] == 8.0
    assert today["precipitation_probability"] == 45.0 and today["uv_index"] == 4
    assert today["native_wind_gust_speed"] == 24.0
    assert 10.0 <= today["native_wind_speed"] <= 12.0
    assert today["wind_bearing"] in (0, 360) or today["wind_bearing"] < 5 or today["wind_bearing"] > 355
    # A day past the hourly data falls back to Apple's daytime wind, and has no gust.
    [beyond] = mapping.daily(response["forecastDaily"]["days"][-1:], [], NOW)
    assert beyond["native_wind_speed"] == 11.5 and beyond["wind_bearing"] == 200
    assert "native_wind_gust_speed" not in beyond


def test_daily_prefers_apples_own_daily_wind() -> None:
    day = {"forecastStart": "2026-10-15T07:00:00Z", "forecastEnd": "2026-10-16T07:00:00Z", "conditionCode": "Clear",
           "temperatureMax": 20, "temperatureMin": 10, "windSpeedAvg": 9.5, "windGustSpeedMax": 41.0}
    [mapped] = mapping.daily([day], [], NOW)
    assert mapped["native_wind_speed"] == 9.5 and mapped["native_wind_gust_speed"] == 41.0


def test_prevailing_bearing_averages_around_north() -> None:
    hours = [{"windDirection": 350, "windSpeed": 10}, {"windDirection": 10, "windSpeed": 10}]
    assert mapping.prevailing_bearing(hours) in (0, 360)
    assert mapping.prevailing_bearing([]) is None


def test_twice_daily(response) -> None:
    parts = mapping.twice_daily(response["forecastDaily"]["days"], NOW)
    assert parts[0]["is_daytime"] is True and parts[0]["native_temperature"] == 17.0
    assert parts[1]["is_daytime"] is False and parts[1]["native_temperature"] == 8.0
    assert parts[1]["condition"] == "clear-night"
    assert len(parts) == 20


def test_next_hour_rain_starting(response) -> None:
    info = mapping.next_hour(response["forecastNextHour"], NOW)
    assert info["summary"] == "Light rain starting in 12 min, stopping 23 min later"
    assert info["starts_in_minutes"] == 12 and info["ends_in_minutes"] == 35
    assert info["precipitation_type"] == "rain"
    assert len(info["minutes"]) == 61
    assert info["minutes"][12] == {"start": "2026-10-15T18:15:00Z", "chance": 70.0, "intensity": 1.1}


def test_next_hour_rain_now(response) -> None:
    info = mapping.next_hour(response["forecastNextHour"], NOW + timedelta(minutes=17))
    assert info["summary"] == "Light rain stopping in 18 min"


def test_next_hour_dry(response) -> None:
    info = mapping.next_hour(response["forecastNextHour"], NOW + timedelta(minutes=40))
    assert info["summary"] == "No precipitation for the next hour"
    assert mapping.next_hour(None, NOW) == {"summary": None}


def test_next_hour_open_ended_heavy_snow() -> None:
    data = {"summary": [{"startTime": "2026-10-15T18:00:00Z", "condition": "snow", "precipitationChance": 0.9,
                         "precipitationIntensity": 9.0}], "minutes": []}
    assert mapping.next_hour(data, NOW)["summary"] == "Heavy snow for the next hour"


def test_alerts_carry_the_agency_text_unaltered(response, alert_detail) -> None:
    [alert] = mapping.alerts(response["weatherAlerts"], NOW, {alert_detail["id"]: alert_detail})
    assert alert["title"] == "Wind Advisory"
    assert alert["source"] == "National Weather Service"
    assert alert["details_url"].startswith("https://weatherkit.apple.com/alertDetails/")
    assert alert["text"] == alert_detail["messages"][0]["text"]
    assert mapping.alerts(response["weatherAlerts"], NOW + timedelta(hours=11), {}) == []
    assert mapping.alerts(None, NOW, {}) == []


def test_moon_phase_and_expiry(response) -> None:
    assert mapping.moon_phase(response["forecastDaily"]["days"]) == "waxing_crescent"
    assert mapping.moon_phase([]) is None
    assert mapping.expire_time(response["forecastHourly"]) == datetime(2026, 10, 15, 19, 3, 4, tzinfo=timezone.utc)
