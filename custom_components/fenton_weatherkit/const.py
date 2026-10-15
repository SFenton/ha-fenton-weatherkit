"""Constants for Fenton WeatherKit."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "fenton_weatherkit"
LOGGER = logging.getLogger(__package__)

API_BASE = "https://weatherkit.apple.com"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
DATA_SOURCES_URL = "https://developer.apple.com/weatherkit/data-source-attribution/"
ATTRIBUTION = f"Data provided by Apple Weather. {DATA_SOURCES_URL}"
AIR_QUALITY_ATTRIBUTION = "Air quality by Open-Meteo.com (CAMS), CC BY 4.0"

CONF_KEY_ID = "key_id"
CONF_TEAM_ID = "team_id"
CONF_SERVICE_ID = "service_id"
CONF_KEY_PEM = "key_pem"

CONF_INTERVAL = "interval_seconds"
CONF_FORECAST_INTERVAL = "forecast_interval_minutes"
CONF_HOURLY_HOURS = "hourly_hours"
CONF_MONTHLY_BUDGET = "monthly_budget"
CONF_AIR_QUALITY = "air_quality"

DEFAULT_INTERVAL = 60
MIN_INTERVAL = 10
DEFAULT_FORECAST_INTERVAL = 15
DEFAULT_HOURLY_HOURS = 48
MAX_HOURLY_HOURS = 240
DEFAULT_MONTHLY_BUDGET = 400_000
# Apple includes 500,000 calls a month with the developer membership.
INCLUDED_MONTHLY_CALLS = 500_000

FORECAST_DAYS = 10
AIR_QUALITY_INTERVAL = timedelta(minutes=15)
METADATA_REFRESH = timedelta(hours=24)
# Keep serving the last good data through short outages, as the core integration does.
STALE_AFTER = timedelta(hours=1)
MAX_BACKOFF = timedelta(minutes=30)
# Each new alert's full text costs one call; more than this in one update waits for the next.
MAX_ALERT_DETAILS_PER_UPDATE = 3

DATA_CURRENT = "currentWeather"
DATA_DAILY = "forecastDaily"
DATA_HOURLY = "forecastHourly"
DATA_NEXT_HOUR = "forecastNextHour"
DATA_ALERTS = "weatherAlerts"
FAST_DATA_SETS = (DATA_CURRENT, DATA_NEXT_HOUR, DATA_ALERTS)
SLOW_DATA_SETS = (DATA_HOURLY, DATA_DAILY)

EVENT_ALERT = f"{DOMAIN}_alert"
