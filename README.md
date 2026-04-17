日本語版はこちら → [README_ja.md](README_ja.md)

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




# ublox_sara_r.py SARA-R410 / R510 MicroPython Driver

A robust MicroPython driver for **u-blox SARA-R410 and R510 LTE modules**, designed for **embedded systems (e.g., Raspberry Pi Pico)**.

This implementation focuses on **stability**, **non-blocking communication**, and **real-world reliability** using a state-machine architecture.

---

## 🚀 Features

* ✅ Supports **SARA-R410** and **SARA-R510**
* ✅ Non-blocking **state machine connection control**
* ✅ Safe **URC (Unsolicited Result Code) handling**
* ✅ Robust **socket communication (USOCO / USOWR / USORD)**
* ✅ Automatic **retry and recovery logic**
* ✅ RTC synchronization via network time (`AT+CCLK`)
* ✅ Designed for **long-term unattended operation**

---

## 🧩 Architecture Overview

### Connection State Machine

The modem connection is handled using a **non-blocking state machine**, avoiding blocking delays and improving system stability.

```
idle
  ↓
UMNOPROF
  ↓
┌───────────────┐
│   R410 branch │
└───────────────┘
  CFUN=15
  ↓
  COPS=2
  ↓
  CGDCONT
  ↓
  UAUTHREQ
  ↓
  COPS=0
  ↓

┌───────────────┐
│   R510 branch │
└───────────────┘
  CFUN=16
  ↓
  CFUN=0
  ↓
  CGDCONT
  ↓
  CFUN=1
  ↓

───────────────
Common sequence
───────────────

CEREG check
  ↓
CGATT check
  ↓

(R510 only)
UPSD → UPSDA
  ↓

done
```

---

## 🔄 URC Handling Strategy

This driver avoids race conditions between **URC and AT commands**.

### Key design:

* `+UUSORD` is **NOT immediately processed**
* Instead:

  * Store pending length → `_rx_pending`
  * Fetch data later using `AT+USORD` in a safe timing

### Benefits:

* Prevents **UART collision**
* Ensures **stable socket receive behavior**
* Works reliably under high traffic

---

## 🔌 Socket Design

### Send (USOWR)

* Supports:

  * Partial send handling
  * Retry with backoff
  * Automatic recovery

### Receive (USORD)

* Buffered receive system:

  * `_rx_pending` → trigger
  * `_rx_buffer` → actual data

---

## 🛡️ Fault Tolerance

Multi-stage recovery mechanism:

1. Retry send
2. Close sockets
3. Reconnect PDP context
4. Reset modem (CFUN)

Designed to recover from:

* Network instability
* Socket failure
* Modem internal errors

---

## ⏱️ Time Synchronization

Uses:

```
AT+CCLK?
```

* Automatically parses network time
* Applies JST correction for R410
* Initializes RTC safely via `mktime`

---

## 📦 Requirements

* MicroPython
* UART-capable board (e.g., Raspberry Pi Pico)
* u-blox SARA-R410 or R510 module

---

## 🛠️ Example Usage

```python
from ublox_sara_r import SaraR
from machine import UART, Pin

uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

modem = SaraR(uart)

if modem.connect("your.apn", "user", "password", 1):
    print("Connected!")

sock = modem.socket_create()

if sock >= 0:
    if modem.socket_connect(sock, "example.com", 80):
        modem.socket_send(b"GET / HTTP/1.0\r\n\r\n")
        data = modem.socket_recv(sock)
        print(data)
```

---

## ⚠️ Known Limitations

* `extract_usord_data()` may fail if payload contains `"` (double quotes)
* No TLS/SSL support (plain TCP only)
* Assumes stable UART configuration

---

## 🔧 Recommended Improvements

* Add global timeout control for `connect()`
* Improve payload parsing for binary-safe handling
* Add TLS support (`USOSEC`)
* Introduce watchdog integration

---




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
   └─ ublox_sara_r.py             # u-blox SARA-R410/R510 modem integration
