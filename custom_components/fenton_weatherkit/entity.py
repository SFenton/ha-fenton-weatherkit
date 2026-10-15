"""Shared device info: everything Apple-sourced sits on one "Apple Weather" device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN


def apple_device(entry_id: str) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry_id)}, name="Apple Weather", manufacturer="Apple",
                      model="WeatherKit REST API", entry_type=DeviceEntryType.SERVICE,
                      configuration_url="https://developer.apple.com/weatherkit/")


def air_quality_device(entry_id: str) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, f"{entry_id}_air_quality")}, name="Outdoor", manufacturer="Open-Meteo",
                      model="Air Quality API (CAMS)", entry_type=DeviceEntryType.SERVICE,
                      configuration_url="https://open-meteo.com/en/docs/air-quality-api")
