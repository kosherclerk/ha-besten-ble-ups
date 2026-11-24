"""BLE transport for the UPS. No Home Assistant imports (only bleak + bleak-retry-connector)."""
from __future__ import annotations

import asyncio
import logging

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .protocol import (
    CONFIG_BASE,
    CONFIG_COUNT,
    MAX_REGS_PER_REQUEST,
    MODBUS_CHAR_UUID,
    STATUS_BASE,
    STATUS_COUNT,
    ProtocolError,
    UpsConfig,
    UpsStatus,
    build_read,
    decode_config,
    decode_status,
    parse_read_reply,
)

_LOGGER = logging.getLogger(__name__)

REPLY_POLL_INTERVAL = 0.06
REPLY_TIMEOUT = 1.5


class UpsDevice:
    """Keeps one BLE connection to the UPS and performs Modbus reads over it.

    The UPS accepts only one BLE central at a time; while Home Assistant is connected,
    phones or other tools cannot connect.
    """

    def __init__(self, ble_device: BLEDevice) -> None:
        self._ble_device = ble_device
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()

    @property
    def address(self) -> str:
        return self._ble_device.address

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the device handle (e.g. when a different adapter/proxy sees it better)."""
        self._ble_device = ble_device

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client and self._client.is_connected:
            return self._client
        _LOGGER.debug("%s: connecting", self.address)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self._ble_device,
            self._ble_device.name or self.address,
            disconnected_callback=self._on_disconnect,
            max_attempts=3,
        )
        return self._client

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("%s: disconnected", self.address)

    async def _transfer(self, client, frame: bytes) -> bytes:
        await client.write_gatt_char(MODBUS_CHAR_UUID, frame, response=True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + REPLY_TIMEOUT
        while loop.time() < deadline:
            await asyncio.sleep(REPLY_POLL_INTERVAL)
            reply = bytes(await client.read_gatt_char(MODBUS_CHAR_UUID))
            if reply:
                return reply
        raise ProtocolError("no reply from UPS")

    async def read_registers(self, register: int, count: int) -> list[int]:
        async with self._lock:
            client = await self._ensure_connected()
            values: list[int] = []
            try:
                while count > 0:
                    n = min(count, MAX_REGS_PER_REQUEST)
                    reply = await self._transfer(client, build_read(register, n))
                    values += parse_read_reply(reply, n)
                    register += n
                    count -= n
            except (BleakError, ProtocolError, asyncio.TimeoutError):
                await self._disconnect_locked()
                raise
            return values

    async def read_status(self) -> UpsStatus:
        return decode_status(await self.read_registers(STATUS_BASE, STATUS_COUNT))

    async def read_config(self) -> UpsConfig:
        return decode_config(await self.read_registers(CONFIG_BASE, CONFIG_COUNT))

    async def _disconnect_locked(self) -> None:
        client, self._client = self._client, None
        if client:
            try:
                await client.disconnect()
            except BleakError:
                pass

    async def disconnect(self) -> None:
        async with self._lock:
            await self._disconnect_locked()
