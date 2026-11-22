"""Collecte des informations envoyées au serveur EcoPulse (télémétrie)."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from typing import Any

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import BACKUP_STALE_AFTER

_LOGGER = logging.getLogger(__name__)

# Entités System Monitor utilisées si elles sont activées (sinon mesure directe)
SYSMON_CPU = "sensor.system_monitor_processor_use"
SYSMON_RAM = "sensor.system_monitor_memory_usage"
SYSMON_DISK = "sensor.system_monitor_disk_usage"


def _num(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        return round(float(state.state), 1)
    except (TypeError, ValueError):
        return None


class Collector:
    """Rassemble l'état du HA. Les mesures système bloquantes tournent dans l'executor."""

    def __init__(self, hass: HomeAssistant, agent_version: str) -> None:
        self.hass = hass
        self.agent_version = agent_version
        self._cpu_prev: tuple[int, int] | None = None

    # ---------- mesures système (executor) ----------

    def _read_cpu(self) -> float | None:
        """Pourcentage CPU depuis /proc/stat, calculé entre deux heartbeats."""
        try:
            with open("/proc/stat", encoding="ascii") as f:
                fields = [int(x) for x in f.readline().split()[1:]]
        except (OSError, ValueError):
            return None
        idle, total = fields[3] + (fields[4] if len(fields) > 4 else 0), sum(fields)
        prev, self._cpu_prev = self._cpu_prev, (idle, total)
        if prev is None or total <= prev[1]:
            return None
        return round(100 * (1 - (idle - prev[0]) / (total - prev[1])), 1)

    @staticmethod
    def _read_ram() -> float | None:
        try:
            info: dict[str, int] = {}
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    key, _, rest = line.partition(":")
                    info[key] = int(rest.split()[0])
            return round(100 * (1 - info["MemAvailable"] / info["MemTotal"]), 1)
        except (OSError, KeyError, ValueError, ZeroDivisionError):
            return None

    def _read_disk(self) -> float | None:
        try:
            usage = shutil.disk_usage(self.hass.config.config_dir)
            return round(100 * usage.used / usage.total, 1)
        except OSError:
            return None

    def _system_metrics(self) -> tuple[float | None, float | None, float | None]:
        return self._read_cpu(), self._read_ram(), self._read_disk()

    # ---------- sources HA ----------

    def _os_version(self) -> str | None:
        try:
            from homeassistant.components.hassio import get_os_info  # noqa: PLC0415

            info = get_os_info(self.hass) or {}
            return info.get("version")
        except Exception:  # noqa: BLE001 - pas de Supervisor (installation non HAOS)
            return None

    def _updates(self) -> list[dict[str, Any]]:
        out = []
        for st in self.hass.states.async_all("update"):
            attrs = st.attributes
            out.append(
                {
                    "entity_id": st.entity_id,
                    "title": attrs.get("title") or attrs.get("friendly_name") or st.entity_id,
                    "installed": attrs.get("installed_version"),
                    "latest": attrs.get("latest_version"),
                    "in_progress": attrs.get("in_progress") not in (False, None),
                    "features": int(attrs.get("supported_features") or 0),
                    "release_url": attrs.get("release_url"),
                }
            )
        return out

    def _backup(self) -> dict[str, Any]:
        """Sauvegardes natives de HA (intégration Backup), sinon add-on Google Drive Backup."""
        registry = er.async_get(self.hass)
        native: dict[str, str] = {}
        for entry in registry.entities.values():
            if entry.platform != "backup" or entry.domain != "sensor":
                continue
            for key in ("backup_manager_state", "last_successful_automatic_backup", "last_attempted_automatic_backup"):
                if entry.unique_id.endswith(key):
                    native[key] = entry.entity_id

        last_ok: datetime | None = None
        state_value: str | None = None
        if native:
            if (st := self.hass.states.get(native.get("last_successful_automatic_backup", ""))) is not None:
                last_ok = dt_util.parse_datetime(st.state) if st.state not in ("unknown", "unavailable") else None
            if (st := self.hass.states.get(native.get("backup_manager_state", ""))) is not None:
                state_value = st.state
        gdrive = self.hass.states.get("sensor.backup_state")
        if last_ok is None and gdrive is not None:
            last_ok = dt_util.parse_datetime(str(gdrive.attributes.get("last_backup") or ""))
            state_value = state_value or gdrive.state

        stale = last_ok is None or dt_util.utcnow() - last_ok > BACKUP_STALE_AFTER
        gstale = self.hass.states.get("binary_sensor.backups_stale")
        if gstale is not None and gstale.state == "on":
            stale = True
        return {
            "backup_state": state_value,
            "backups_stale": bool(stale) if (native or gdrive) else False,
            "last_backup": last_ok.isoformat() if last_ok else None,
        }

    def _cloud(self) -> dict[str, Any]:
        """Nabu Casa : statut, adresse *.ui.nabu.casa et fin d'abonnement (si connecté)."""
        result: dict[str, Any] = {"nabu_casa": None, "cloud_url": None, "nabu_casa_expiration": None}
        try:
            from homeassistant.components import cloud  # noqa: PLC0415

            if "cloud" not in self.hass.config.components or not cloud.async_is_logged_in(self.hass):
                return result
            result["nabu_casa"] = "connected" if cloud.async_is_connected(self.hass) else "disconnected"
            try:
                result["cloud_url"] = cloud.async_remote_ui_url(self.hass)
            except Exception:  # noqa: BLE001 - accès distant désactivé
                pass
            cloud_obj = self.hass.data.get("cloud")
            exp = getattr(cloud_obj, "expiration_date", None)
            if exp is not None:
                result["nabu_casa_expiration"] = exp.date().isoformat()
        except Exception as err:  # noqa: BLE001 - l'API cloud évolue : ne jamais bloquer le heartbeat
            _LOGGER.debug("Infos Nabu Casa indisponibles : %s", err)
        return result

    # ---------- assemblage ----------

    async def async_collect(self, boot: bool) -> dict[str, Any]:
        cpu, ram, disk = await self.hass.async_add_executor_job(self._system_metrics)
        cpu = _num(self.hass, SYSMON_CPU) if _num(self.hass, SYSMON_CPU) is not None else cpu
        ram = _num(self.hass, SYSMON_RAM) if _num(self.hass, SYSMON_RAM) is not None else ram
        disk = _num(self.hass, SYSMON_DISK) if _num(self.hass, SYSMON_DISK) is not None else disk
        updates = self._updates()
        cloud = self._cloud()
        return {
            "site_id": self.hass.config.location_name,
            "boot": boot,
            "agent": {"name": "ecopulse_connect", "version": self.agent_version},
            "ha_version": HA_VERSION,
            "os_version": self._os_version(),
            "cpu_percent": cpu,
            "ram_percent": ram,
            "disk_percent": disk,
            "pending_updates": [
                u["entity_id"] for u in updates if u["latest"] and u["installed"] and u["latest"] != u["installed"]
            ],
            "updates": updates,
            "remote_access": {
                "nabu_casa": cloud["nabu_casa"],
                "external_url": self.hass.config.external_url,
                "cloud_url": cloud["cloud_url"],
                "nabu_casa_expiration": cloud["nabu_casa_expiration"],
            },
            **self._backup(),
            "repairs_count": None,
            "timestamp": dt_util.now().isoformat(),
        }
