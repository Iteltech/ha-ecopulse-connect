"""Capteur binaire : serveur EcoPulse joignable."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoPulseConfigEntry
from .entity import EcoPulseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoPulseConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ServerConnectedSensor(entry.runtime_data, "server")])


class ServerConnectedSensor(EcoPulseEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        return self.agent.server_ok
