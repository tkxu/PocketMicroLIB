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
├─ README.md
└─ src/
   ├─ micro_http_client.py       # Lightweight HTTP client for MicroPython
   ├─ micro_logger.py            # Simple logging utilities
   ├─ micro_modem.py             # Generic modem base class
   ├─ micro_socket.py            # Socket abstraction layer
   ├─ micro_storage_manager.py   # File and storage management utilities
   ├─ micro_unzip.py             # Minimal unzip utility for MicroPython
   ├─ micro_zip.py               # Minimal zip utility for MicroPython
   ├─ sdcard.py                  # SD card driver (SPI-based)
   ├─ soracom_harvest_files.py   # SORACOM Harvest Files client
   ├─ state.py                   # Simple state management utilities
   └─ ublox_sara_r.py             # u-blox F9P GNSS + SARA-R modem integration
