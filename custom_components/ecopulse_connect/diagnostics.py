"""Diagnostics téléchargeables (Settings > Devices & services > EcoPulse Connect)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import EcoPulseConfigEntry
from .const import CONF_TOKEN

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EcoPulseConfigEntry) -> dict[str, Any]:
    agent = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "agent_version": agent.collector.agent_version,
        "server_ok": agent.server_ok,
        "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        "last_error": agent.last_error,
        "last_payload": agent.last_payload,
        "last_response": agent.last_response,
        "last_command": agent.last_command,
    }
