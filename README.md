# PocketMicroLIB
PocketMicroLIB – Practical MicroPython libraries for GNSS &amp; LTE IoT devices

This library is designed primarily for MicroPython on Raspberry Pi Pico-class boards.
No Python package installation is required.
Simply copy the .py files to the root of the device.

- Files prefixed with `micro_` are generic infrastructure modules.
- Files without the prefix are device-specific implementations.

## Design Philosophy

- **No Python packages**
- **Flat file structure**
- **Optimized for MicroPython**
- **Designed for actual hardware operation**

All modules are intended to be copied directly into the root directory
of a MicroPython device (e.g. `/flash` on Raspberry Pi Pico-class boards).

No `pip`, no `sys.path` modification, no deep directory trees.

```text
PocketMicroLIB/
├─ README.md
├─ LICENSE
├─ src/
   └─ micro_logger.py
   ├─ micro_state.py
   ├─ micro_storage.py
   ├─ micro_modem.py
   ├─ micro_http_client.py
   ├─ micro_socket_client.py
