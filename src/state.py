"""
File        : state.py
Description : Global state and hardware pin definitions for Raspberry Pi Pico2.
              Includes flags for SD card mounting, safe mode, debug level, and references for LEDs, power/reset pins, internal temperature sensor, and VSYS voltage ADC.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# state.py 

sd_mounted = False
safe_mode = False
board_type = ""

debug_level = 2  # LEVEL_DEBUG

# Initialize LED and power pins
led1 = None
led2 = None
led3 = None
led4 = None
power = None
reset = None

sensor_temp = None  # ADC4 = internal temperature sensor
vsys_adc = None   # GPIO29 / ADC3 connected to VSYS/3　for reading VSYS voltage
