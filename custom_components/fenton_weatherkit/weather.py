"""weather.apple_weather: current conditions and hourly, daily and twice-daily forecasts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTRIBUTION, DATA_SOURCES_URL
from .coordinator import WeatherKitCoordinator
from .entity import apple_device


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([AppleWeather(entry.runtime_data.weather)])


class AppleWeather(SingleCoordinatorWeatherEntity[WeatherKitCoordinator]):
    """Same attribute and forecast field names as Pirate Weather, so the apps only change the entity id."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.MBAR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = (WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
                                | WeatherEntityFeature.FORECAST_TWICE_DAILY)
    _unrecorded_attributes = frozenset({"attribution_url", "attribution_logo_light", "attribution_logo_dark",
                                        "attribution_logo_square"})

    def __init__(self, coordinator: WeatherKitCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = entry_id
        self._attr_device_info = apple_device(entry_id)

    def _value(self, key: str) -> Any:
        return self.coordinator.data.current.get(key)

    @property
    def condition(self) -> str | None:
        return self._value("condition")

    @property
    def native_temperature(self) -> float | None:
        return self._value("native_temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._value("native_apparent_temperature")

    @property
    def native_dew_point(self) -> float | None:
        return self._value("native_dew_point")

    @property
    def humidity(self) -> float | None:
        return self._value("humidity")

    @property
    def native_pressure(self) -> float | None:
        return self._value("native_pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self._value("native_wind_speed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._value("native_wind_gust_speed")

    @property
    def wind_bearing(self) -> float | None:
        return self._value("wind_bearing")

    @property
    def native_visibility(self) -> float | None:
        return self._value("native_visibility")

    @property
    def uv_index(self) -> float | None:
        return self._value("uv_index")

    @property
    def cloud_coverage(self) -> float | None:
        return self._value("cloud_coverage")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The legal link and Apple's logos, which the apps must show next to Apple's data."""
        logos = self.coordinator.attribution
        attributes = {"attribution_url": DATA_SOURCES_URL}
        for name, key in (("attribution_logo_light", "logoLight@3x"), ("attribution_logo_dark", "logoDark@3x"),
                          ("attribution_logo_square", "logoSquare@3x")):
            if logos.get(key):
                attributes[name] = logos[key]
        return attributes

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return self.coordinator.data.hourly or None

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        return self.coordinator.data.daily or None

    @callback
    def _async_forecast_twice_daily(self) -> list[Forecast] | None:
        return self.coordinator.data.twice_daily or None
