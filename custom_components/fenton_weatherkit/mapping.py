"""Turn WeatherKit responses into Home Assistant weather values.

Pure functions with no Home Assistant imports, so the unit tests run without it. Forecast dicts use Home
Assistant's ``native_*`` keys (metric, as WeatherKit reports); the weather entity converts them to the
user's units.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

# Home Assistant condition strings (homeassistant.components.weather.ATTR_CONDITION_*).
SUNNY = "sunny"
CLEAR_NIGHT = "clear-night"
PARTLY_CLOUDY = "partlycloudy"
CLOUDY = "cloudy"
RAINY = "rainy"
POURING = "pouring"
SNOWY = "snowy"
SNOWY_RAINY = "snowy-rainy"
HAIL = "hail"
LIGHTNING = "lightning"
LIGHTNING_RAINY = "lightning-rainy"
FOG = "fog"
WINDY = "windy"
EXCEPTIONAL = "exceptional"

# Every WeatherKit condition code. Clear skies split by daylight, which the core integration doesn't do.
CONDITIONS: dict[str, str] = {
    "Clear": SUNNY,
    "MostlyClear": SUNNY,
    "Hot": SUNNY,
    "Frigid": SUNNY,
    "PartlyCloudy": PARTLY_CLOUDY,
    "MostlyCloudy": CLOUDY,
    "Cloudy": CLOUDY,
    "Foggy": FOG,
    "Haze": FOG,
    "Smoky": FOG,
    "BlowingDust": WINDY,
    "Breezy": WINDY,
    "Windy": WINDY,
    "Drizzle": RAINY,
    "Rain": RAINY,
    "SunShowers": RAINY,
    "HeavyRain": POURING,
    "IsolatedThunderstorms": LIGHTNING,
    "ScatteredThunderstorms": LIGHTNING,
    "Thunderstorms": LIGHTNING_RAINY,
    "StrongStorms": LIGHTNING_RAINY,
    "Hail": HAIL,
    "Flurries": SNOWY,
    "SunFlurries": SNOWY,
    "Snow": SNOWY,
    "HeavySnow": SNOWY,
    "Blizzard": SNOWY,
    "BlowingSnow": SNOWY,
    "Sleet": SNOWY_RAINY,
    "WintryMix": SNOWY_RAINY,
    "FreezingDrizzle": SNOWY_RAINY,
    "FreezingRain": SNOWY_RAINY,
    "Hurricane": EXCEPTIONAL,
    "TropicalStorm": EXCEPTIONAL,
}

MOON_PHASES = {
    "new": "new_moon",
    "waxingCrescent": "waxing_crescent",
    "firstQuarter": "first_quarter",
    "waxingGibbous": "waxing_gibbous",
    "full": "full_moon",
    "waningGibbous": "waning_gibbous",
    "thirdQuarter": "last_quarter",
    "waningCrescent": "waning_crescent",
}

PRECIPITATION_WORDS = {
    "rain": "rain",
    "snow": "snow",
    "sleet": "sleet",
    "hail": "hail",
    "mixed": "mixed precipitation",
    "precipitation": "precipitation",
}


def condition(code: Any, daylight: bool | None = True) -> str | None:
    """The Home Assistant condition for a WeatherKit code; clear skies at night are clear-night."""
    if not isinstance(code, str):
        return None
    mapped = CONDITIONS.get(code) or CONDITIONS.get(code[:1].upper() + code[1:])
    if mapped == SUNNY and daylight is False:
        return CLEAR_NIGHT
    return mapped


def parse_time(value: Any) -> datetime | None:
    """WeatherKit timestamps (ISO 8601, usually with a Z)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _percent(value: Any) -> float | None:
    """WeatherKit fractions (0-1) as percentages."""
    number = _number(value)
    return None if number is None else round(number * 100, 1)


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def current(data: dict[str, Any]) -> dict[str, Any]:
    """Current conditions as weather entity values."""
    visibility = _number(data.get("visibility"))
    return {
        "condition": condition(data.get("conditionCode"), data.get("daylight")),
        "native_temperature": _number(data.get("temperature")),
        "native_apparent_temperature": _number(data.get("temperatureApparent")),
        "native_dew_point": _number(data.get("temperatureDewPoint")),
        "humidity": _percent(data.get("humidity")),
        "native_pressure": _number(data.get("pressure")),
        "native_wind_speed": _number(data.get("windSpeed")),
        "native_wind_gust_speed": _number(data.get("windGust")),
        "wind_bearing": _number(data.get("windDirection")),
        "native_visibility": None if visibility is None else round(visibility / 1000, 2),
        "uv_index": _number(data.get("uvIndex")),
        "cloud_coverage": _percent(data.get("cloudCover")),
    }


def hourly(hours: list[dict[str, Any]], now: datetime, limit: int) -> list[dict[str, Any]]:
    """Hourly forecast from the current hour on, at most ``limit`` entries."""
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    result = []
    for hour in hours:
        start = parse_time(hour.get("forecastStart"))
        if start is None or start < hour_start:
            continue
        result.append(_clean({
            "datetime": hour["forecastStart"],
            "condition": condition(hour.get("conditionCode"), hour.get("daylight")),
            "native_temperature": _number(hour.get("temperature")),
            "native_apparent_temperature": _number(hour.get("temperatureApparent")),
            "native_dew_point": _number(hour.get("temperatureDewPoint")),
            "native_pressure": _number(hour.get("pressure")),
            "native_wind_speed": _number(hour.get("windSpeed")),
            "native_wind_gust_speed": _number(hour.get("windGust")),
            "wind_bearing": _number(hour.get("windDirection")),
            "humidity": _percent(hour.get("humidity")),
            "native_precipitation": _number(hour.get("precipitationAmount")),
            "precipitation_probability": _percent(hour.get("precipitationChance")),
            "cloud_coverage": _percent(hour.get("cloudCover")),
            "uv_index": _number(hour.get("uvIndex")),
        }))
        if len(result) >= limit:
            break
    return result


def _hours_between(hours: list[dict[str, Any]], start: datetime | None, end: datetime | None) -> list[dict[str, Any]]:
    if start is None or end is None:
        return []
    return [hour for hour in hours
            if (when := parse_time(hour.get("forecastStart"))) is not None and start <= when < end]


def prevailing_bearing(hours: list[dict[str, Any]]) -> float | None:
    """Wind direction averaged as vectors weighted by speed, so 350° and 10° average to 0°, not 180°."""
    x = y = 0.0
    for hour in hours:
        bearing, speed = _number(hour.get("windDirection")), _number(hour.get("windSpeed"))
        if bearing is None:
            continue
        weight = speed if speed else 0.001
        x += math.sin(math.radians(bearing)) * weight
        y += math.cos(math.radians(bearing)) * weight
    if x == 0 and y == 0:
        return None
    return round(math.degrees(math.atan2(x, y)) % 360)


def day_wind(day: dict[str, Any], hours: list[dict[str, Any]]) -> dict[str, float | None]:
    """Daily wind: Apple's own daily fields when present, else the day's hours.

    The apps show a daily speed, gust and direction; WeatherKit's documented daily data has none of them.
    """
    in_day = _hours_between(hours, parse_time(day.get("forecastStart")), parse_time(day.get("forecastEnd")))
    speeds = [s for hour in in_day if (s := _number(hour.get("windSpeed"))) is not None]
    gusts = [g for hour in in_day if (g := _number(hour.get("windGust"))) is not None]
    daytime = day.get("daytimeForecast") or {}
    speed = _number(day.get("windSpeedAvg"))
    if speed is None and speeds:
        speed = round(sum(speeds) / len(speeds), 2)
    if speed is None:
        speed = _number(daytime.get("windSpeed"))
    gust = _number(day.get("windGustSpeedMax"))
    if gust is None and gusts:
        gust = max(gusts)
    bearing = prevailing_bearing(in_day)
    if bearing is None:
        bearing = _number(daytime.get("windDirection"))
    return {"native_wind_speed": speed, "native_wind_gust_speed": gust, "wind_bearing": bearing}


def daily(days: list[dict[str, Any]], hours: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Daily forecast from today on."""
    result = []
    for day in days:
        end = parse_time(day.get("forecastEnd"))
        if end is not None and end <= now:
            continue
        daytime = day.get("daytimeForecast") or {}
        result.append(_clean({
            "datetime": day.get("forecastStart"),
            "condition": condition(day.get("conditionCode"), True),
            "native_temperature": _number(day.get("temperatureMax")),
            "native_templow": _number(day.get("temperatureMin")),
            "native_precipitation": _number(day.get("precipitationAmount")),
            "precipitation_probability": _percent(day.get("precipitationChance")),
            "uv_index": _number(day.get("maxUvIndex")),
            "humidity": _percent(daytime.get("humidity")),
            "cloud_coverage": _percent(daytime.get("cloudCover")),
            **day_wind(day, hours),
        }))
    return result


def _day_part(part: dict[str, Any], is_daytime: bool, temperature: float | None) -> dict[str, Any]:
    return _clean({
        "datetime": part.get("forecastStart"),
        "is_daytime": is_daytime,
        "condition": condition(part.get("conditionCode"), is_daytime),
        "native_temperature": temperature,
        "native_precipitation": _number(part.get("precipitationAmount")),
        "precipitation_probability": _percent(part.get("precipitationChance")),
        "native_wind_speed": _number(part.get("windSpeed")),
        "wind_bearing": _number(part.get("windDirection")),
        "humidity": _percent(part.get("humidity")),
        "cloud_coverage": _percent(part.get("cloudCover")),
    })


def twice_daily(days: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Day (7 AM-7 PM) and overnight halves; the day's high goes on the day, its low on the night."""
    result = []
    for day in days:
        for key, is_daytime, temp_key in (("daytimeForecast", True, "temperatureMax"),
                                          ("overnightForecast", False, "temperatureMin")):
            part = day.get(key)
            if not isinstance(part, dict):
                continue
            end = parse_time(part.get("forecastEnd"))
            if end is not None and end <= now:
                continue
            temperature = _number(part.get(temp_key))
            if temperature is None:
                temperature = _number(day.get(temp_key))
            result.append(_day_part(part, is_daytime, temperature))
    return result


def _intensity_word(mm_per_hour: float) -> str:
    if mm_per_hour < 2.5:
        return "light"
    if mm_per_hour < 7.6:
        return "moderate"
    return "heavy"


def _minutes_until(when: datetime | None, now: datetime) -> int | None:
    if when is None:
        return None
    return max(0, round((when - now).total_seconds() / 60))


def next_hour(data: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    """A one-line summary of the minute-by-minute forecast, with the minutes for charts."""
    if not data:
        return {"summary": None}
    periods = [p for p in data.get("summary") or [] if isinstance(p, dict)]
    minutes = [
        {"start": m.get("startTime"), "chance": _percent(m.get("precipitationChance")),
         "intensity": _number(m.get("precipitationIntensity"))}
        for m in data.get("minutes") or [] if isinstance(m, dict) and (parse_time(m.get("startTime")) or now) >= now.replace(second=0, microsecond=0)
    ]
    wet = [p for p in periods if p.get("condition") not in (None, "clear")
           and ((end := parse_time(p.get("endTime"))) is None or end > now)]
    info: dict[str, Any] = {"minutes": minutes, "precipitation_type": None,
                            "starts_in_minutes": None, "ends_in_minutes": None}
    if not wet:
        info["summary"] = "No precipitation for the next hour"
        return info
    period = wet[0]
    kind = PRECIPITATION_WORDS.get(str(period.get("condition")), "precipitation")
    intensity = _number(period.get("precipitationIntensity")) or 0.0
    label = f"{_intensity_word(intensity)} {kind}"
    start = parse_time(period.get("startTime"))
    end = parse_time(period.get("endTime"))
    starts_in = _minutes_until(start, now) or 0
    ends_in = _minutes_until(end, now)
    info.update(precipitation_type=period.get("condition"), starts_in_minutes=starts_in, ends_in_minutes=ends_in,
                chance=_percent(period.get("precipitationChance")), intensity=intensity)
    if starts_in <= 0:
        text = f"{label} stopping in {ends_in} min" if ends_in is not None else f"{label} for the next hour"
    elif ends_in is not None:
        text = f"{label} starting in {starts_in} min, stopping {ends_in - starts_in} min later"
    else:
        text = f"{label} starting in {starts_in} min"
    info["summary"] = text[:1].upper() + text[1:]
    return info


def alerts(data: dict[str, Any] | None, now: datetime, details: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Active alerts, newest first, with the agency's own text when it has been fetched.

    Apple's terms: show the issuing agency in full, link Apple's details page, never alter the text.
    """
    result = []
    for alert in (data or {}).get("alerts") or []:
        if not isinstance(alert, dict) or not alert.get("id"):
            continue
        expires = parse_time(alert.get("expireTime"))
        if expires is not None and expires <= now:
            continue
        detail = details.get(str(alert["id"])) or {}
        messages = [m.get("text") for m in detail.get("messages") or [] if isinstance(m, dict) and m.get("text")]
        result.append(_clean({
            "id": str(alert["id"]),
            "title": alert.get("description"),
            "source": alert.get("source"),
            "severity": alert.get("severity"),
            "urgency": alert.get("urgency"),
            "certainty": alert.get("certainty"),
            "area": alert.get("areaName"),
            "issued": alert.get("issuedTime"),
            "effective": alert.get("effectiveTime"),
            "onset": alert.get("eventOnsetTime"),
            "ends": alert.get("eventEndTime"),
            "expires": alert.get("expireTime"),
            "responses": alert.get("responses") or None,
            "details_url": alert.get("detailsUrl") or (data or {}).get("detailsUrl"),
            "text": "\n\n".join(messages) or None,
        }))
    result.sort(key=lambda a: a.get("issued") or "", reverse=True)
    return result


def moon_phase(days: list[dict[str, Any]]) -> str | None:
    """Today's moon phase in the names Home Assistant's moon integration uses."""
    return MOON_PHASES.get(str(days[0].get("moonPhase"))) if days else None


def expire_time(block: dict[str, Any] | None) -> datetime | None:
    """When Apple says a data set goes stale."""
    return parse_time(((block or {}).get("metadata") or {}).get("expireTime"))
