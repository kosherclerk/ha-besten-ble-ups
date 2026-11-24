"""Config flow: Bluetooth discovery, manual pick, and options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME_PREFIX,
)


class BestenUpsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        name = self._discovery.name or self._discovery.address
        if user_input is not None:
            return self.async_create_entry(title=name, data={CONF_ADDRESS: self._discovery.address.upper()})
        self._set_confirm_only()
        return self.async_show_form(step_id="bluetooth_confirm", description_placeholders={"name": name})

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._discovered.get(address, address), data={CONF_ADDRESS: address})

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            address = info.address.upper()
            if address in configured or not (info.name or "").startswith(NAME_PREFIX):
                continue
            self._discovered[address] = info.name
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In({a: f"{n} ({a})" for a, n in self._discovered.items()})}
            ),
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
