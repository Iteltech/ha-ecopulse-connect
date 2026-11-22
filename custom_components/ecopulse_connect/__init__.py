"""EcoPulse Connect : supervision et maintenance à distance d'une installation Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant
from homeassistant.loader import async_get_integration

from .agent import EcoPulseAgent
from .const import CONF_TOKEN, CONF_URL

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type EcoPulseConfigEntry = ConfigEntry[EcoPulseAgent]


async def async_setup_entry(hass: HomeAssistant, entry: EcoPulseConfigEntry) -> bool:
    integration = await async_get_integration(hass, entry.domain)
    agent = EcoPulseAgent(
        hass,
        entry.entry_id,
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        str(integration.version or "0"),
    )
    entry.runtime_data = agent
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    agent.async_start()

    if hass.state is CoreState.running:
        # Ajout ou rechargement de l'intégration : heartbeat immédiat
        entry.async_create_task(hass, agent.async_heartbeat(boot=False), "EcoPulse first heartbeat")
    else:
        # Démarrage de HA : heartbeat « boot » (confirme au serveur un redémarrage ou une mise à jour)
        async def _started(_event: Event) -> None:
            await agent.async_heartbeat(boot=True)

        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _started))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcoPulseConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
