"""Support for Songpal-enabled (Sony) media devices."""

import asyncio
from collections import OrderedDict
import logging
from typing import override
from urllib.parse import urlparse

from songpal import (
    ConnectChange,
    ContentChange,
    Device,
    PowerChange,
    SettingChange,
    SongpalException,
    VolumeChange,
)
from songpal.containers import Setting

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.wake_on_lan import (
    DOMAIN as WOL_DOMAIN,
    SERVICE_SEND_MAGIC_PACKET,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_BROADCAST_ADDRESS,
    CONF_MAC,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import CONF_ENDPOINT, CONF_ON_ACTION, CONF_WOL, DOMAIN, ERROR_REQUEST_RETRY

_LOGGER = logging.getLogger(__name__)

PARAM_NAME = "name"
PARAM_VALUE = "value"

INITIAL_RETRY_DELAY = 10


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up from legacy configuration file. Obsolete."""
    _LOGGER.error(
        "Configuring Songpal through media_player platform is no longer supported."
        " Convert to songpal platform or UI configuration"
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up songpal media player."""
    name = config_entry.data[CONF_NAME]
    endpoint = config_entry.data[CONF_ENDPOINT]
    mac = config_entry.data.get(CONF_MAC)
    on_action = config_entry.options.get(CONF_ON_ACTION)
    wol = config_entry.options.get(CONF_WOL, False)

    device = Device(endpoint)
    connected = True
    try:
        async with asyncio.timeout(
            10
        ):  # set timeout to avoid blocking the setup process
            await device.get_supported_methods()
    except (SongpalException, TimeoutError) as ex:
        if not (on_action or wol) or mac is None:
            _LOGGER.warning("[%s(%s)] Unable to connect", name, endpoint)
            _LOGGER.debug("Unable to get methods from songpal: %s", ex)
            raise PlatformNotReady from ex
        # The device can be turned on, so set it up as off and keep trying to
        # connect in the background
        _LOGGER.warning(
            "[%s(%s)] Unable to connect, assuming the device is off", name, endpoint
        )
        _LOGGER.debug("Unable to get methods from songpal: %s", ex)
        connected = False

    songpal_entity = SongpalEntity(name, device, on_action, wol, mac, connected)
    async_add_entities([songpal_entity], connected)


class SongpalEntity(MediaPlayerEntity):
    """Class representing a Songpal device."""

    _attr_should_poll = False
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self, name, device, on_action=None, wol=False, mac=None, connected=True
    ):
        """Initialize the Songpal device."""
        self._name = name
        self._dev = device
        self._sysinfo = None
        self._model = None
        self._on_action = on_action
        self._wol = wol
        self._mac = mac
        # Whether the supported methods have been fetched from the device,
        # the device cannot be used before that
        self._methods_loaded = connected

        self._state = False
        self._attr_available = False
        self._initialized = False
        self._delay = INITIAL_RETRY_DELAY

        self._volume_control = None
        self._volume_min = 0
        self._volume_max = 1
        self._volume = 0
        self._attr_is_volume_muted = False

        self._active_source = None
        self._sources = {}
        self._active_sound_mode = None
        self._sound_modes = {}

    def _reset_delay(self) -> None:
        """Reset delay after turn_on_action called to speed up reconnecting."""
        self._delay = INITIAL_RETRY_DELAY

    @override
    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await self.async_activate_websocket()

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await self._dev.stop_listen_notifications()

    async def _get_sound_modes_info(self):
        """Get available sound modes and the active one."""
        for settings in await self._dev.get_sound_settings():
            if settings.target == "soundField":
                break
        else:
            return None, {}

        if isinstance(settings, Setting):
            settings = [settings]

        sound_modes = {}
        active_sound_mode = None
        for setting in settings:
            cur = setting.currentValue
            for opt in setting.candidate:
                if not opt.isAvailable:
                    continue
                if opt.value == cur:
                    active_sound_mode = opt.value
                sound_modes[opt.value] = opt

        _LOGGER.debug("Got sound modes: %s", sound_modes)
        _LOGGER.debug("Active sound mode: %s", active_sound_mode)

        return active_sound_mode, sound_modes

    async def async_activate_websocket(self):
        """Activate websocket for listening if wanted."""
        _LOGGER.debug("Activating websocket connection")

        # Narrowed once here rather than at each call site: the entity is only
        # ever added from async_setup_entry, so the platform always has an entry.
        entry = self.platform.config_entry
        assert entry is not None

        async def _volume_changed(volume: VolumeChange):
            _LOGGER.debug("Volume changed: %s", volume)
            self._volume = volume.volume
            self._attr_is_volume_muted = volume.mute
            self.async_write_ha_state()

        async def _source_changed(content: ContentChange):
            _LOGGER.debug("Source changed: %s", content)
            if content.is_input:
                self._active_source = self._sources[content.uri]
                _LOGGER.debug("New active source: %s", self._active_source)
                self.async_write_ha_state()
            else:
                _LOGGER.debug("Got non-handled content change: %s", content)

        async def _setting_changed(setting: SettingChange):
            _LOGGER.debug("Setting changed: %s", setting)

            if setting.target == "soundField":
                self._active_sound_mode = setting.currentValue
                _LOGGER.debug("New active sound mode: %s", self._active_sound_mode)
                self.async_write_ha_state()
            else:
                _LOGGER.debug("Got non-handled setting change: %s", setting)

        async def _power_changed(power: PowerChange):
            _LOGGER.debug("Power changed: %s", power)
            self._state = power.status
            self.async_write_ha_state()

        async def _try_reconnect(connect: ConnectChange):
            _LOGGER.warning(
                "[%s(%s)] Got disconnected, trying to reconnect",
                self.name,
                self._dev.endpoint,
            )
            _LOGGER.debug("Disconnected: %s", connect.exception)
            self._state = False
            self._attr_available = False
            self.async_write_ha_state()

            await self._async_reconnect(entry)

        self._dev.on_notification(VolumeChange, _volume_changed)
        self._dev.on_notification(ContentChange, _source_changed)
        self._dev.on_notification(PowerChange, _power_changed)
        self._dev.on_notification(SettingChange, _setting_changed)
        self._dev.on_notification(ConnectChange, _try_reconnect)

        async def handle_stop(event):
            await self._dev.stop_listen_notifications()

        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, handle_stop)
        )

        if not self._methods_loaded:
            # The device was not reachable during setup
            entry.async_create_background_task(
                self.hass, self._async_reconnect(entry), "songpal-reconnect"
            )
            return

        entry.async_create_background_task(
            self.hass, self._dev.listen_notifications(), "songpal-listen-notifications"
        )

    async def _async_reconnect(self, entry: ConfigEntry) -> None:
        """Try to reconnect forever.

        A successful reconnect will initialize the websocket connection again.
        """
        self._reset_delay()
        while not self._attr_available:
            delay = self._delay
            _LOGGER.debug("Trying to reconnect in %s seconds", delay)
            # Sleep in short steps, so that _reset_delay() (called after
            # turning the device on) can cut the wait short
            remaining = delay
            while remaining > 0 and self._delay >= delay:
                await asyncio.sleep(min(remaining, INITIAL_RETRY_DELAY))
                remaining -= INITIAL_RETRY_DELAY

            try:
                await self._dev.get_supported_methods()
            except SongpalException as ex:
                _LOGGER.debug("Failed to reconnect: %s", ex)
                self._delay = min(2 * self._delay, 300)
            else:
                self._methods_loaded = True
                # We need to inform HA about the state in case we are coming
                # back from a disconnected state.
                await self.async_update_ha_state(force_refresh=True)

        entry.async_create_background_task(
            self.hass,
            self._dev.listen_notifications(),
            "songpal-listen-notifications",
        )
        _LOGGER.warning(
            "[%s(%s)] Connection reestablished", self.name, self._dev.endpoint
        )

    @callback
    def _async_store_mac(self) -> None:
        """Store the MAC address, so that the device can be set up while off."""
        entry = self.platform.config_entry
        assert entry is not None
        self._mac = self.unique_id
        if self._mac and entry.data.get(CONF_MAC) != self._mac:
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_MAC: self._mac}
            )

    async def _async_enable_wol(self) -> None:
        """Enable wake-on-lan on the device."""
        _LOGGER.debug("Enabling wake-on-lan for songpal device: %s", self._name)
        try:
            await self._dev.set_power_settings("wolMode", "on")
        except SongpalException as ex:
            _LOGGER.warning(
                "[%s(%s)] Unable to enable wake-on-lan: %s",
                self._name,
                self._dev.endpoint,
                ex,
            )

    @property
    @override
    def unique_id(self):
        """Return a unique ID."""
        if self._sysinfo is None:
            # Not connected yet, use the MAC address stored on a previous run
            return self._mac
        return self._sysinfo.macAddr or self._sysinfo.wirelessMacAddr

    @property
    @override
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""
        if self._sysinfo is None:
            if self._mac is None:
                return None
            # Not connected yet, the rest is known once the device is reachable
            return DeviceInfo(
                connections={(dr.CONNECTION_NETWORK_MAC, self._mac)},
                identifiers={(DOMAIN, self._mac)},
                manufacturer="Sony Corporation",
                name=self._name,
            )
        connections = set()
        if self._sysinfo.macAddr:
            connections.add((dr.CONNECTION_NETWORK_MAC, self._sysinfo.macAddr))
        if self._sysinfo.wirelessMacAddr:
            connections.add((dr.CONNECTION_NETWORK_MAC, self._sysinfo.wirelessMacAddr))
        return DeviceInfo(
            connections=connections,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Sony Corporation",
            model=self._model,
            name=self._name,
            sw_version=self._sysinfo.version,
        )

    @property
    @override
    def available(self) -> bool:
        """Return availability of the device."""
        if (self._on_action or self._wol) and not self._attr_available:
            # Report available when off, so that the device can be turned on
            _LOGGER.debug(
                "Device available is: %s but on_action set to %s and wol is %s"
                " - returning True",
                self._attr_available,
                self._on_action,
                self._wol,
            )
            return True
        return self._attr_available

    async def async_set_sound_setting(self, name, value):
        """Change a setting on the device."""
        _LOGGER.debug("Calling set_sound_setting with %s: %s", name, value)
        await self._dev.set_sound_settings(name, value)

    async def async_update(self) -> None:
        """Fetch updates from the device."""
        if not self._methods_loaded:
            # Not connected yet, see _async_reconnect
            return
        try:
            if self._sysinfo is None:
                self._sysinfo = await self._dev.get_system_info()
                self._async_store_mac()
                if self._wol:
                    await self._async_enable_wol()

            if self._model is None:
                interface_info = await self._dev.get_interface_information()
                self._model = interface_info.modelName

            volumes = await self._dev.get_volume_information()
            if not volumes:
                _LOGGER.error("Got no volume controls, bailing out")
                self._attr_available = False
                return

            if len(volumes) > 1:
                _LOGGER.debug("Got %s volume controls, using the first one", volumes)

            volume = volumes[0]
            _LOGGER.debug("Current volume: %s", volume)

            self._volume_max = volume.maxVolume
            self._volume_min = volume.minVolume
            self._volume = volume.volume
            self._volume_control = volume
            if self._volume_max:
                self._attr_volume_step = 1 / self._volume_max
            self._attr_is_volume_muted = self._volume_control.is_muted

            status = await self._dev.get_power()
            self._state = status.status
            _LOGGER.debug("Got state: %s", status)

            inputs = await self._dev.get_inputs()
            _LOGGER.debug("Got ins: %s", inputs)

            self._sources = OrderedDict()
            for input_ in inputs:
                self._sources[input_.uri] = input_
                if input_.active:
                    self._active_source = input_

            _LOGGER.debug("Active source: %s", self._active_source)

            (
                self._active_sound_mode,
                self._sound_modes,
            ) = await self._get_sound_modes_info()

            self._attr_available = True

        except SongpalException as ex:
            _LOGGER.error("Unable to update: %s", ex)
            self._attr_available = False

    @override
    async def async_select_source(self, source: str) -> None:
        """Select source."""
        for out in self._sources.values():
            if out.title == source:
                await out.activate()
                return

        _LOGGER.error("Unable to find output: %s", source)

    @property
    @override
    def source_list(self):
        """Return list of available sources."""
        return [src.title for src in self._sources.values()]

    @override
    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode."""
        for mode in self._sound_modes.values():
            if mode.title == sound_mode:
                await self._dev.set_sound_settings("soundField", mode.value)
                return

        _LOGGER.error("Unable to find sound mode: %s", sound_mode)

    @property
    @override
    def sound_mode_list(self) -> list[str] | None:
        """Return list of available sound modes.

        When active mode is None it means that sound mode is
        unavailable on the sound bar.
        Can be due to incompatible sound bar or the sound bar is in a mode that does not
        support sound mode changes.
        """
        if not self._active_sound_mode:
            return None
        return [sound_mode.title for sound_mode in self._sound_modes.values()]

    @property
    @override
    def state(self) -> MediaPlayerState:
        """Return current state."""
        if self._state:
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    @override
    def source(self):
        """Return currently active source."""
        # Avoid a KeyError when _active_source is not (yet) populated
        return getattr(self._active_source, "title", None)

    @property
    @override
    def sound_mode(self) -> str | None:
        """Return currently active sound_mode."""
        active_sound_mode = self._sound_modes.get(self._active_sound_mode)
        return active_sound_mode.title if active_sound_mode else None

    @property
    @override
    def volume_level(self):
        """Return volume level."""
        return self._volume / self._volume_max

    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        volume = int(volume * self._volume_max)
        _LOGGER.debug("Setting volume to %s", volume)
        return await self._volume_control.set_volume(volume)

    @override
    async def async_turn_on(self) -> None:
        """Turn the device on."""
        if not self._attr_available and (self._wol or self._on_action):
            # The device cannot be reached to turn it on, wake it up instead
            await self._async_wake_up()
            return
        try:
            await self._dev.set_power(True)
        except SongpalException as ex:
            if ex.code == ERROR_REQUEST_RETRY:
                _LOGGER.debug(
                    "Swallowing %s, the device might be already in the wanted state", ex
                )
                return
            raise

    async def _async_wake_up(self) -> None:
        """Wake up the device with wake-on-lan and the turn on action."""
        if self._wol:
            # Send the packet both to the broadcast address and directly to the
            # device, as which of them reaches the device depends on the network
            for data in (
                {CONF_MAC: self.unique_id},
                {
                    CONF_MAC: self.unique_id,
                    CONF_BROADCAST_ADDRESS: urlparse(self._dev.endpoint).hostname,
                },
            ):
                _LOGGER.debug(
                    "Sending wake-on-lan packet to songpal device %s data %r",
                    self._name,
                    data,
                )
                await self.hass.services.async_call(
                    WOL_DOMAIN, SERVICE_SEND_MAGIC_PACKET, data, context=self._context
                )
        if self._on_action:
            _LOGGER.debug(
                "Calling on_action %s for songpal device %s",
                self._on_action,
                self._name,
            )
            domain, service = self._on_action.split(".")
            await self.hass.services.async_call(domain, service, context=self._context)
        self._reset_delay()

    @override
    async def async_turn_off(self) -> None:
        """Turn the device off."""
        try:
            await self._dev.set_power(False)
        except SongpalException as ex:
            if ex.code == ERROR_REQUEST_RETRY:
                _LOGGER.debug(
                    "Swallowing %s, the device might be already in the wanted state", ex
                )
                return
            raise

    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the device."""
        _LOGGER.debug("Set mute: %s", mute)
        return await self._volume_control.set_mute(mute)
