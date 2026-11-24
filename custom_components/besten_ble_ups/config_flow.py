"""Config flow: Bluetooth discovery, manual pick, and options."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .battery import BATTERY_TYPES, RATED_VOLTAGE, default_usable_pct
from .const import (
    CONF_BATTERY_AH,
    CONF_BATTERY_BMS,
    CONF_BATTERY_TYPE,
    CONF_BATTERY_USABLE_PCT,
    CONF_BATTERY_VOLTAGE,
    CONF_SCAN_INTERVAL,
    CONF_TYPICAL_LOAD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME_PREFIX,
    SERVICE_UUID,
)
from .device import UpsDevice
from .protocol import ProtocolError


_LOGGER = logging.getLogger(__name__)


def _has_name(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").startswith(NAME_PREFIX)


def _is_candidate(info: BluetoothServiceInfoBleak) -> bool:
    """The name only comes in the scan response (active scanning). Passive scanners
    (ESPHome/Shelly proxies) only see the FFE0 service UUID, so accept either."""
    return _has_name(info) or SERVICE_UUID in [u.lower() for u in info.service_uuids]


def _title(info: BluetoothServiceInfoBleak) -> str:
    return info.name if _has_name(info) else f"BestEn UPS {info.address.upper()[-5:]}"


class BestenUpsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def _async_validate(self, address: str) -> str | None:
        """Connect and read the status block, so we only add a real UPS (FFE0 is a common UUID).

        Returns an error key, or None if the device answered like the UPS."""
        ble_device = async_ble_device_from_address(self.hass, address, connectable=True)
        if ble_device is None:
            return "cannot_connect"
        device = UpsDevice(ble_device)
        try:
            await device.read_status()
        except ProtocolError as err:
            _LOGGER.debug("%s answered but not like the UPS: %s", address, err)
            return "not_supported"
        except (BleakError, TimeoutError, OSError) as err:
            _LOGGER.debug("%s: connection failed: %s", address, err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001 - e.g. no FFE1 characteristic on a different FFE0 device
            _LOGGER.debug("%s: unexpected error during validation", address, exc_info=True)
            return "not_supported"
        finally:
            await device.disconnect()
        return None

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        if not _is_candidate(discovery_info):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        name = _title(self._discovery)
        errors: dict[str, str] = {}
        if user_input is not None:
            address = self._discovery.address.upper()
            if (error := await self._async_validate(address)) is None:
                return self.async_create_entry(title=name, data={CONF_ADDRESS: address})
            errors["base"] = error
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders={"name": name}, errors=errors
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if (error := await self._async_validate(address)) is None:
                info = self._discovered.get(address)
                return self.async_create_entry(title=_title(info) if info else address, data={CONF_ADDRESS: address})
            errors["base"] = error

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            address = info.address.upper()
            if address not in configured and _is_candidate(info):
                self._discovered[address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        choices = {
            a: f"{i.name} ({a})" if _has_name(i) else f"Unnamed FFE0 device ({a}), possibly the UPS"
            for a, i in self._discovered.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return BestenUpsOptionsFlow()


def _number(min_: float, max_: float, step: float, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=min_, max=max_, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX)
    )


class BestenUpsOptionsFlow(OptionsFlow):
    """Step 1: update interval + battery type, capacity, BMS. Step 2: rated voltage + usable %."""

    def __init__(self) -> None:
        self._step1: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._step1 = user_input
            if float(user_input.get(CONF_BATTERY_AH) or 0) <= 0:
                return self.async_create_entry(data=user_input)  # no battery → no runtime estimate
            return await self.async_step_battery()
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                        _number(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, 1, "s"),
                    vol.Required(CONF_BATTERY_TYPE, default=opts.get(CONF_BATTERY_TYPE, "lifepo4")): SelectSelector(
                        SelectSelectorConfig(options=list(BATTERY_TYPES), translation_key="battery_type",
                                             mode=SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Required(CONF_BATTERY_AH, default=opts.get(CONF_BATTERY_AH, 0)): _number(0, 5000, 1, "Ah"),
                    vol.Required(CONF_BATTERY_BMS, default=opts.get(CONF_BATTERY_BMS, True)): BooleanSelector(),
                    vol.Required(CONF_TYPICAL_LOAD, default=opts.get(CONF_TYPICAL_LOAD, 0)): _number(0, 2000, 0.1, "W"),
                }
            ),
        )

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._step1, **user_input})
        opts = self.config_entry.options
        btype = self._step1[CONF_BATTERY_TYPE]
        bms = bool(self._step1.get(CONF_BATTERY_BMS, True))
        same_battery = opts.get(CONF_BATTERY_TYPE) == btype and opts.get(CONF_BATTERY_BMS, True) == bms
        voltage = opts.get(CONF_BATTERY_VOLTAGE) if same_battery and opts.get(CONF_BATTERY_VOLTAGE) else RATED_VOLTAGE[btype]
        usable = opts.get(CONF_BATTERY_USABLE_PCT) if same_battery and opts.get(CONF_BATTERY_USABLE_PCT) \
            else default_usable_pct(btype, bms)
        rated_wh = float(voltage) * float(self._step1[CONF_BATTERY_AH])
        return self.async_show_form(
            step_id="battery",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BATTERY_VOLTAGE, default=voltage): _number(6, 60, 0.1, "V"),
                    vol.Required(CONF_BATTERY_USABLE_PCT, default=usable): _number(10, 100, 1, "%"),
                }
            ),
            description_placeholders={
                "rated_wh": f"{rated_wh:.0f}",
                "usable_wh": f"{rated_wh * float(usable) / 100:.0f}",
                "default_pct": str(default_usable_pct(btype, bms)),
            },
        )
