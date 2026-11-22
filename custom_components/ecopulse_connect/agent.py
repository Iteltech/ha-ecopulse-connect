"""Agent EcoPulse : heartbeat périodique, réception et exécution des ordres."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .collector import Collector
from .const import (
    ACTION_REBOOT,
    ACTION_RESTART,
    ACTION_UPDATE,
    ALLOWED_ACTIONS,
    FEATURE_BACKUP,
    FEATURE_INSTALL,
    FEATURE_SPECIFIC_VERSION,
    HEARTBEAT_INTERVAL,
    HTTP_TIMEOUT,
    SIGNAL_UPDATED,
)

_LOGGER = logging.getLogger(__name__)
_ENTITY_RE = re.compile(r"^update\.[a-z0-9_]+$")


class EcoPulseError(Exception):
    """Erreur de communication avec le serveur."""


class EcoPulseAuthError(EcoPulseError):
    """Token refusé par le serveur (401)."""


async def async_post(hass: HomeAssistant, url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST JSON vers le serveur EcoPulse et renvoie la réponse décodée."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
        ) as resp:
            if resp.status == 401:
                raise EcoPulseAuthError("Token refusé")
            body = await resp.json(content_type=None)
            if resp.status != 200:
                raise EcoPulseError(f"HTTP {resp.status} : {body}")
            return body if isinstance(body, dict) else {}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise EcoPulseError(f"Serveur injoignable : {err}") from err


class EcoPulseAgent:
    """Un agent par entrée de configuration."""

    def __init__(self, hass: HomeAssistant, entry_id: str, url: str, token: str, version: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.url = url
        self.token = token
        self.collector = Collector(hass, version)
        self._unsub: Callable[[], None] | None = None
        self._cmd_lock = asyncio.Lock()
        self._hb_lock = asyncio.Lock()
        self._cmd_task: asyncio.Task | None = None
        # État exposé aux entités et aux diagnostics
        self.last_heartbeat: datetime | None = None
        self.last_error: str | None = None
        self.server_ok: bool | None = None
        self.last_payload: dict[str, Any] | None = None
        self.last_response: dict[str, Any] | None = None
        self.last_command: dict[str, Any] | None = None

    # ---------- cycle de vie ----------

    @callback
    def async_start(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._async_tick, HEARTBEAT_INTERVAL, name="EcoPulse heartbeat"
        )

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _async_tick(self, _now: datetime) -> None:
        await self.async_heartbeat(boot=False)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry_id))

    # ---------- heartbeat ----------

    async def async_heartbeat(self, boot: bool = False) -> None:
        """Envoie la télémétrie ; lance l'ordre reçu en tâche de fond."""
        if self._hb_lock.locked():
            return
        async with self._hb_lock:
            payload = await self.collector.async_collect(boot)
            self.last_payload = payload
            try:
                resp = await async_post(self.hass, self.url, self.token, payload)
            except EcoPulseError as err:
                self.server_ok = False
                self.last_error = str(err)
                _LOGGER.error("Heartbeat échoué : %s", err)
                self._notify()
                return
            self.server_ok = True
            self.last_error = None
            self.last_heartbeat = dt_util.utcnow()
            self.last_response = resp
            self._notify()

        cmd = resp.get("command")
        if isinstance(cmd, dict) and cmd.get("id"):
            if self._cmd_lock.locked():
                _LOGGER.warning("Ordre %s reçu pendant un autre ordre : ignoré", cmd.get("id"))
                return
            self._cmd_task = self.hass.async_create_background_task(
                self._async_run_command(cmd), name=f"EcoPulse command {cmd.get('id')}"
            )

    async def _async_result(self, cmd_id: str, status: str, message: str = "") -> None:
        if self.last_command and self.last_command.get("id") == cmd_id:
            self.last_command["status"] = status
            self.last_command["message"] = message
            self.last_command["updated"] = dt_util.utcnow().isoformat()
            self._notify()
        try:
            await async_post(
                self.hass, self.url, self.token,
                {"type": "result", "id": str(cmd_id), "status": status, "message": message},
            )
        except EcoPulseError as err:
            _LOGGER.error("Résultat de l'ordre %s non transmis : %s", cmd_id, err)

    # ---------- ordres ----------

    def validate(self, cmd: dict[str, Any]) -> tuple[str | None, int]:
        """Renvoie (motif de refus ou None, supported_features). Même logique que le package YAML."""
        action = cmd.get("action")
        if action not in ALLOWED_ACTIONS:
            return f"action non autorisée : {action}", 0
        try:
            expires = int(cmd.get("expires") or 0)
        except (TypeError, ValueError):
            expires = 0
        if expires < dt_util.utcnow().timestamp():
            return "ordre expiré", 0
        if action != ACTION_UPDATE:
            return None, 0
        ent = str(cmd.get("entity") or "")
        version = str(cmd.get("version") or "")
        state = self.hass.states.get(ent) if _ENTITY_RE.match(ent) else None
        if state is None or state.state not in ("on", "off"):
            return f"entité inconnue : {ent}", 0
        features = int(state.attributes.get("supported_features") or 0)
        if str(state.attributes.get("installed_version")) == version:
            return "déjà installée", features
        if not features & FEATURE_INSTALL:
            return "installation non supportée", features
        latest = str(state.attributes.get("latest_version"))
        if latest != version and not features & FEATURE_SPECIFIC_VERSION:
            return f"version disponible différente ({latest})", features
        return None, features

    async def _async_run_command(self, cmd: dict[str, Any]) -> None:
        async with self._cmd_lock:
            cmd_id = str(cmd["id"])
            action, ent, version = cmd.get("action"), str(cmd.get("entity") or ""), str(cmd.get("version") or "")
            self.last_command = {
                "id": cmd_id, "action": action, "entity": ent, "version": version,
                "received": dt_util.utcnow().isoformat(), "status": "received", "message": "",
            }
            refusal, features = self.validate(cmd)
            _LOGGER.warning("Ordre reçu : %s %s %s -> %s", action, ent, version, f"refusé : {refusal}" if refusal else "exécution")
            if refusal:
                await self._async_result(cmd_id, "done" if refusal == "déjà installée" else "rejected", refusal)
                return

            # « started » est envoyé avant : un redémarrage coupe l'agent, le serveur conclut via le heartbeat de boot
            await self._async_result(cmd_id, "started")
            try:
                if action == ACTION_UPDATE:
                    data: dict[str, Any] = {"entity_id": ent}
                    if features & FEATURE_BACKUP:
                        data["backup"] = True
                    if features & FEATURE_SPECIFIC_VERSION:
                        data["version"] = version
                    await self.hass.services.async_call("update", "install", data, blocking=True)
                elif action == ACTION_RESTART:
                    await self.hass.services.async_call("homeassistant", "restart", blocking=False)
                    return
                elif action == ACTION_REBOOT:
                    await self.hass.services.async_call("hassio", "host_reboot", blocking=False)
                    return
            except Exception as err:  # noqa: BLE001 - toute erreur est remontée au serveur
                await self._async_result(cmd_id, "failed", f"Erreur : {err}")
                return

            await asyncio.sleep(5)
            state = self.hass.states.get(ent)
            installed = state.attributes.get("installed_version") if state else None
            await self._async_result(
                cmd_id, "done" if str(installed) == version else "failed", f"Version installée : {installed}"
            )
