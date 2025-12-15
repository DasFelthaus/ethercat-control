"""LC10E cyclic synchronous velocity (CSV) demo using PySOEM.

This script:
  - Configures PDOs for CSV (controlword + mode of operation + target velocity).
  - Sets mode of operation (0x6060) to CSV (0x09).
  - Drives the LC10E to the requested speed (default 100 rpm) after CiA402
    state transitions (shutdown -> switched on -> operation enabled).

Derived from pysoem's basic_example style and LC10E V1.04 ESI mapping.

Usage:
    python drive_demo.py "<adapter name>" [--slave-index 0] [--rpm 100] [--duration 5]

Make sure:
  - The LC10E ESI is loaded on the master.
  - The drive has DC power and the motor is free/safe to rotate.
"""

import argparse
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PY_SOEM_PATH = REPO_ROOT / "pysoem-master"
if PY_SOEM_PATH.exists():
    sys.path.insert(0, str(PY_SOEM_PATH))

import pysoem


class LC10ECsvDemo:
    VENDOR_ID = 0x0000_0766
    PRODUCT_CODE = 0x0000_0402
    REVISION = 0x0000_0204

    CSV_MODE = 0x09
    COUNTS_PER_REV = 131_072  # 17-bit incremental encoder

    CONTROLWORD_FAULT_RESET = 0x0080
    CONTROLWORD_SHUTDOWN = 0x0006
    CONTROLWORD_SWITCH_ON = 0x0007
    CONTROLWORD_ENABLE = 0x000F

    STATE_MASK = 0x006F
    STATE_READY = 0x0021
    STATE_SWITCHED_ON = 0x0023
    STATE_OPERATION_ENABLED = 0x0027

    def __init__(self, iface: str, slave_index: int, target_rpm: float, duration: float):
        self.iface = iface
        self.slave_index = slave_index
        self.target_rpm = target_rpm
        self.duration = duration
        self.master = pysoem.Master()

    # ------------------------------------------------------------------ PDO setup
    def _map_pdos(self, slave):
        """Configure Rx/Tx PDOs for CSV (controlword + mode + target velocity)."""
        # Clear Rx assignment and map 0x1600: CW(16) + Modes(8) + TargetVel(32)
        slave.sdo_write(0x1C12, 0, struct.pack("B", 0))
        slave.sdo_write(0x1600, 0, struct.pack("B", 0))
        slave.sdo_write(0x1600, 1, struct.pack("<I", 0x6040_0010))  # Controlword
        slave.sdo_write(0x1600, 2, struct.pack("<I", 0x6060_0008))  # Modes of operation
        slave.sdo_write(0x1600, 3, struct.pack("<I", 0x60FF_0020))  # Target velocity
        slave.sdo_write(0x1600, 0, struct.pack("B", 3))
        slave.sdo_write(0x1C12, 1, struct.pack("<H", 0x1600))
        slave.sdo_write(0x1C12, 0, struct.pack("B", 1))

        # Clear Tx assignment and map 0x1A00: SW(16) + VelActual(32)
        slave.sdo_write(0x1C13, 0, struct.pack("B", 0))
        slave.sdo_write(0x1A00, 0, struct.pack("B", 0))
        slave.sdo_write(0x1A00, 1, struct.pack("<I", 0x6041_0010))  # Statusword
        slave.sdo_write(0x1A00, 2, struct.pack("<I", 0x606C_0020))  # Velocity actual value
        slave.sdo_write(0x1A00, 0, struct.pack("B", 2))
        slave.sdo_write(0x1C13, 1, struct.pack("<H", 0x1A00))
        slave.sdo_write(0x1C13, 0, struct.pack("B", 1))

        # Set CSV mode via SDO for good measure.
        slave.sdo_write(0x6060, 0, struct.pack("b", self.CSV_MODE))

    def _setup_slave(self, pos: int):
        slave = self.master.slaves[pos]
        self._map_pdos(slave)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _decode_state(status_word: int) -> str:
        state_val = status_word & 0x006F
        return {
            0x0000: "Not ready to switch on",
            0x0001: "Switch on disabled (step)",
            0x0003: "Switch on disabled / transition",
            0x0004: "Switch on disabled",
            0x0040: "Switch on disabled",
            0x0021: "Ready to switch on",
            0x0023: "Switched on",
            0x0027: "Operation enabled",
            0x0007: "Quick stop active",
            0x000F: "Fault reaction active",
            0x0008: "Fault",
        }.get(state_val, f"Unknown (0x{state_val:04x})")

    def _pack_outputs(self, slave, controlword: int, target_velocity: int) -> bytes:
        """Pack CW + Modes + Target velocity into the mapped RxPDO layout."""
        payload_len = len(slave.output)
        payload = bytearray(payload_len)

        struct.pack_into("<H", payload, 0, controlword)           # 0x6040
        struct.pack_into("<b", payload, 2, self.CSV_MODE)         # 0x6060
        struct.pack_into("<i", payload, 3, target_velocity)       # 0x60FF
        return bytes(payload)

    def _exchange_pd(self, controlword: int, target_velocity: int):
        """Write outputs, exchange PD, and parse inputs."""
        slave = self.master.slaves[self.slave_index]
        slave.output = self._pack_outputs(slave, controlword, target_velocity)

        self.master.send_processdata()
        self.master.receive_processdata(2_000)

        status_word = struct.unpack_from("<H", slave.input, 0)[0] if len(slave.input) >= 2 else 0
        vel_actual = struct.unpack_from("<i", slave.input, 2)[0] if len(slave.input) >= 6 else 0
        return status_word, vel_actual

    def _clear_faults(self) -> bool:
        for _ in range(50):
            status_word, _ = self._exchange_pd(self.CONTROLWORD_FAULT_RESET, 0)
            if (status_word & 0x0008) == 0:
                return True
            time.sleep(0.05)
        return False

    def _reach_state(self, expected_state: int, cw: int, vel: int, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status_word, _ = self._exchange_pd(cw, vel)
            if (status_word & self.STATE_MASK) == expected_state:
                return True
            print(
                f"  waiting for state 0x{expected_state:04x}; "
                f"status 0x{status_word:04x} ({self._decode_state(status_word)})"
            )
            time.sleep(0.05)
        return False

    def _enable_drive(self, target_velocity: int):
        if not self._clear_faults():
            raise RuntimeError("Drive is in fault and did not acknowledge reset (CW=0x0080).")

        if not self._reach_state(self.STATE_READY, self.CONTROLWORD_SHUTDOWN, 0):
            raise RuntimeError('Drive did not reach "Ready to switch on" (CW=0x0006).')

        if not self._reach_state(self.STATE_SWITCHED_ON, self.CONTROLWORD_SWITCH_ON, 0):
            raise RuntimeError('Drive did not reach "Switched on" (CW=0x0007).')

        if not self._reach_state(self.STATE_OPERATION_ENABLED, self.CONTROLWORD_ENABLE, target_velocity):
            raise RuntimeError('Drive did not reach "Operation enabled" (CW=0x000F).')

    def _hold_velocity(self, target_velocity: int):
        start = time.time()
        next_log = start
        while time.time() - start < self.duration:
            status_word, vel_actual = self._exchange_pd(self.CONTROLWORD_ENABLE, target_velocity)
            now = time.time()
            if now >= next_log:
                approx_rpm = vel_actual * 60.0 / self.COUNTS_PER_REV
                print(
                    f"Status 0x{status_word:04x} ({self._decode_state(status_word)}) | "
                    f"target {target_velocity} | actual raw {vel_actual} | ~rpm {approx_rpm:.1f}"
                )
                next_log = now + 0.5
            time.sleep(0.01)

        # Ramp down to zero target, then shutdown.
        self._exchange_pd(self.CONTROLWORD_ENABLE, 0)
        self._exchange_pd(self.CONTROLWORD_SHUTDOWN, 0)

    # ------------------------------------------------------------------ main run
    def run(self):
        self.master.open(self.iface)
        try:
            if self.master.config_init() <= self.slave_index:
                raise RuntimeError(f"No slave found at index {self.slave_index} (found {len(self.master.slaves)} total).")

            slave = self.master.slaves[self.slave_index]
            print(f"Found slave {self.slave_index}: {slave.name} man=0x{slave.man:08x} id=0x{slave.id:08x} rev=0x{slave.rev:08x}")
            if (slave.man, slave.id) != (self.VENDOR_ID, self.PRODUCT_CODE):
                print("Warning: Vendor/Product does not match LC10E ESI.")

            slave.config_func = self._setup_slave

            self.master.config_map()
            if self.master.state_check(pysoem.SAFEOP_STATE, timeout=50_000) != pysoem.SAFEOP_STATE:
                raise RuntimeError("Not all slaves reached SAFE_OP.")

            # Enter OP
            self.master.state = pysoem.OP_STATE
            self.master.send_processdata()
            self.master.receive_processdata(2_000)
            self.master.write_state()
            if self.master.state_check(pysoem.OP_STATE, timeout=50_000) != pysoem.OP_STATE:
                raise RuntimeError("Not all slaves reached OPERATIONAL.")

            slave = self.master.slaves[self.slave_index]
            print(f"Process data sizes -> outputs: {len(slave.output)} bytes, inputs: {len(slave.input)} bytes")

            target_velocity_command = int(round(self.target_rpm))
            print(f"Setting CSV mode (0x6060 = 0x09) and commanding {target_velocity_command} rpm for {self.duration}s...")

            self._enable_drive(target_velocity_command)
            self._hold_velocity(target_velocity_command)

        finally:
            self.master.state = pysoem.INIT_STATE
            self.master.write_state()
            self.master.close()


def main():
    parser = argparse.ArgumentParser(description="LC10E CSV mode demo (PySOEM).")
    parser.add_argument("iface", help='EtherCAT adapter name (e.g. "\\Device\\NPF_{...}")')
    parser.add_argument("--slave-index", type=int, default=0, help="Index of LC10E on the bus (default 0).")
    parser.add_argument("--rpm", type=float, default=10000.0, help="Target speed in rpm (0x60FF units).")
    parser.add_argument("--duration", type=float, default=60.0, help="Duration to hold speed before shutdown (s).")
    args = parser.parse_args()

    demo = LC10ECsvDemo(args.iface, args.slave_index, args.rpm, args.duration)
    try:
        demo.run()
    except Exception as exc:  # noqa: BLE001
        print(f"drive_demo failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
