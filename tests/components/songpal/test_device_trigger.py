"""Test songpal device triggers."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from pytest_unordered import unordered
from songpal import ConnectChange, SongpalException

from homeassistant.components import automation, media_player
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.songpal.const import DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_MAC,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from . import (
    CONF_DATA,
    ENTITY_ID,
    MAC,
    _create_mocked_device,
    _patch_media_player_device,
)

from tests.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_get_device_automations,
)


async def _setup_device(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> tuple[MagicMock, str]:
    """Set up a songpal device, return the mocked device and the device id."""
    mocked_device = _create_mocked_device()
    entry = MockConfigEntry(domain=DOMAIN, data=CONF_DATA)
    entry.add_to_hass(hass)

    with _patch_media_player_device(mocked_device):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, MAC), entry.entry_id
    )
    assert device is not None
    return mocked_device, device.id


async def _setup_turn_on_automation(hass: HomeAssistant, device_id: str) -> None:
    """Set up an automation triggered by the turn on request."""
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device_id,
                        "type": "turn_on",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "{{ trigger.device_id }}",
                            "id": "{{ trigger.id }}",
                        },
                    },
                }
            ]
        },
    )


async def _turn_on(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        media_player.DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _wait(hass: HomeAssistant, seconds: int) -> None:
    """Let the reconnect delay pass."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_get_triggers(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Test we get the expected triggers."""
    _, device_id = await _setup_device(hass, device_registry)

    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "turn_on",
            "device_id": device_id,
            "metadata": {},
        },
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_id
    )
    triggers = [trigger for trigger in triggers if trigger["domain"] == DOMAIN]
    assert triggers == unordered(expected_triggers)


async def test_turn_on_reachable(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    service_calls: list[ServiceCall],
) -> None:
    """Test a reachable device is turned on directly, without the trigger."""
    mocked_device, device_id = await _setup_device(hass, device_registry)
    await _setup_turn_on_automation(hass, device_id)

    await _turn_on(hass)

    mocked_device.set_power.assert_called_once_with(True)
    assert [call.domain for call in service_calls] == [media_player.DOMAIN]


async def test_turn_on_unreachable(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    service_calls: list[ServiceCall],
) -> None:
    """Test the trigger turns on an unreachable device, and it reconnects soon."""
    mocked_device, device_id = await _setup_device(hass, device_registry)
    await _setup_turn_on_automation(hass, device_id)
    type(mocked_device).get_supported_methods = AsyncMock(
        side_effect=[SongpalException(""), SongpalException(""), None]
    )
    connect_change = MagicMock()
    connect_change.exception = "disconnected"
    reconnect = asyncio.create_task(
        mocked_device.notification_callbacks[ConnectChange](connect_change)
    )
    await hass.async_block_till_done()

    # Shown as off rather than unavailable, as it can be turned on
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    # Turning off does nothing, as the device is off already
    await hass.services.async_call(
        media_player.DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    mocked_device.set_power.assert_not_called()

    # Reconnecting fails while the device is off, after 10 and 20 seconds
    await _wait(hass, 11)
    await _wait(hass, 21)
    assert mocked_device.get_supported_methods.call_count == 2
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await _turn_on(hass)

    mocked_device.set_power.assert_not_called()
    assert len(service_calls) == 3
    assert service_calls[2].domain == "test"
    assert service_calls[2].service == "automation"
    assert service_calls[2].data["some"] == device_id
    assert service_calls[2].data["id"] == 0

    # The next attempt is after 10 seconds again instead of 40 seconds
    await _wait(hass, 11)
    assert mocked_device.get_supported_methods.call_count == 3
    await reconnect
    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_unreachable_without_trigger(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Test an unreachable device is unavailable without a turn on trigger."""
    mocked_device, _ = await _setup_device(hass, device_registry)
    type(mocked_device).get_supported_methods = AsyncMock(side_effect=[None])
    connect_change = MagicMock()
    connect_change.exception = "disconnected"
    reconnect = asyncio.create_task(
        mocked_device.notification_callbacks[ConnectChange](connect_change)
    )
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    await _wait(hass, 11)
    await reconnect
    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_turn_on_unreachable_at_startup(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    service_calls: list[ServiceCall],
) -> None:
    """Test the trigger turns on a device that was unreachable during setup."""
    mocked_device = _create_mocked_device(throw_exception=True)
    entry = MockConfigEntry(domain=DOMAIN, data={**CONF_DATA, CONF_MAC: MAC})
    entry.add_to_hass(hass)

    with _patch_media_player_device(mocked_device):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, MAC), entry.entry_id
    )
    assert device is not None
    await _setup_turn_on_automation(hass, device.id)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await _turn_on(hass)

    mocked_device.set_power.assert_not_called()
    assert len(service_calls) == 2
    assert service_calls[1].domain == "test"
    assert service_calls[1].data["some"] == device.id
