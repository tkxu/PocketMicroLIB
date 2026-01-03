"""
File        : boot.py
Description : 
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# boot.py
import sys
import utime
from machine import Pin
from micro_logger import log_status, LEVEL_INFO, LEVEL_ERROR

log_status(sys.version)
log_status("boot.py: start")

utime.sleep(1)

# Safe mode
if Pin(15, Pin.IN, Pin.PULL_UP).value() == 0:
    log_status("SAFE MODE: skip main.py")
    sys.exit()

# Board select & init
board_name = sys.implementation._machine
log_status(f"Board detected: {board_name}", LEVEL_INFO)

try:
    if "Pico2" in board_name:
        import board_rpi_pico2 as board
    elif "MechaTracks MicroCat.1" in board_name:
        import board_microcat1 as board        
    else:
        log_status("Unknown board, fallback to generic", LEVEL_ERROR)
        from boards import board_generic as board

    board.init()
    log_status("Board: init")

except Exception as e:
    log_status(f"Board init failed: {e}", LEVEL_ERROR)

log_status(f"boot.py: done (Board={board_name})", LEVEL_INFO)

