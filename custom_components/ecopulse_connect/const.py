"""Constantes d'EcoPulse Connect."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "ecopulse_connect"
NAME = "EcoPulse Connect"

CONF_URL = "url"
CONF_TOKEN = "token"
DEFAULT_URL = "https://wiztech-ha.duckdns.org/telemetry/heartbeat"

HEARTBEAT_INTERVAL = timedelta(minutes=15)
HTTP_TIMEOUT = 30

# Liste fixe des actions exécutables à distance : rien d'autre n'est possible.
ACTION_UPDATE = "update"
ACTION_RESTART = "restart"
ACTION_REBOOT = "reboot"
ALLOWED_ACTIONS = (ACTION_UPDATE, ACTION_RESTART, ACTION_REBOOT)

# UpdateEntityFeature (valeurs stables de HA)
FEATURE_INSTALL = 1
FEATURE_SPECIFIC_VERSION = 2
FEATURE_BACKUP = 8

# Une sauvegarde automatique plus vieille que ceci est signalée « en retard »
BACKUP_STALE_AFTER = timedelta(hours=48)

SIGNAL_UPDATED = f"{DOMAIN}_updated_{{}}"
