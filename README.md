# PocketMicroLIB
PocketMicroLIB – Practical MicroPython libraries for LTE IoT devices using GNSS.

This library is designed primarily for MicroPython on Raspberry Pi Pico-class boards.
No Python package installation is required.
Simply copy the .py files to the root of the device.

- Files prefixed with `micro_` are generic infrastructure modules.
- Files without the prefix are device-specific implementations.

## License

This project is released under the **MIT License**.  
See the `LICENSE` file in the repository for details.

## Design Philosophy

- **No Python packages**
- **Flat file structure**
- **Optimized for MicroPython**
- **Designed for actual hardware operation**

All modules are intended to be copied directly into the root directory
of a MicroPython device (e.g. `/flash` on Raspberry Pi Pico-class boards).

No `pip`, no `sys.path` modification, no deep directory trees.

### Core Infrastructure Modules (`micro_*`)

- `micro_logger.py`  
  Simple and lightweight logging utilities designed for MicroPython environments.

- `micro_state.py`  
  Basic state and flag management helpers for embedded applications.

- `micro_storage_manager.py`  
  Utilities for file handling, log rotation, and persistent storage management.

- `micro_modem.py`  
  Generic base class for cellular modems, providing common AT command handling.

- `micro_socket.py`  
  Socket abstraction layer that hides modem-specific socket implementations.

- `micro_http_client.py`  
  Minimal HTTP client built on top of `micro_socket`, optimized for low-memory devices.

- `micro_zip.py`  
  Minimal ZIP creation utility suitable for MicroPython.

- `micro_unzip.py`  
  Minimal ZIP extraction utility for MicroPython environments.

---

### Hardware / Service Specific Modules

- `sdcard.py`  
  SPI-based SD card driver for MicroPython.

- `soracom_harvest_files.py`  
  Client implementation for SORACOM Harvest Files service.

- `ublox_sara_r.py`  
  Integrated driver for u-blox F9P GNSS receiver and SARA-R cellular modem.

- `state.py`  
  Lightweight state management helpers used by application logic.


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
