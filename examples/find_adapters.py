import pysoem

adapters = pysoem.find_adapters()   # returns a list of Adapter objects

for i, adapter in enumerate(adapters):
    print(f"{i}: name={adapter.name}, desc={adapter.desc}")