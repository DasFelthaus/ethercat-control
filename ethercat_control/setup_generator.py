"""Interactive setup generator for EtherCAT servos."""

from pathlib import Path
from typing import Optional

from .config import Homing, Limits, ServoConfig, SetupConfig, default_setup_template, save_setup


def _prompt(text: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{text}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def _prompt_int(text: str, default: int) -> int:
    while True:
        raw = _prompt(text, str(default))
        try:
            return int(raw)
        except ValueError:
            print("Please enter a number.")


def interactive_setup(output_path: Optional[str | Path] = None) -> Path:
    template = default_setup_template()
    iface = _prompt("EtherCAT network interface name", template["network_interface"])
    servo_count = _prompt_int("How many servos?", 1)

    servos: list[ServoConfig] = []
    for i in range(servo_count):
        print(f"\nServo {i + 1}")
        name = _prompt("Name", f"servo{i + 1}")
        alias = _prompt_int("Alias", 0)
        position = _prompt_int("Position index", i)
        esi_path = _prompt("ESI file path", template["servos"][0]["esi"])

        max_rpm = _prompt_int("Max RPM", 3000)
        accel = _prompt_int("Acceleration (rpm/s)", 1000)
        decel = _prompt_int("Deceleration (rpm/s)", 1000)
        pos_min = _prompt_int("Position min (counts)", -100000)
        pos_max = _prompt_int("Position max (counts)", 100000)
        homing_method = _prompt_int("Homing method (CiA-402 code)", 35)
        homing_offset = _prompt_int("Homing offset (counts)", 0)

        limits = Limits(
            max_rpm=max_rpm,
            accel_rpm_s=accel,
            decel_rpm_s=decel,
            pos_min=pos_min,
            pos_max=pos_max,
        )
        homing = Homing(method=homing_method, offset=homing_offset)
        servos.append(
            ServoConfig(
                name=name,
                alias=alias,
                position=position,
                esi=Path(esi_path),
                limits=limits,
                homing=homing,
            )
        )

    setup = SetupConfig(network_interface=iface, servos=servos, cycle_time_ms=template["cycle_time_ms"])
    target = Path(output_path) if output_path else Path("setup.json")
    saved_path = save_setup(setup, target)
    print(f"\nSaved setup to {saved_path}")
    return saved_path


if __name__ == "__main__":
    interactive_setup()
