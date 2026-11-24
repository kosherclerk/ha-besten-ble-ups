"""Sensors for the BestEn BLE UPS."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import BestenUpsConfigEntry, BestenUpsCoordinator, UpsData
from .entity import BestenUpsEntity


@dataclass(frozen=True, kw_only=True)
class UpsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[UpsData], Any]
    attrs_fn: Callable[[UpsData], dict[str, Any]] | None = None


SENSORS: tuple[UpsSensorDescription, ...] = (
    UpsSensorDescription(
        key="power_source",
        translation_key="power_source",
        device_class=SensorDeviceClass.ENUM,
        options=["mains", "battery"],
        value_fn=lambda d: d.status.power_source,
    ),
    UpsSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda d: d.status.battery_voltage,
    ),
    UpsSensorDescription(
        key="output_voltage",
        translation_key="output_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda d: d.status.output_voltage,
    ),
    UpsSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda d: d.status.battery_current,
        attrs_fn=lambda d: {"note": "negative = discharging (reliable); positive charging values are uncalibrated"},
    ),
    UpsSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        value_fn=lambda d: d.status.battery_power,
    ),
    UpsSensorDescription(
        key="runtime",
        translation_key="runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=lambda d: d.runtime_h,
        attrs_fn=lambda d: {
            "basis": "time left in this outage (assumes full battery at start)" if d.status.on_battery
            else "full battery at the last measured load",
            "outage_energy_wh": d.outage_energy_wh if d.status.on_battery else None,
        },
    ),
    UpsSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status.temperature,
    ),
    UpsSensorDescription(
        key="charge_stage",
        translation_key="charge_stage",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status.charge_stage,
    ),
    UpsSensorDescription(
        key="charge_current_setting",
        translation_key="charge_current_setting",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.config.charge_current if d.config else None,
    ),
    UpsSensorDescription(
        key="charge_voltage_setting",
        translation_key="charge_voltage_setting",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.config.charge_voltage if d.config else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: BestenUpsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [UpsSensor(coordinator, d) for d in SENSORS]
    entities += [UpsLoadSensor(coordinator), UpsLastRestartSensor(coordinator)]
    async_add_entities(entities)


class UpsSensor(BestenUpsEntity, SensorEntity):
    entity_description: UpsSensorDescription

    def __init__(self, coordinator: BestenUpsCoordinator, description: UpsSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None


class UpsLoadSensor(BestenUpsEntity, RestoreSensor):
    """Power drawn by the devices on the UPS output.

    Live while on battery; on mains it shows the average of the last outage (restored across restarts).
    """

    _attr_translation_key = "load_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BestenUpsCoordinator) -> None:
        super().__init__(coordinator, "load_power")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.load_estimate is None and (last := await self.async_get_last_sensor_data()):
            try:
                self.coordinator.load_estimate = float(last.native_value)
            except (TypeError, ValueError):
                pass

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.load_w

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {"source": "live (on battery)" if data.load_live else "average of the last outage"}


class UpsLastRestartSensor(BestenUpsEntity, SensorEntity):
    """When the UPS module last powered up (from its uptime counter)."""

    _attr_translation_key = "last_restart"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BestenUpsCoordinator) -> None:
        super().__init__(coordinator, "last_restart")
        self._boot: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        boot = dt_util.utcnow() - timedelta(seconds=self.coordinator.data.status.uptime)
        # Keep the value stable: only move it if the counter really jumped (restart).
        if self._boot is None or abs((boot - self._boot).total_seconds()) > 120:
            self._boot = boot.replace(microsecond=0)
        return self._boot
