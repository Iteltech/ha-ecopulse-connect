"""Base commune des entités EcoPulse Connect."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .agent import EcoPulseAgent
from .const import DOMAIN, NAME, SIGNAL_UPDATED


class EcoPulseEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, agent: EcoPulseAgent, key: str) -> None:
        self.agent = agent
        self._attr_translation_key = key
        self._attr_unique_id = f"{agent.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, agent.entry_id)},
            name=NAME,
            manufacturer="EcoPulse",
            model="Connect",
            sw_version=agent.collector.agent_version,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATED.format(self.agent.entry_id), self.async_write_ha_state
            )
        )
