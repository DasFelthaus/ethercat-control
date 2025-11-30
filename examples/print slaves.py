import sys

import pysoem


adapters = pysoem.find_adapters()

if not adapters:
    print("No adapters found")
    sys.exit(1)

for index, adapter in enumerate(adapters):
    master = pysoem.Master()
    try:
        master.open(adapter.name)
        if master.config_init() > 0:
            print(f"[{index}] Using adapter: {adapter.name} ({adapter.desc})")
            print(f"  Found {len(master.slaves)} slave(s)")
        else:
            continue
    except pysoem.SOEMError as exc:
        print(f"  Error while scanning: {exc}")
    finally:
        try:
            master.close()
        except Exception:
            pass
