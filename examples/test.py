import pysoem

master = pysoem.Master()

master.open('Ethernet')

if master.config_init() > 0:
    device_foo = master.slaves[0]
    device_bar = master.slaves[1]
else:
    print('no device found')

master.close()