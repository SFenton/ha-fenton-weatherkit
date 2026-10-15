"""Outdoor US AQI from Open-Meteo, because WeatherKit has no air quality data.

Free, no key, CAMS model data. The apps' AQI tile and briefing hazard read this in place of Pirate Weather's
sensor. EPA AirNow (observed rather than modelled) would be the upgrade if a key is ever added.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .api import REQUEST_TIMEOUT, WeatherKitError
from .const import OPEN_METEO_AIR_QUALITY_URL

FIELDS = ("us_aqi", "pm2_5", "pm10", "ozone", "nitrogen_dioxide", "carbon_monoxide")


async def fetch_air_quality(session: aiohttp.ClientSession, latitude: float, longitude: float) -> dict[str, Any]:
    """Current US AQI and pollutant concentrations (µg/m³)."""
    params = {"latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}",
              "current": ",".join(FIELDS), "timezone": "UTC"}
    try:
        async with session.get(OPEN_METEO_AIR_QUALITY_URL, params=params, timeout=REQUEST_TIMEOUT) as response:
            if response.status >= 400:
                raise WeatherKitError("cannot_connect", response.status, (await response.text())[:200])
            body = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise WeatherKitError("cannot_connect", detail=str(err)) from err
    current = body.get("current") if isinstance(body, dict) else None
    if not isinstance(current, dict) or current.get("us_aqi") is None:
        raise WeatherKitError("cannot_connect", detail="no us_aqi in response")
    return {key: current.get(key) for key in ("time", *FIELDS)}
