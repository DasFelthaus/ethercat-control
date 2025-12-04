"""PySOEM CiA-402 cyclic synchronous demo (CSP/CSV/CST).

Edit the config section below to pick a mode and tweak the step tables.
This talks directly to the first slave found on an interface that reports
connected devices during config_init(). Not intended for production use.
"""
from __future__ import annotations
import sys
import time
from typing import Any, Tuple

import pysoem

# --- User configuration -------------------------------------------------
MODE = "csp"  # choose between: "csp", "csv", "cst"
CYCLE_TIME = 0.01  # seconds between PDO send/receive calls
ADAPTER_HINT: str | None = None  # optional adapter.name to prefer

# Target tables: (setpoint, duration_seconds)
CSP_STEPS: list[Tuple[int, float]] = [
    (0, 0.5),
    (20000, 1.5),
    (-20000, 1.5),
    (0, 1.0),
]
CSV_STEPS: list[Tuple[int, float]] = [
    (400, 2.0),
    (-400, 2.0),
    (0, 1.0),
]
CST_STEPS: list[Tuple[int, float]] = [
    (150, 2.0),  # units are drive-specific (often 0.1% rated torque)
    (-150, 2.0),
    (0, 1.0),
]

# --- Internals ----------------------------------------------------------
MODE_TO_CODE = {"csp": 8, "csv": 9, "cst": 10}
CONTROLWORD_SEQUENCE = (
    (0x0006, 0x006F, 0x0021),  # ready to switch on
    (0x0007, 0x006F, 0x0023),  # switched on
    (0x000F, 0x006F, 0x0027),  # operation enabled
)


def pick_adapter() -> Any | None:
    adapters = pysoem.find_adapters()
    if not adapters:
        print("No network adapters found.")
        return None

    if ADAPTER_HINT:
        adapters = sorted(adapters, key=lambda a: 0 if a.name == ADAPTER_HINT else 1)

    for adapter in adapters:
        master = pysoem.Master()
        try:
            master.open(adapter.name)
            found = master.config_init()
            if found > 0:
                print(f"Using adapter: {adapter.name} ({adapter.desc}), slaves={found}")
                return adapter
            print(f"  {adapter.name} has no slaves attached.")
        except pysoem.SOEMError as exc:
            print(f"  Error scanning {adapter.name}: {exc}")
        finally:
            try:
                master.close()
            except Exception:
                pass
    return None


def write_int(slave: pysoem.Slave, index: int, subindex: int, value: int, size: int, signed: bool = False) -> None:
    slave.sdo_write(index, subindex, value.to_bytes(size, byteorder="little", signed=signed), True)


def read_u16(slave: pysoem.Slave, index: int, subindex: int = 0) -> int:
    return int.from_bytes(slave.sdo_read(index, subindex), byteorder="little", signed=False)


def wait_status(slave: pysoem.Slave, mask: int, value: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = read_u16(slave, 0x6041)
        if status & mask == value:
            return
        time.sleep(0.01)
    raise TimeoutError(f"Status 0x6041 did not reach mask {mask:#04x} == {value:#04x}")


def transition_to_op(master: pysoem.Master) -> None:
    if not master.config_init():
        raise RuntimeError("No EtherCAT slaves found after opening adapter.")

    master.config_map()
    master.state = pysoem.SAFEOP_STATE
    master.write_state()
    master.state_check(pysoem.SAFEOP_STATE, 2_000_000)

    master.state = pysoem.OP_STATE
    master.write_state()
    master.state_check(pysoem.OP_STATE, 2_000_000)


def enable_drive(slave: pysoem.Slave) -> None:
    for cw, mask, value in CONTROLWORD_SEQUENCE:
        write_int(slave, 0x6040, 0x00, cw, size=2, signed=False)
        wait_status(slave, mask=mask, value=value, timeout=2.0)


def set_mode(slave: pysoem.Slave, mode: str) -> None:
    if mode not in MODE_TO_CODE:
        raise ValueError(f"Unsupported mode '{mode}', choose from {list(MODE_TO_CODE)}")
    write_int(slave, 0x6060, 0x00, MODE_TO_CODE[mode], size=1, signed=True)
    # best-effort confirmation
    current = int.from_bytes(slave.sdo_read(0x6061, 0x00), byteorder="little", signed=True)
    if current != MODE_TO_CODE[mode]:
        print(f"Warning: mode display 0x6061 is {current}, expected {MODE_TO_CODE[mode]}")


def pump_process_data(master: pysoem.Master, duration: float) -> None:
    end = time.time() + duration
    while time.time() < end:
        master.send_processdata()
        master.receive_processdata(int(CYCLE_TIME * 1_000_000))
        time.sleep(CYCLE_TIME)


def run_csp(master: pysoem.Master, slave: pysoem.Slave) -> None:
    toggle = False
    for target_counts, dwell in CSP_STEPS:
        write_int(slave, 0x607A, 0x00, target_counts, size=4, signed=True)
        cw = 0x000F | (0x0010 if toggle else 0)
        write_int(slave, 0x6040, 0x00, cw, size=2, signed=False)
        toggle = not toggle
        pump_process_data(master, dwell)


def run_csv(master: pysoem.Master, slave: pysoem.Slave) -> None:
    for rpm, dwell in CSV_STEPS:
        write_int(slave, 0x60FF, 0x00, rpm, size=4, signed=True)
        write_int(slave, 0x6040, 0x00, 0x000F, size=2, signed=False)
        pump_process_data(master, dwell)


def run_cst(master: pysoem.Master, slave: pysoem.Slave) -> None:
    for torque, dwell in CST_STEPS:
        write_int(slave, 0x6071, 0x00, torque, size=2, signed=True)
        write_int(slave, 0x6040, 0x00, 0x000F, size=2, signed=False)
        pump_process_data(master, dwell)


def quick_stop(slave: pysoem.Slave) -> None:
    try:
        write_int(slave, 0x6040, 0x00, 0x000B, size=2, signed=False)
    except Exception:
        pass


def main() -> None:
    adapter = pick_adapter()
    if adapter is None:
        sys.exit(1)

    master = pysoem.Master()
    try:
        master.open(adapter.name)
        transition_to_op(master)
        slave = master.slaves[0]

        set_mode(slave, MODE)
        enable_drive(slave)

        print(f"Running {MODE.upper()} demo on slave 0...")
        if MODE == "csp":
            run_csp(master, slave)
        elif MODE == "csv":
            run_csv(master, slave)
        elif MODE == "cst":
            run_cst(master, slave)
        print("Demo complete. Issuing quick stop.")
        quick_stop(slave)
    except KeyboardInterrupt:
        print("Interrupted, issuing quick stop...")
        if master.slaves:
            quick_stop(master.slaves[0])
    finally:
        try:
            master.state = pysoem.INIT_STATE
            master.write_state()
        finally:
            master.close()


if __name__ == "__main__":
    main()
