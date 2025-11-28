"""Public API for ethercat_control.

This module exposes a small convenience wrapper to load a setup file and
instantiate the controller, plus a helper to generate a setup interactively.
"""

from pathlib import Path
from typing import Optional

from .config import SetupConfig, load_setup
from .controller import EtherCATController
from .setup_generator import interactive_setup


def load(setup_path: str | Path, connect: bool = True, prompt_on_missing: bool = True) -> EtherCATController:
    """Load a setup JSON and return an EtherCATController.

    If the file is missing and prompt_on_missing is True, the user will be
    asked whether to generate one interactively.
    """

    path = Path(setup_path)
    if not path.exists() and prompt_on_missing:
        answer = input(f"{path} not found. Generate it now? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            interactive_setup(path)
        else:
            raise FileNotFoundError(f"Setup file not found: {path}")

    config = load_setup(path)
    controller = EtherCATController(config)
    if connect:
        controller.connect()
    return controller


def generate_setup(output_path: Optional[str | Path] = None) -> Path:
    """Run the interactive setup generator and return the saved path."""

    return interactive_setup(output_path)


__all__ = ["load", "generate_setup", "SetupConfig", "EtherCATController"]
