"""Config flow to configure songpal component."""

import logging
from typing import TYPE_CHECKING, Any, override
from urllib.parse import ParseResult, urlparse

import probatio
from songpal import Device, SongpalException

from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_SSDP,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_UDN,
    SsdpServiceInfo,
)

from .const import CONF_ENDPOINT, CONF_ON_ACTION, CONF_WOL, DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = probatio.Schema({probatio.Required(CONF_ENDPOINT): str})


def _urlparse(endpoint: str) -> ParseResult:
    """Parse Endpoint URL."""
    parsed_url = urlparse(endpoint)
    # Support entering just the domain / IP address of the device
    if not parsed_url.scheme:
        parsed_url = parsed_url._replace(
            scheme="http", netloc=f"{parsed_url.path}:10000", path="/sony"
        )

    _LOGGER.debug(
        "Parsed endpoint URL: %s scheme %s", parsed_url.geturl(), parsed_url.scheme
    )
    return parsed_url


class SongpalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Songpal configuration flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self.endpoint: str | None = None
        self.host: str | None = None
        self.name: str | None = None

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SongpalOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SongpalOptionsFlowHandler()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        if user_input is not None:
            return await self.async_step_init(user_input)

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow start."""
        if self.source == SOURCE_SSDP:
            # Check if already configured
            self._async_abort_entries_match({CONF_ENDPOINT: self.endpoint})
            if user_input is None:
                if TYPE_CHECKING:
                    assert self.name is not None
                    assert self.host is not None
                return self.async_show_form(
                    step_id="init",
                    description_placeholders={
                        CONF_NAME: self.name,
                        CONF_HOST: self.host,
                    },
                )

        if TYPE_CHECKING:
            assert user_input is not None

        # Validate user form input
        name: str | None = user_input.get(CONF_NAME)
        endpoint = self.endpoint or _urlparse(user_input[CONF_ENDPOINT]).geturl()

        try:
            device = Device(endpoint)
            await device.get_supported_methods()
            name = name or self.name
            if name is None:
                interface_info = await device.get_interface_information()
                name = interface_info.modelName
        except SongpalException as ex:
            _LOGGER.debug("Connection failed: %s", ex)
            if self.source in (SOURCE_IMPORT, SOURCE_SSDP):
                return self.async_abort(reason="cannot_connect")
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    CONFIG_SCHEMA, user_input
                ),
                errors={"base": "cannot_connect"},
            )

        # Check if already configured
        self._async_abort_entries_match({CONF_ENDPOINT: endpoint})

        await self.async_set_unique_id(endpoint)
        self._abort_if_unique_id_configured()

        options = {}
        if self.source == SOURCE_IMPORT:
            # The options can also be given in the YAML configuration
            options = {
                key: user_input[key]
                for key in (CONF_ON_ACTION, CONF_WOL)
                if key in user_input
            }

        return self.async_create_entry(
            title=name,
            data={CONF_NAME: name, CONF_ENDPOINT: endpoint},
            options=options,
        )

    @override
    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a discovered Songpal device."""
        await self.async_set_unique_id(discovery_info.upnp[ATTR_UPNP_UDN])
        self._abort_if_unique_id_configured()

        _LOGGER.debug("Discovered: %s", discovery_info)

        self.name = discovery_info.upnp[ATTR_UPNP_FRIENDLY_NAME]
        hostname = urlparse(discovery_info.ssdp_location).hostname
        scalarweb_info = discovery_info.upnp["X_ScalarWebAPI_DeviceInfo"]
        self.endpoint = scalarweb_info["X_ScalarWebAPI_BaseURL"]
        service_types = scalarweb_info["X_ScalarWebAPI_ServiceList"][
            "X_ScalarWebAPI_ServiceType"
        ]

        # Ignore Bravia TVs
        if "videoScreen" in service_types or "video" in service_types:
            return self.async_abort(reason="not_songpal_device")

        if TYPE_CHECKING:
            # the hostname must be str because the ssdp_location is not bytes and
            # not a relative url
            assert isinstance(hostname, str)
        self.host = hostname

        self.context["title_placeholders"] = {
            CONF_NAME: self.name,
            CONF_HOST: self.host,
        }

        return await self.async_step_init()

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a config entry."""
        return await self.async_step_init(import_data)


class SongpalOptionsFlowHandler(OptionsFlowWithReload):
    """Handle Songpal options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Validate user form input
            on_action = user_input.get(CONF_ON_ACTION)
            if on_action is not None and on_action not in (
                self.hass.states.async_entity_ids("script")
            ):
                errors[CONF_ON_ACTION] = "script_not_found"

            if not errors:
                return self.async_create_entry(
                    data={
                        CONF_ON_ACTION: on_action,
                        CONF_WOL: user_input.get(CONF_WOL, False),
                    },
                )

        options_schema = probatio.Schema(
            {
                probatio.Optional(CONF_ON_ACTION): EntitySelector(
                    EntitySelectorConfig(domain="script")
                ),
                probatio.Optional(CONF_WOL, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, user_input or self.config_entry.options
            ),
            errors=errors,
        )
