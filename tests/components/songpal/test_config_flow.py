"""Test the songpal config flow."""

import copy
import dataclasses
from unittest.mock import patch

from homeassistant.components.songpal.const import (
    CONF_ENDPOINT,
    CONF_ON_ACTION,
    CONF_WOL,
    DOMAIN,
)
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_SSDP,
    SOURCE_USER,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_UDN,
    SsdpServiceInfo,
)

from . import (
    CONF_DATA,
    ENDPOINT,
    FRIENDLY_NAME,
    HOST,
    MODEL,
    _create_mocked_device,
    _patch_config_flow_device,
)

from tests.common import MockConfigEntry

UDN = "uuid:1234"

SSDP_DATA = SsdpServiceInfo(
    ssdp_usn="mock_usn",
    ssdp_st="mock_st",
    ssdp_location=f"http://{HOST}:52323/dmr.xml",
    upnp={
        ATTR_UPNP_UDN: UDN,
        ATTR_UPNP_FRIENDLY_NAME: FRIENDLY_NAME,
        "X_ScalarWebAPI_DeviceInfo": {
            "X_ScalarWebAPI_BaseURL": ENDPOINT,
            "X_ScalarWebAPI_ServiceList": {
                "X_ScalarWebAPI_ServiceType": ["guide", "system", "audio", "avContent"],
            },
        },
    },
)


def _flow_next(hass: HomeAssistant, flow_id: str) -> ConfigFlowResult:
    return next(
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["flow_id"] == flow_id
    )


def _patch_setup():
    return patch(
        "homeassistant.components.songpal.async_setup_entry",
        return_value=True,
    )


async def test_flow_ssdp(hass: HomeAssistant) -> None:
    """Test working ssdp flow."""
    mocked_device = _create_mocked_device()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=SSDP_DATA,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["description_placeholders"] == {
        CONF_NAME: FRIENDLY_NAME,
        CONF_HOST: HOST,
    }
    flow = _flow_next(hass, result["flow_id"])
    assert flow["context"]["unique_id"] == UDN

    with _patch_config_flow_device(mocked_device), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == FRIENDLY_NAME
        assert result["data"] == CONF_DATA

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_flow_ssdp_invalid(hass: HomeAssistant) -> None:
    """Test ssdp flow aborting when the device cannot be reached."""
    mocked_device = _create_mocked_device(True)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=SSDP_DATA,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    with _patch_config_flow_device(mocked_device):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "cannot_connect"


async def test_flow_user(hass: HomeAssistant) -> None:
    """Test working user initialized flow."""
    mocked_device = _create_mocked_device()

    with _patch_config_flow_device(mocked_device), _patch_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] is None
        _flow_next(hass, result["flow_id"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_ENDPOINT: ENDPOINT},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == MODEL
        assert result["data"] == {
            CONF_NAME: MODEL,
            CONF_ENDPOINT: ENDPOINT,
        }

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_called_once()


async def test_flow_user_host_only(hass: HomeAssistant) -> None:
    """Test user flow with only the host of the device given."""
    mocked_device = _create_mocked_device()

    with (
        _patch_config_flow_device(mocked_device) as device_cls,
        _patch_setup(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_ENDPOINT: HOST},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == {
            CONF_NAME: MODEL,
            CONF_ENDPOINT: ENDPOINT,
        }

    device_cls.assert_called_once_with(ENDPOINT)


async def test_flow_import(hass: HomeAssistant) -> None:
    """Test working import flow."""
    mocked_device = _create_mocked_device()

    with _patch_config_flow_device(mocked_device), _patch_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=CONF_DATA
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == FRIENDLY_NAME
        assert result["data"] == CONF_DATA

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_flow_import_with_options(hass: HomeAssistant) -> None:
    """Test import flow storing the options given in YAML."""
    mocked_device = _create_mocked_device()

    with _patch_config_flow_device(mocked_device), _patch_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                **CONF_DATA,
                CONF_ON_ACTION: "script.turn_on_soundbar",
                CONF_WOL: True,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == CONF_DATA

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.options == {
        CONF_ON_ACTION: "script.turn_on_soundbar",
        CONF_WOL: True,
    }


async def test_flow_import_without_name(hass: HomeAssistant) -> None:
    """Test import flow without optional name."""
    mocked_device = _create_mocked_device()

    with _patch_config_flow_device(mocked_device), _patch_setup():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_ENDPOINT: ENDPOINT}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == MODEL
        assert result["data"] == {CONF_NAME: MODEL, CONF_ENDPOINT: ENDPOINT}

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_called_once()


def _create_mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="uuid:0000",
        data=CONF_DATA,
    ).add_to_hass(hass)


async def test_ssdp_bravia(hass: HomeAssistant) -> None:
    """Test discovering a bravia TV."""
    ssdp_data = dataclasses.replace(SSDP_DATA)
    ssdp_data.upnp = copy.deepcopy(ssdp_data.upnp)
    ssdp_data.upnp["X_ScalarWebAPI_DeviceInfo"]["X_ScalarWebAPI_ServiceList"][
        "X_ScalarWebAPI_ServiceType"
    ].append("videoScreen")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=ssdp_data,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_songpal_device"


async def test_sddp_exist(hass: HomeAssistant) -> None:
    """Test discovering existed device."""
    _create_mock_config_entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_SSDP},
        data=SSDP_DATA,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_exist(hass: HomeAssistant) -> None:
    """Test user adding existed device."""
    mocked_device = _create_mocked_device()
    _create_mock_config_entry(hass)

    with _patch_config_flow_device(mocked_device):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=CONF_DATA
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_import_exist(hass: HomeAssistant) -> None:
    """Test importing existed device."""
    mocked_device = _create_mocked_device()
    _create_mock_config_entry(hass)

    with _patch_config_flow_device(mocked_device):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=CONF_DATA
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_user_invalid(hass: HomeAssistant) -> None:
    """Test using adding invalid config."""
    mocked_device = _create_mocked_device(True)
    _create_mock_config_entry(hass)

    with _patch_config_flow_device(mocked_device):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=CONF_DATA
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_import_invalid(hass: HomeAssistant) -> None:
    """Test importing invalid config."""
    mocked_device = _create_mocked_device(True)
    _create_mock_config_entry(hass)

    with _patch_config_flow_device(mocked_device):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=CONF_DATA
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "cannot_connect"

    mocked_device.get_supported_methods.assert_called_once()
    mocked_device.get_interface_information.assert_not_called()


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test the options flow."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ENDPOINT, data=CONF_DATA)
    entry.add_to_hass(hass)
    hass.states.async_set("script.turn_on_soundbar", "off")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ON_ACTION: "script.turn_on_soundbar", CONF_WOL: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_ON_ACTION: "script.turn_on_soundbar",
        CONF_WOL: True,
    }


async def test_options_flow_script_not_found(hass: HomeAssistant) -> None:
    """Test the options flow with a turn on script that does not exist."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ENDPOINT, data=CONF_DATA)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ON_ACTION: "script.missing"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ON_ACTION: "script_not_found"}
