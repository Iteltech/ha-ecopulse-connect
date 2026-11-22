"""Tests d'EcoPulse Connect."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ecopulse_connect.agent import EcoPulseAgent, EcoPulseAuthError
from custom_components.ecopulse_connect.const import CONF_TOKEN, CONF_URL, DEFAULT_URL, DOMAIN

URL = DEFAULT_URL


async def _setup(hass: HomeAssistant, aioclient_mock, response: dict | None = None) -> MockConfigEntry:
    aioclient_mock.post(URL, json=response or {"status": "ok", "command": None})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL, CONF_TOKEN: "secret"}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


def _update_entity(hass, installed="1.0", latest="1.1", features=1 | 2 | 8):
    hass.states.async_set(
        "update.demo", "on",
        {"installed_version": installed, "latest_version": latest, "supported_features": features, "title": "Demo"},
    )


async def test_config_flow_ok(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(URL, json={"status": "ok"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.ecopulse_connect.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "Bearer abc"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: URL, CONF_TOKEN: "abc"}
    assert aioclient_mock.mock_calls[0][2] == {"type": "probe"}
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer abc"


async def test_config_flow_errors(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(URL, status=401, json={"detail": "Unauthorized"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "x"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://insecure/x", CONF_TOKEN: "x"}
    )
    assert result["errors"] == {CONF_URL: "https_required"}


async def test_setup_sends_heartbeat_and_entities(hass: HomeAssistant, aioclient_mock) -> None:
    hass.config.location_name = "Maison Test"
    hass.config.external_url = "https://maison.duckdns.org"
    _update_entity(hass)
    entry = await _setup(hass, aioclient_mock)
    payload = aioclient_mock.mock_calls[-1][2]
    assert payload["site_id"] == "Maison Test"
    assert payload["agent"]["name"] == "ecopulse_connect"
    assert payload["agent"]["version"] == "0.1.0"
    assert payload["remote_access"]["external_url"] == "https://maison.duckdns.org"
    assert payload["pending_updates"] == ["update.demo"]
    assert payload["updates"][0]["features"] == 11
    assert payload["boot"] is False
    assert hass.states.get("binary_sensor.ecopulse_connect_server").state == "on"
    assert hass.states.get("sensor.ecopulse_connect_last_heartbeat").state not in ("unknown", "unavailable")

    n = aioclient_mock.call_count
    await hass.services.async_call("button", "press", {"entity_id": "button.ecopulse_connect_send_telemetry_now"}, blocking=True)
    assert aioclient_mock.call_count == n + 1

    diag = await __import__(
        "custom_components.ecopulse_connect.diagnostics", fromlist=["x"]
    ).async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"][CONF_TOKEN] == "**REDACTED**"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_server_down(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock, {"status": "ok"})
    aioclient_mock.clear_requests()
    aioclient_mock.post(URL, status=500, json={"detail": "boom"})
    await entry.runtime_data.async_heartbeat()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("binary_sensor.ecopulse_connect_server").state == "off"


def _results(aioclient_mock):
    return [c[2] for c in aioclient_mock.mock_calls if isinstance(c[2], dict) and c[2].get("type") == "result"]


async def test_update_command_executed(hass: HomeAssistant, aioclient_mock) -> None:
    _update_entity(hass)
    calls = async_mock_service(hass, "update", "install")
    cmd = {"id": "c1", "action": "update", "entity": "update.demo", "version": "1.1", "expires": int(time.time()) + 600}
    with patch("custom_components.ecopulse_connect.agent.asyncio.sleep"):
        await _setup(hass, aioclient_mock, {"status": "ok", "command": cmd})
        await hass.async_block_till_done(wait_background_tasks=True)
    assert calls[0].data == {"entity_id": "update.demo", "backup": True, "version": "1.1"}
    res = _results(aioclient_mock)
    assert res[0]["status"] == "started"
    assert res[-1]["status"] == "failed"  # la version installée n'a pas changé dans ce test
    assert hass.states.get("sensor.ecopulse_connect_last_command").state == "failed"


@pytest.mark.parametrize(
    ("cmd", "status", "msg"),
    [
        ({"action": "shell", "expires": 9e9}, "rejected", "action non autorisée"),
        ({"action": "restart", "expires": 1}, "rejected", "ordre expiré"),
        ({"action": "update", "entity": "update.nope", "version": "1", "expires": 9e9}, "rejected", "entité inconnue"),
        ({"action": "update", "entity": "update.demo", "version": "1.0", "expires": 9e9}, "done", "déjà installée"),
        ({"action": "update", "entity": "update.demo", "version": "2.0", "expires": 9e9, "_f": 1}, "rejected", "version disponible différente"),
        ({"action": "update", "entity": "update.demo", "version": "1.1", "expires": 9e9, "_f": 0}, "rejected", "installation non supportée"),
    ],
)
async def test_command_refused(hass: HomeAssistant, aioclient_mock, cmd, status, msg) -> None:
    _update_entity(hass, features=cmd.pop("_f", 11))
    calls = async_mock_service(hass, "update", "install")
    await _setup(hass, aioclient_mock, {"status": "ok", "command": {"id": "c2", **cmd}})
    await hass.async_block_till_done(wait_background_tasks=True)
    res = _results(aioclient_mock)
    assert len(res) == 1 and res[0]["status"] == status and res[0]["message"].startswith(msg)
    assert not calls


async def test_restart_command(hass: HomeAssistant, aioclient_mock) -> None:
    calls = async_mock_service(hass, "homeassistant", "restart")
    cmd = {"id": "c3", "action": "restart", "expires": int(time.time()) + 600}
    await _setup(hass, aioclient_mock, {"status": "ok", "command": cmd})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls) == 1
    assert [r["status"] for r in _results(aioclient_mock)] == ["started"]
