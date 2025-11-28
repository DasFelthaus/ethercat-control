"""PySOEM-based EtherCAT CiA-402 controller."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

import pysoem

from .config import Limits, ServoConfig, SetupConfig
from .esi import ensure_esies_exist


MODE_PROFILE_POSITION = 1
MODE_PROFILE_VELOCITY = 3
MODE_HOMING = 6


@dataclass
class ServoHandle:
    config: ServoConfig
    slave: pysoem.Slave


class EtherCATController:
    def __init__(self, setup: SetupConfig):
        self.setup = setup
        self.master: pysoem.Master | None = None
        self.servos: Dict[str, ServoHandle] = {}

    def connect(self) -> None:
        """Open the master, configure slaves, and map servo handles."""

        ensure_esies_exist([servo.esi for servo in self.setup.servos])
        self.master = pysoem.Master()
        self.master.open(self.setup.network_interface)

        if not self.master.config_init():
            raise RuntimeError("No EtherCAT slaves found.")

        self.master.config_map()
        self.master.state = pysoem.SAFEOP_STATE
        self.master.write_state()
        self.master.state_check(pysoem.SAFEOP_STATE, 5_000_000)

        # Map servo configs to discovered slaves by alias and position.
        for cfg in self.setup.servos:
            slave = self._find_slave(cfg.alias, cfg.position)
            self.servos[cfg.name] = ServoHandle(cfg, slave)

        # Move network to operational.
        self.master.state = pysoem.OP_STATE
        self.master.write_state()
        self.master.state_check(pysoem.OP_STATE, 5_000_000)

    def shutdown(self) -> None:
        if self.master:
            self.master.close()
            self.master = None

    # -- CiA-402 helpers -------------------------------------------------
    def enable_all(self) -> None:
        for name in self.servos:
            self.enable_drive(name)

    def enable_drive(self, name: str) -> None:
        servo = self._servo(name)
        # Shutdown -> Switch on -> Enable operation
        sequence = (
            (0x0006, 0x004F, 0x0021),  # ready to switch on
            (0x0007, 0x006F, 0x0023),  # switched on
            (0x000F, 0x006F, 0x0027),  # operation enabled
        )
        for cw, mask, value in sequence:
            self._write_controlword(servo, cw)
            self._wait_status(servo, mask=mask, value=value, timeout=1.0)

    def quick_stop(self, name: str) -> None:
        servo = self._servo(name)
        self._write_controlword(servo, 0x000B)

    def set_target_position(self, name: str, position_counts: int) -> None:
        """Set a new position setpoint (profile position mode)."""

        servo = self._servo(name)
        cfg = servo.config
        self._set_mode(servo, MODE_PROFILE_POSITION)
        self._write_profile_limits(servo, cfg.limits)

        # Set target and trigger new set-point
        self._write_sdo_int(servo, 0x607A, 0x00, position_counts, size=4, signed=True)
        # Set-point bit (bit4) toggle sequence: set, then clear
        self._write_controlword(servo, 0x003F)
        self._write_controlword(servo, 0x001F)

    def set_target_velocity(self, name: str, velocity_rpm: int) -> None:
        """Set a new velocity setpoint (profile velocity mode)."""

        servo = self._servo(name)
        cfg = servo.config
        self._set_mode(servo, MODE_PROFILE_VELOCITY)
        self._write_profile_limits(servo, cfg.limits)
        self._write_sdo_int(servo, 0x60FF, 0x00, velocity_rpm, size=4, signed=True)
        self._write_controlword(servo, 0x000F)

    def home(self, name: str) -> None:
        """Start a homing sequence using configured method and speeds."""

        servo = self._servo(name)
        homing = servo.config.homing

        self._set_mode(servo, MODE_HOMING)
        self._write_sdo_int(servo, 0x6098, 0x00, homing.method, size=1, signed=False)
        if homing.speed_fast is not None:
            self._write_sdo_int(servo, 0x6099, 0x01, homing.speed_fast, size=4, signed=False)
        if homing.speed_slow is not None:
            self._write_sdo_int(servo, 0x6099, 0x02, homing.speed_slow, size=4, signed=False)
        if homing.accel is not None:
            self._write_sdo_int(servo, 0x609A, 0x00, homing.accel, size=4, signed=False)
        self._write_controlword(servo, 0x001F)  # start homing
        # Wait for homing attained (bit 12) and not error (bit 13)
        self._wait_status(servo, mask=0x3000, value=0x1000, timeout=10.0)

    # -- Internal helpers ------------------------------------------------
    def _write_profile_limits(self, servo: ServoHandle, limits: Limits) -> None:
        self._write_sdo_int(servo, 0x6081, 0x00, limits.max_rpm, size=4, signed=False)
        self._write_sdo_int(servo, 0x6083, 0x00, limits.accel_rpm_s, size=4, signed=False)
        self._write_sdo_int(servo, 0x6084, 0x00, limits.decel_rpm_s, size=4, signed=False)

    def _write_controlword(self, servo: ServoHandle, value: int) -> None:
        self._write_sdo_int(servo, 0x6040, 0x00, value, size=2, signed=False)

    def _set_mode(self, servo: ServoHandle, mode: int) -> None:
        self._write_sdo_int(servo, 0x6060, 0x00, mode, size=1, signed=True)

    def _wait_status(self, servo: ServoHandle, mask: int, value: int, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status_bytes = servo.slave.sdo_read(0x6041, 0x00)
            status = int.from_bytes(status_bytes, byteorder="little", signed=False)
            if (status & mask) == value:
                return
            time.sleep(0.01)
        raise TimeoutError(f"Timeout waiting for status mask {mask:#x} == {value:#x}")

    def _servo(self, name: str) -> ServoHandle:
        if name not in self.servos:
            raise KeyError(f"Servo '{name}' not configured.")
        return self.servos[name]

    def _find_slave(self, alias: int, position: int) -> pysoem.Slave:
        for slave in self.master.slaves:
            if slave.alias == alias and slave.position == position:
                return slave
        raise RuntimeError(f"No slave found with alias={alias} position={position}")

    def _write_sdo_int(
        self, servo: ServoHandle, index: int, subindex: int, value: int, size: int = 4, signed: bool = False
    ) -> None:
        data = value.to_bytes(size, byteorder="little", signed=signed)
        servo.slave.sdo_write(index, subindex, data, True)
