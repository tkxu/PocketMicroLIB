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

- `micro_storage_manager.py`  
  Utilities for file handling, log rotation, and persistent storage management.

- `micro_modem.py`  
  Generic base class for cellular modems, providing common AT command handling.

- `micro_socket.py`  
  Socket abstraction layer that hides modem-specific socket implementations.

- `micro_http_client.py`  
  Minimal HTTP client built optimized for low-memory devices.

- `micro_zip.py`  
  Minimal ZIP creation utility for MicroPython environments.

- `micro_unzip.py`  
  Minimal ZIP extraction utility for MicroPython environments.

---

### Hardware / Service Specific Modules
- `boot.py`  
  
- `board_rpi_pico2.py`  
  Board-specific initialization and utilities for Raspberry Pi Pico 2 (RP2040).
  Handles SD card mounting, pin mapping, GPIO/ADC setup, power control, and board-level helper functions.
  
- `sdcard.py`  
  SPI-based SD card driver for MicroPython.

- `soracom_harvest_files.py`  
  Client implementation for SORACOM Harvest Files service.

- `ublox_sara_r.py`  
  Integrated driver for u-blox SARA-R cellular modem.


```text
PocketMicroLIB/
├─ README.md
├─ LICENSE.md
└─ src/
   ├─ board_rpi_pico2.py        
   ├─ boot.py       
   ├─ micro_http_client.py       # Lightweight HTTP client for MicroPython
   ├─ micro_logger.py            # Simple logging utilities
   ├─ micro_modem.py             # Generic modem base class
   ├─ micro_socket.py            # Socket abstraction layer
   ├─ micro_storage_manager.py   # File and storage management utilities
   ├─ micro_unzip.py             # Minimal unzip utility for MicroPython
   ├─ micro_zip.py               # Minimal zip utility for MicroPython
   ├─ sdcard.py                  # SD card driver (SPI-based)
   ├─ soracom_harvest_files.py   # SORACOM Harvest Files client
   └─ ublox_sara_r.py             # u-blox F9P GNSS + SARA-R modem integration
