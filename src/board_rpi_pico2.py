"""
File        : board_rpi_pico2.py
Description : Board-specific initialization and utilities for Raspberry Pi Pico 2 (RP2040).
              Handles SD card mounting, pin mapping, GPIO/ADC setup, power control, and board-level helper functions.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# board_rpi_pico2.py
import utime
import os
from machine import Pin, SPI, ADC
from micro_logger import log_status, LEVEL_INFO, LEVEL_ERROR
import sdcard


# ADC conversion factor for RP2040 (12-bit ADC read as 16-bit)
conversion_factor = 3.3 / 65535

sd_mounted = False
safe_mode = False
board_type = ""


# Initialize LED and power pins
led1 = None
led2 = None
led3 = None
led4 = None
power = None
reset = None

sensor_temp = None  # ADC4 = internal temperature sensor
vsys_adc = None   # GPIO29 / ADC3 connected to VSYS/3　for reading VSYS voltage


def read_vsys_voltage():
    raw = vsys_adc.read_u16()
    return round((raw * conversion_factor) * 3.0, 2)

def read_cpu_temp():
    reading = sensor_temp.read_u16()
    voltage = reading * conversion_factor
    temp_c = 27 - (voltage - 0.706) / 0.001721
    return round(temp_c, 1)


def _mount_sd():
    """
    Try SD card mount with known SPI pin sets.
    """
    global sd_mounted, board_type
    
    spi_pins_list = [
        {"sck": 2,  "mosi": 3,  "miso": 4,  "cs": 5,  "type": "B1"},
        {"sck": 18, "mosi": 19, "miso": 16, "cs": 17, "type": "B2"},
    ]

    sd_mounted = False

    for pins in spi_pins_list:
        try:
            spi = SPI(
                0,
                baudrate=25_000_000,
                sck=Pin(pins["sck"]),
                mosi=Pin(pins["mosi"]),
                miso=Pin(pins["miso"]),
            )
            sd = sdcard.SDCard(spi, Pin(pins["cs"]))
            os.mount(sd, "/sd")

            try:
                os.mkdir("/sd/log")
            except OSError:
                pass

            sd_mounted = True
            board_type = pins["type"]
            log_status(f"SD mounted pins={pins}", LEVEL_INFO)
            return

        except Exception as e:
            log_status(f"SD mount failed pins={pins} err={e}", LEVEL_ERROR)

    log_status("SD not mounted, continue without SD", LEVEL_ERROR)


def _pinmap_by_board_type(board_type):
    """
    Return pin map by detected board type.
    """
    if board_type == "B1":
        return {"led2": 18, "led3": 19, "led4": 20, "power": 22, "reset": None}
    elif board_type == "B2":
        return {"led2": 14, "led3": 15, "led4": 28, "power": 2,  "reset": 3}
    else:
        # fallback
        return {"led2": 14, "led3": 15, "led4": 28, "power": 2,  "reset": 3}


def _print_sd_info():
    """
    Print SD card usage info.
    """
    try:
        stat = os.statvfs("/sd")
        total = stat[2] * stat[0]
        free  = stat[3] * stat[0]
        used  = total - free

        log_status("SD card info:")
        log_status("  Total: {:.2f} MB".format(total / 1024 / 1024))
        log_status("  Used : {:.2f} MB".format(used / 1024 / 1024))
        log_status("  Free : {:.2f} MB".format(free / 1024 / 1024))

    except Exception as e:
        log_status(f"SD info error: {e}", LEVEL_ERROR)


def init():
    """
    Initialize Raspberry Pi Pico 2 board.
    """
    global board_name, board_type, sd_mounted
    global led1, led2, led3, led4, power, reset
    global sensor_temp, vsys_adc
    
    log_status("board_rpi_pico2: init")

    # --- SD mount & board_type detection ---
    _mount_sd()

    # --- Pin map ---
    pins = _pinmap_by_board_type(board_type)

    # --- GPIO ---
    led1 = Pin(25, Pin.OUT)  # onboard LED
    led2 = Pin(pins["led2"], Pin.OUT)
    led3 = Pin(pins["led3"], Pin.OUT)
    led4 = Pin(pins["led4"], Pin.OUT)

    power = Pin(pins["power"], Pin.OUT)
    reset = Pin(pins["reset"], Pin.OUT) if pins["reset"] else None

    # --- ADC ---
    sensor_temp = ADC(4)
    vsys_adc   = ADC(29)

    # --- Power ON ---
    led1.on()
    led2.on()
    led3.on()
    led4.on()
    power.value(1)

    # --- SD info ---
    if sd_mounted:
        _print_sd_info()



# ================= TEST code =================
if __name__ == "__main__":
    from micro_logger import log_status, LEVEL_INFO, LEVEL_ERROR
    
    log_status("board_rpi_pico2: start")
    init()

        
    try:
        vbat = read_vsys_voltage()
        temp_c = read_cpu_temp()
        log_status(f"CPU Temperature:{temp_c:.1f}°C / VSYS voltage = {vbat:.2f} V", level=LEVEL_INFO)
    except Exception as e:
        log_status("Failed to read VSYS voltage: {}".format(e), level=LEVEL_ERROR)
        
    led1.on()
    led2.on()
    led3.on()
    led4.on()
    utime.sleep(1)

    led1.off()
    led2.off()
    led3.off()
    led4.off()
    utime.sleep(1) 
