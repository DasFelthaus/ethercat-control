"""Minimal example to move one or more servos using a setup file."""

from pathlib import Path

from ethercat_control import generate_setup, load


def main() -> None:
    setup_path = Path("setup.json")
    if not setup_path.exists():
        answer = input("No setup.json found. Generate one now? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            generate_setup(setup_path)
        else:
            print("Cannot proceed without a setup file.")
            return

    controller = load(setup_path, connect=True)
    controller.enable_all()

    # Move the first configured servo as a simple smoke test.
    first = next(iter(controller.servos.keys()))
    print(f"Moving {first} to +10000 counts, then back to 0.")
    controller.set_target_position(first, 10_000)
    input("Press Enter to move back to 0...")
    controller.set_target_position(first, 0)

    controller.shutdown()


if __name__ == "__main__":
    main()
