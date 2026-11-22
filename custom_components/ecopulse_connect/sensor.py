"""Capteurs : dernier heartbeat, dernier ordre."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoPulseConfigEntry
from .entity import EcoPulseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoPulseConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    agent = entry.runtime_data
    async_add_entities([LastHeartbeatSensor(agent, "last_heartbeat"), LastCommandSensor(agent, "last_command")])


class LastHeartbeatSensor(EcoPulseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> datetime | None:
        return self.agent.last_heartbeat

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"last_error": self.agent.last_error}


class LastCommandSensor(EcoPulseEntity, SensorEntity):
    """État du dernier ordre reçu (received / started / done / failed / rejected)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        return (self.agent.last_command or {}).get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cmd = self.agent.last_command or {}
        return {k: cmd.get(k) for k in ("id", "action", "entity", "version", "message", "received", "updated")}
