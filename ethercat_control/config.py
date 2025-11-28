"""Setup config models and loader."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Limits:
    max_rpm: int = 3000
    accel_rpm_s: int = 1000
    decel_rpm_s: int = 1000
    pos_min: Optional[int] = None
    pos_max: Optional[int] = None


@dataclass
class Homing:
    method: int = 35  # default: move to negative limit then offset
    offset: int = 0
    speed_fast: Optional[int] = None
    speed_slow: Optional[int] = None
    accel: Optional[int] = None


@dataclass
class ServoConfig:
    name: str
    alias: int
    position: int
    esi: Path
    limits: Limits = field(default_factory=Limits)
    homing: Homing = field(default_factory=Homing)
    mode: str = "pp"  # profile position (pp) or profile velocity (pv)


@dataclass
class SetupConfig:
    network_interface: str
    servos: List[ServoConfig]
    cycle_time_ms: int = 10
    description: str | None = None


def _dict_to_limits(data: Dict[str, Any]) -> Limits:
    return Limits(
        max_rpm=data.get("max_rpm", 3000),
        accel_rpm_s=data.get("accel_rpm_s", 1000),
        decel_rpm_s=data.get("decel_rpm_s", 1000),
        pos_min=data.get("pos_min"),
        pos_max=data.get("pos_max"),
    )


def _dict_to_homing(data: Dict[str, Any]) -> Homing:
    return Homing(
        method=data.get("method", 35),
        offset=data.get("offset", 0),
        speed_fast=data.get("speed_fast"),
        speed_slow=data.get("speed_slow"),
        accel=data.get("accel"),
    )


def _dict_to_servo(data: Dict[str, Any]) -> ServoConfig:
    missing = [k for k in ("name", "alias", "position", "esi") if k not in data]
    if missing:
        raise ValueError(f"Servo is missing required fields: {', '.join(missing)}")

    limits = _dict_to_limits(data.get("limits", {}))
    homing = _dict_to_homing(data.get("homing", {}))
    return ServoConfig(
        name=data["name"],
        alias=int(data["alias"]),
        position=int(data["position"]),
        esi=Path(data["esi"]).expanduser(),
        limits=limits,
        homing=homing,
        mode=data.get("mode", "pp"),
    )


def load_setup(setup_path: str | Path) -> SetupConfig:
    path = Path(setup_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Setup file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "network_interface" not in data or "servos" not in data:
        raise ValueError("Setup JSON must include 'network_interface' and 'servos'.")

    servos = [_dict_to_servo(item) for item in data["servos"]]
    return SetupConfig(
        network_interface=data["network_interface"],
        servos=servos,
        cycle_time_ms=int(data.get("cycle_time_ms", 10)),
        description=data.get("description"),
    )


def save_setup(config: SetupConfig, path: str | Path) -> Path:
    path = Path(path).expanduser().resolve()
    payload = {
        "description": config.description,
        "network_interface": config.network_interface,
        "cycle_time_ms": config.cycle_time_ms,
        "servos": [
            {
                "name": servo.name,
                "alias": servo.alias,
                "position": servo.position,
                "esi": str(servo.esi),
                "mode": servo.mode,
                "limits": {
                    "max_rpm": servo.limits.max_rpm,
                    "accel_rpm_s": servo.limits.accel_rpm_s,
                    "decel_rpm_s": servo.limits.decel_rpm_s,
                    "pos_min": servo.limits.pos_min,
                    "pos_max": servo.limits.pos_max,
                },
                "homing": {
                    "method": servo.homing.method,
                    "offset": servo.homing.offset,
                    "speed_fast": servo.homing.speed_fast,
                    "speed_slow": servo.homing.speed_slow,
                    "accel": servo.homing.accel,
                },
            }
            for servo in config.servos
        ],
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def default_setup_template() -> Dict[str, Any]:
    """Return a minimal template dictionary for a new setup file."""

    return {
        "description": "Example EtherCAT servo setup",
        "network_interface": "Ethernet 0",
        "cycle_time_ms": 10,
        "servos": [
            {
                "name": "servo1",
                "alias": 0,
                "position": 0,
                "esi": "ESI Example/LC10E V1.04.xml",
                "mode": "pp",
                "limits": {
                    "max_rpm": 3000,
                    "accel_rpm_s": 1000,
                    "decel_rpm_s": 1000,
                    "pos_min": -100000,
                    "pos_max": 100000,
                },
                "homing": {
                    "method": 35,
                    "offset": 0,
                    "speed_fast": 500,
                    "speed_slow": 100,
                    "accel": 1000,
                },
            }
        ],
    }
