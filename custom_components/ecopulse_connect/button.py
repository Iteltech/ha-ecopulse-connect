"""Bouton : envoyer la télémétrie maintenant."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcoPulseConfigEntry
from .entity import EcoPulseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoPulseConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([SendNowButton(entry.runtime_data, "send_now")])


class SendNowButton(EcoPulseEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        await self.agent.async_heartbeat(boot=False)
