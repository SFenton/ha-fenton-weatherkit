"""Sensors: next hour, alerts, pressure trend, precipitation intensity, moon phase, API calls and outdoor AQI.

None of the Apple-sourced sensors has a state class: long-term statistics would keep Apple's data
indefinitely, and Apple's terms allow only temporary caching.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, EntityCategory, UnitOfVolumetricFlux
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import AIR_QUALITY_ATTRIBUTION, ATTRIBUTION, INCLUDED_MONTHLY_CALLS
from .coordinator import AirQualityCoordinator, WeatherKitCoordinator, WeatherKitData
from .entity import air_quality_device, apple_device
from .mapping import MOON_PHASES


@dataclass(frozen=True, kw_only=True)
class AppleSensorDescription(SensorEntityDescription):
    value: Callable[[WeatherKitData], Any]
    attributes: Callable[[WeatherKitData], dict[str, Any]] | None = None


def _next_hour_attributes(data: WeatherKitData) -> dict[str, Any]:
    return {key: value for key, value in data.next_hour.items() if key != "summary"}


SENSORS: tuple[AppleSensorDescription, ...] = (
    AppleSensorDescription(
        key="next_hour", translation_key="next_hour",
        value=lambda d: d.next_hour.get("summary"), attributes=_next_hour_attributes),
    AppleSensorDescription(
        key="alerts", translation_key="alerts",
        value=lambda d: len(d.alerts), attributes=lambda d: {"alerts": d.alerts}),
    AppleSensorDescription(
        key="pressure_trend", translation_key="pressure_trend", device_class=SensorDeviceClass.ENUM,
        options=["rising", "falling", "steady"], value=lambda d: d.pressure_trend),
    AppleSensorDescription(
        key="precipitation_intensity", translation_key="precipitation_intensity",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        value=lambda d: d.precipitation_intensity),
    AppleSensorDescription(
        key="moon_phase", translation_key="moon_phase", device_class=SensorDeviceClass.ENUM,
        options=list(MOON_PHASES.values()), value=lambda d: d.moon_phase),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [AppleSensor(runtime.weather, d) for d in SENSORS]
    entities.append(ApiCallsSensor(runtime.weather))
    if runtime.air_quality is not None:
        entities.append(AirQualityIndexSensor(runtime.air_quality))
    async_add_entities(entities)


class AppleSensor(CoordinatorEntity[WeatherKitCoordinator], SensorEntity):
    """A value derived from the latest WeatherKit data."""

    entity_description: AppleSensorDescription
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    # The minute-by-minute list and alert texts change constantly and are large; keep them out of history.
    _unrecorded_attributes = frozenset({"minutes", "alerts"})

    def __init__(self, coordinator: WeatherKitCoordinator, description: AppleSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = apple_device(entry_id)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.data)


class ApiCallsSensor(CoordinatorEntity[WeatherKitCoordinator], SensorEntity):
    """Calls this month, so the usage page never holds a surprise."""

    _attr_has_entity_name = True
    _attr_translation_key = "api_calls"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "calls"

    def __init__(self, coordinator: WeatherKitCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_api_calls"
        self._attr_device_info = apple_device(entry_id)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.budget.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        interval = self.coordinator.update_interval
        return {
            "month": self.coordinator.budget.month,
            "projected": self.coordinator.budget.projected(now),
            "budget": self.coordinator.budget.budget,
            "included": INCLUDED_MONTHLY_CALLS,
            "interval_seconds": interval.total_seconds() if interval else None,
            "data_sets": self.coordinator.data.data_sets if self.coordinator.data else [],
        }


class AirQualityIndexSensor(CoordinatorEntity[AirQualityCoordinator], SensorEntity):
    """sensor.outdoor_air_quality_index: US AQI, with pollutant concentrations as attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "air_quality_index"
    _attr_device_class = SensorDeviceClass.AQI
    _attr_attribution = AIR_QUALITY_ATTRIBUTION

    def __init__(self, coordinator: AirQualityCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_air_quality_index"
        self._attr_device_info = air_quality_device(entry_id)

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.get("us_aqi")
        return round(value) if isinstance(value, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attributes = {f"{key}_ugm3": data.get(key) for key in ("pm2_5", "pm10", "ozone", "nitrogen_dioxide",
                                                                "carbon_monoxide") if data.get(key) is not None}
        attributes["unit_of_concentration"] = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        attributes["observed"] = data.get("time")
        return attributes
