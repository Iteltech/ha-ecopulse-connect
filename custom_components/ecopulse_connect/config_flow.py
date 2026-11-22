"""Configuration via l'interface : URL du serveur + token du site."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .agent import EcoPulseAuthError, EcoPulseError, async_post
from .const import CONF_TOKEN, CONF_URL, DEFAULT_URL, DOMAIN, NAME


def _clean_token(value: str) -> str:
    value = value.strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else value


class EcoPulseConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_check(self, url: str, token: str) -> str | None:
        """Envoie un heartbeat minimal pour valider l'URL et le token."""
        try:
            await async_post(
                self.hass, url, token,
                {"type": "probe"},
            )
        except EcoPulseAuthError:
            return "invalid_auth"
        except EcoPulseError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip()
            token = _clean_token(user_input[CONF_TOKEN])
            if not url.startswith("https://"):
                errors[CONF_URL] = "https_required"
            elif (err := await self._async_check(url, token)) is not None:
                errors["base"] = err
            else:
                return self.async_create_entry(title=NAME, data={CONF_URL: url, CONF_TOKEN: token})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                    vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Changer le token (ex. régénéré dans le tableau de bord)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip()
            token = _clean_token(user_input[CONF_TOKEN])
            if not url.startswith("https://"):
                errors[CONF_URL] = "https_required"
            elif (err := await self._async_check(url, token)) is not None:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry, data={CONF_URL: url, CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=entry.data[CONF_URL]): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                    vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )
