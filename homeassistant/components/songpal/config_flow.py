"""Config flow to configure songpal component."""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import ParseResult, urlparse

from songpal import Device, SongpalException
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_SSDP
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ENDPOINT, CONF_ON_ACTION, CONF_WOL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _urlparse(endpoint: str) -> ParseResult:
    """Parse Endpoint URL."""
    parsed_url = urlparse(endpoint)
    # Support entering just the domain / IP address of the device
    if not parsed_url.scheme:
        parsed_url._replace(scheme="http")
        parsed_url._replace(netloc=f"{parsed_url.path}:10000")
        parsed_url._replace(path="sony")

    _LOGGER.debug("Parsed endpoint URL: %s", parsed_url.geturl())
    return parsed_url


class SongpalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Songpal configuration flow."""

    VERSION = 1
    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_ENDPOINT): str,
        }
    )

    def __init__(self) -> None:
        """Initialize the flow."""
        self.endpoint: Optional[str] = None
        self.host: Optional[str] = None
        self.name: Optional[str] = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SongpalOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        if user_input is not None:
            return await self.async_step_init(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=SongpalConfigFlow.CONFIG_SCHEMA,
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow start."""
        if self.context["source"] == SOURCE_SSDP:
            # Check if already configured
            self._async_abort_entries_match({CONF_ENDPOINT: self.endpoint})
            if user_input is None:
                return self.async_show_form(
                    step_id="init",
                    description_placeholders={
                        CONF_NAME: self.name,
                        CONF_HOST: self.host,
                    },
                )
            await self.async_set_unique_id(self.endpoint)
            self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_abort(reason="not_supported")

        # Validate user form input
        errors = {}

        name = user_input.get(CONF_NAME)
        parsed_url = _urlparse(str(user_input.get(CONF_ENDPOINT)))
        if self.host is None:
            self.host = parsed_url.hostname
        endpoint = self.endpoint or parsed_url.geturl()

        try:
            device = Device(endpoint)
            await device.get_supported_methods()
            name = name or self.name
            if name is None:
                interface_info = await device.get_interface_information()
                name = interface_info.modelName

        except SongpalException as ex:
            _LOGGER.debug("Connection failed: %s", ex)
            if self.context["source"] in {SOURCE_IMPORT, SOURCE_SSDP}:
                return self.async_abort(reason="cannot_connect")
            errors[CONF_ENDPOINT] = f"Connection failed: {ex}"
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=SongpalConfigFlow.CONFIG_SCHEMA,
                errors=errors,
            )

        # Check if already configured
        self._async_abort_entries_match({CONF_ENDPOINT: endpoint})

        await self.async_set_unique_id(endpoint)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=str(name),
            data={
                CONF_NAME: name,
                CONF_ENDPOINT: endpoint,
            },
        )

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        """Handle a discovered Songpal device."""
        await self.async_set_unique_id(discovery_info.upnp[ssdp.ATTR_UPNP_UDN])
        self._abort_if_unique_id_configured()

        _LOGGER.debug("Discovered: %s", discovery_info)

        self.name = discovery_info.upnp[ssdp.ATTR_UPNP_FRIENDLY_NAME]
        parsed_url = urlparse(discovery_info.ssdp_location)
        self.host = str(parsed_url.hostname)
        scalarweb_info = discovery_info.upnp["X_ScalarWebAPI_DeviceInfo"]
        self.endpoint = scalarweb_info["X_ScalarWebAPI_BaseURL"]
        service_types = scalarweb_info["X_ScalarWebAPI_ServiceList"][
            "X_ScalarWebAPI_ServiceType"
        ]

        # Ignore Bravia TVs
        if "videoScreen" in service_types:
            return self.async_abort(reason="not_songpal_device")

        self.context["title_placeholders"] = {
            CONF_NAME: self.name,
            CONF_HOST: self.host,
        }

        return await self.async_step_init()

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Import a config entry."""
        return await self.async_step_init(user_input)


class SongpalOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Songpal options."""

    VERSION = 1

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Validate user form input
            errors = {}

            name = user_input[CONF_NAME]
            on_action = user_input[CONF_ON_ACTION]
            if (
                on_action is not None
                and on_action not in self.hass.states.async_entity_ids("script")
            ):
                errors[CONF_ON_ACTION] = "Script not found."

            wol = bool(user_input[CONF_WOL])

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_NAME: name,
                        CONF_ON_ACTION: on_action,
                        CONF_WOL: wol,
                    },
                )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Optional(CONF_ON_ACTION, default=None): vol.In(
                    self.hass.states.async_entity_ids("script")
                ),
                vol.Optional(CONF_WOL, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, self.config_entry.options
            ),
            errors=errors,
        )
