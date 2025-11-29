import pysoem

master = pysoem.Master()

# Example: use the first adapter (index 0) – adjust as needed
adapters = pysoem.find_adapters()
ec_ifname = adapters[-1].name   # or choose by description

print("Using adapter:", ec_ifname)
master.open(ec_ifname)

if master.config_init() > 0:
    print(f"Found {len(master.slaves)} slaves")
else:
    print("No EtherCAT slaves found")

master.close()
