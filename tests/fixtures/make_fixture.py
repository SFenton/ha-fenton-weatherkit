"""Regenerate weather.json: a WeatherKit response with all five data sets, read at 2026-10-15 18:03 UTC.

Shapes follow Apple's REST documentation and a recorded 2023 response (Home Assistant core's weatherkit
fixture); values are made up. Run: python tests/fixtures/make_fixture.py
"""

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

READ = datetime(2026, 10, 15, 18, 3, 4, tzinfo=timezone.utc)
HOUR0 = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)
DAY0 = datetime(2026, 10, 15, 7, tzinfo=timezone.utc)  # local midnight, America/Los_Angeles


def z(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def meta(expire: timedelta) -> dict:
    return {"attributionURL": "https://developer.apple.com/weatherkit/data-source-attribution/",
            "expireTime": z(READ + expire), "latitude": 47.61, "longitude": -122.33, "readTime": z(READ),
            "reportedTime": z(READ - timedelta(minutes=50)), "units": "m", "version": 1}


def hour(i: int) -> dict:
    t = HOUR0 - timedelta(hours=1) + timedelta(hours=i)
    local = (t.hour - 7) % 24
    daylight = 7 <= local < 19
    temp = 12 + 5 * math.sin((local - 9) / 24 * 2 * math.pi)
    rainy = 20 <= i < 26
    return {"forecastStart": z(t), "cloudCover": 0.9 if rainy else 0.35, "conditionCode": "Rain" if rainy else
            ("Clear" if i % 7 else "PartlyCloudy"), "daylight": daylight, "humidity": 0.72,
            "precipitationAmount": 1.2 if rainy else 0.0, "precipitationIntensity": 1.2 if rainy else 0.0,
            "precipitationChance": 0.8 if rainy else 0.05, "precipitationType": "rain" if rainy else "clear",
            "pressure": 1016.2, "pressureTrend": "falling", "snowfallIntensity": 0.0, "snowfallAmount": 0.0,
            "temperature": round(temp, 2), "temperatureApparent": round(temp - 1.5, 2),
            "temperatureDewPoint": 7.1, "uvIndex": 3 if daylight else 0, "visibility": 24000.0,
            "windDirection": (350 + 20 * (i % 2)) % 360, "windGust": 20.0 + i % 5, "windSpeed": 10.0 + i % 3}


def day(i: int) -> dict:
    start = DAY0 + timedelta(days=i)
    part = lambda s, e, code: {"forecastStart": z(s), "forecastEnd": z(e), "cloudCover": 0.4, "conditionCode": code,
                               "humidity": 0.7, "precipitationAmount": 0.5, "precipitationAmountByType": {},
                               "precipitationChance": 0.3, "precipitationType": "rain", "snowfallAmount": 0.0,
                               "windDirection": 200, "windSpeed": 11.5}
    return {"forecastStart": z(start), "forecastEnd": z(start + timedelta(days=1)), "conditionCode": "PartlyCloudy",
            "maxUvIndex": 4, "moonPhase": "waxingCrescent", "moonrise": z(start + timedelta(hours=10)),
            "moonset": z(start + timedelta(hours=20)), "precipitationAmount": 2.4, "precipitationAmountByType": {},
            "precipitationChance": 0.45, "precipitationType": "rain", "snowfallAmount": 0.0,
            "solarMidnight": z(start + timedelta(hours=1)), "solarNoon": z(start + timedelta(hours=13)),
            "sunrise": z(start + timedelta(hours=7, minutes=25)), "sunset": z(start + timedelta(hours=18, minutes=17)),
            "temperatureMax": 17.0 - i * 0.3, "temperatureMin": 8.0 - i * 0.2,
            "daytimeForecast": part(start + timedelta(hours=7), start + timedelta(hours=19), "PartlyCloudy"),
            "overnightForecast": part(start + timedelta(hours=19), start + timedelta(hours=31), "Clear")}


def minute(i: int) -> dict:
    wet = 12 <= i < 35
    return {"startTime": z(READ.replace(second=0) + timedelta(minutes=i)), "precipitationChance": 0.7 if wet else 0.05,
            "precipitationIntensity": 1.1 if wet else 0.0}


response = {
    "currentWeather": {"name": "CurrentWeather", "metadata": meta(timedelta(minutes=5)), "asOf": z(READ),
                       "cloudCover": 0.62, "cloudCoverLowAltPct": 0.35, "cloudCoverMidAltPct": 0.22,
                       "cloudCoverHighAltPct": 0.32, "conditionCode": "MostlyClear", "daylight": True, "humidity": 0.71,
                       "precipitationIntensity": 0.0, "pressure": 1016.4, "pressureTrend": "falling",
                       "temperature": 14.2, "temperatureApparent": 13.1, "temperatureDewPoint": 9.0, "uvIndex": 3,
                       "visibility": 24135.0, "windDirection": 200, "windGust": 24.1, "windSpeed": 12.3},
    "forecastDaily": {"name": "DailyForecast", "metadata": meta(timedelta(hours=1)), "days": [day(i) for i in range(10)]},
    "forecastHourly": {"name": "HourlyForecast", "metadata": meta(timedelta(hours=1)),
                       "hours": [hour(i) for i in range(241)]},
    "forecastNextHour": {"name": "NextHourForecast", "metadata": meta(timedelta(minutes=5)),
                         "forecastStart": z(READ.replace(second=0)), "forecastEnd": z(READ.replace(second=0) + timedelta(hours=1)),
                         "minutes": [minute(i) for i in range(61)],
                         "summary": [
                             {"startTime": z(READ.replace(second=0)), "endTime": z(READ.replace(second=0) + timedelta(minutes=12)),
                              "condition": "clear", "precipitationChance": 0.05, "precipitationIntensity": 0.0},
                             {"startTime": z(READ.replace(second=0) + timedelta(minutes=12)),
                              "endTime": z(READ.replace(second=0) + timedelta(minutes=35)),
                              "condition": "rain", "precipitationChance": 0.7, "precipitationIntensity": 1.1},
                             {"startTime": z(READ.replace(second=0) + timedelta(minutes=35)),
                              "condition": "clear", "precipitationChance": 0.05, "precipitationIntensity": 0.0}]},
    "weatherAlerts": {"name": "WeatherAlerts", "metadata": meta(timedelta(minutes=5)),
                      "detailsUrl": "https://weatherkit.apple.com/alertDetails/index.html?ids=x",
                      "alerts": [{"name": "WeatherAlert", "id": "2f6f2e0b-1b1c-4e2e-9a39-6d7c2d4f1a10",
                                  "areaId": "WAZ558", "areaName": "Seattle and Vicinity", "certainty": "likely",
                                  "countryCode": "US", "description": "Wind Advisory",
                                  "detailsUrl": "https://weatherkit.apple.com/alertDetails/index.html?ids=2f6f2e0b",
                                  "effectiveTime": z(READ - timedelta(hours=2)),
                                  "eventEndTime": z(READ + timedelta(hours=10)),
                                  "eventOnsetTime": z(READ + timedelta(hours=1)),
                                  "expireTime": z(READ + timedelta(hours=10)),
                                  "issuedTime": z(READ - timedelta(hours=2)), "responses": ["prepare"],
                                  "severity": "moderate", "source": "National Weather Service", "urgency": "expected"}]},
}

alert_detail = {"id": "2f6f2e0b-1b1c-4e2e-9a39-6d7c2d4f1a10", "area": {}, "messages": [
    {"language": "en", "text": "...WIND ADVISORY IN EFFECT FROM 11 AM TO 9 PM PDT...\n\n* WHAT...South winds 20 to 30 mph."}]}

here = Path(__file__).parent
(here / "weather.json").write_text(json.dumps(response, separators=(",", ":")))
(here / "alert.json").write_text(json.dumps(alert_detail, indent=1))
