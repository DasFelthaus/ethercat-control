# ethercat-control

Simple EtherCAT servo controller built on PySOEM with CiA-402 helpers.

## Quick start

1) Install (requires Python 3.9+):
```bash
pip install -e .
```

2) Generate a setup file (interactive):
```bash
python -m ethercat_control.setup_generator
```
You will be prompted for interface, servo aliases/positions, and ESI paths (e.g. `ESI Example/LC10E V1.04.xml`).

3) Use in code:
```python
import ethercat_control as ec

ctrl = ec.load("setup.json")  # loads, connects, configures to OP state
ctrl.enable_all()
ctrl.set_target_position("servo1", 10000)
ctrl.shutdown()
```

See `examples/basic_move.py` for a runnable sample.
