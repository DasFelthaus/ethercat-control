"""Print available network adapters and probe each one for attached slaves."""

import pysoem


def probe_adapter(adapter):
    """Open the adapter, run config_init, and report discovered slaves."""
    master = pysoem.Master()
    try:
        master.open(adapter.name)
        slave_count = master.config_init()
        if slave_count > 0:
            print(f"  Found {slave_count} slave(s):")
            for idx, slave in enumerate(master.slaves):
                print(
                    f"    [{idx}] {slave.name} "
                    f"(man=0x{slave.man:08x}, id=0x{slave.id:08x}, rev=0x{slave.rev:08x})"
                )
        else:
            print("  No slaves found.")
    except Exception as exc:  # noqa: BLE001
        print(f"  Probe failed: {exc}")
    finally:
        try:
            master.close()
        except Exception:
            pass


def main():
    adapters = pysoem.find_adapters()
    if not adapters:
        print("No adapters found.")
        return

    for i, adapter in enumerate(adapters):
        print(f"Adapter {i}")
        print(f"  {adapter.name}")
        print(f"  {adapter.desc}")
        probe_adapter(adapter)


if __name__ == "__main__":
    main()
