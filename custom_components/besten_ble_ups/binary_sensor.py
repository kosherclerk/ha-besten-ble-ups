"""Binary sensors for the BestEn BLE UPS."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BestenUpsConfigEntry, BestenUpsCoordinator, UpsData
from .entity import BestenUpsEntity


@dataclass(frozen=True, kw_only=True)
class UpsBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[UpsData], bool]


BINARY_SENSORS: tuple[UpsBinaryDescription, ...] = (
    UpsBinaryDescription(
        key="ac_power",
        translation_key="ac_power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda d: not d.status.on_battery,
    ),
    UpsBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.charging,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: BestenUpsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(UpsBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class UpsBinarySensor(BestenUpsEntity, BinarySensorEntity):
    entity_description: UpsBinaryDescription

    def __init__(self, coordinator: BestenUpsCoordinator, description: UpsBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)
