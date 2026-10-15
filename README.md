# Fenton WeatherKit

A Home Assistant integration that reads Apple WeatherKit's REST API and replaces Pirate Weather for the Fenton Home web dashboard and native app. Home Assistant is the only caller: the WeatherKit key stays in the config entry, and the apps read the entities below over their existing Home Assistant connection.

## Entities

| Entity | Holds |
|---|---|
| `weather.apple_weather` | Current conditions and `weather.get_forecasts` for `hourly` (48 h by default, up to 240), `daily` (10 days) and `twice_daily`. Same attribute and forecast field names as Pirate Weather. Clear skies at night are `clear-night`. Daily wind speed, gust and direction come from the day's hours, since WeatherKit's daily data has no gust. |
| `sensor.apple_weather_next_hour` | "Light rain starting in 12 min, stopping 23 min later"; attributes `minutes` (`start`, `chance` %, `intensity` mm/h), `precipitation_type`, `starts_in_minutes`, `ends_in_minutes`. |
| `sensor.apple_weather_alerts` | Number of active alerts; attribute `alerts` with `title`, `source`, `severity`, `urgency`, `certainty`, `area`, `effective`, `expires`, `details_url` and the agency's `text`. A new alert fires `fenton_weatherkit_alert` once. |
| `sensor.apple_weather_pressure_trend` | `rising`, `falling` or `steady`. |
| `sensor.apple_weather_precipitation_intensity` | mm/h now. |
| `sensor.apple_weather_moon_phase` | Moon phase, in the moon integration's names. |
| `sensor.apple_weather_api_calls` | Calls this month (diagnostic), with `projected`, `budget` and `interval_seconds`. |
| `sensor.outdoor_air_quality_index` | US AQI from Open-Meteo (WeatherKit has no air quality), with PM2.5, PM10, ozone, NO₂ and CO in µg/m³. Can be turned off in the options. |

## Calls

Each update is one call asking for current conditions, the next-hour forecast and alerts. The hourly and daily forecasts ride along in the same call every 15 minutes, or sooner when Apple's expiry time for them passes, so they cost nothing extra. A new alert's full text costs one call, once. Availability is checked once a day.

At the default of once a minute that is about 44,640 calls in a 31-day month, under 9% of the 500,000 included with the Apple Developer Program. The integration counts calls per UTC calendar month and lengthens the interval by itself to stay under the monthly budget (default 400,000). Failures back off, doubling up to 30 minutes, and the last good data is kept for an hour.

## Apple's terms

- Wherever the apps show this data they must show the Apple Weather trademark and link to <https://developer.apple.com/weatherkit/data-source-attribution/>. `weather.apple_weather` carries `attribution_url` and Apple's logo URLs (`attribution_logo_light`, `attribution_logo_dark`).
- Alerts must name the issuing agency, link `details_url`, and be shown unaltered.
- Apple data may be cached only temporarily. Forecasts never enter the recorder, the minute and alert lists are unrecorded attributes, and no Apple-sourced sensor has a state class, so none of it lands in long-term statistics. Don't export these entities to an external database.
- WeatherKit may not be used for an emergency or life-safety product.

## Install

1. Apple Developer account → Certificates, Identifiers & Profiles:
   - **Keys** → + → tick **WeatherKit** (an existing APNs key can have WeatherKit added) → download the .p8 and note the Key ID.
   - **Identifiers** → + → **Services IDs** → e.g. `com.sfenton.home.weatherkit`.
   - Note the Team ID from Membership details.
2. HACS → Integrations → ⋮ → Custom repositories → `https://github.com/SFenton/ha-fenton-weatherkit` (Integration) → download **Fenton WeatherKit** → restart.
3. Settings → Devices & services → Add integration → **Fenton WeatherKit**. Paste the Key ID, Team ID, Services ID and the whole .p8 file. The key is checked with Apple before it is saved; if Apple later rejects it, Home Assistant asks for a new one.
4. Options: update interval (default 60 s), forecast refresh (15 min), hourly length (48 h), monthly budget (400,000), outdoor AQI (on).

## Development

`python -m pytest tests/unit` (no Home Assistant needed); `python -m pytest tests/ha --asyncio-mode=auto` with `pytest-homeassistant-custom-component`. CI also runs HACS and hassfest validation. `tests/fixtures/make_fixture.py` regenerates the recorded response.
