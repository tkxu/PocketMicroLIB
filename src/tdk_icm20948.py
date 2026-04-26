"""
File        : icm20948.py
Description : MicroPython driver source code for interfacing the Raspberry Pi Pico 2
              with the ICM20948(Accel/Gyro/Mag) via I2C on the Waveshare 10-DOF IMU Sensor Module.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-03-21
              Rev. 0.91  2026-04-26
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# tdk_icm20948.py

import math
import utime

# === register definitions ===
REG_BANK_SEL     = 0x7F

# Bank 0
ACCEL_XOUT_H     = 0x2D
GYRO_XOUT_H      = 0x33
TEMP_OUT_H       = 0x39

# Bank 3 (I2C Master)
I2C_MST_CTRL     = 0x00  # I2C master control
I2C_MST_ODR_CFG  = 0x01  # I2C master ODR config
I2C_SLV0_ADDR    = 0x03
I2C_SLV0_REG     = 0x04
I2C_SLV0_CTRL    = 0x05
I2C_SLV0_DO      = 0x06

# EXT_SLV_SENS_DATA_00: slave sensor readback base in Bank 0
EXT_SLV_SENS_DATA_00 = 0x3B

# Magnetometer (AK09916)
MAG_ADDR         = 0x0C
MAG_REG_CNTL2    = 0x31
MAG_REG_HXL      = 0x11

# Scale factors
ACCEL_SCALE = 16384.0   # LSB/g  (±2g range)
GYRO_SCALE  = 131.0     # LSB/dps (±250dps range)
MAG_SCALE   = 0.15      # uT/LSB


class ICM20948:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr
        self.bank = -1

        self._select_bank(0)

        # Power management: enable, clock auto-select
        self._write_reg(0x06, 0x01)
        utime.sleep_ms(100)

        # Disable sleep mode
        self._write_reg(0x07, 0x00)
        utime.sleep_ms(10)

        self._init_magnetometer()

    # === low-level ===
    def _select_bank(self, bank):
        if self.bank != bank:
            self.i2c.writeto_mem(self.addr, REG_BANK_SEL, bytes([bank << 4]))
            self.bank = bank

    def _write_reg(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes([val]))

    def _read_reg(self, reg, n=1):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _to_signed(self, msb, lsb):
        val = (msb << 8) | lsb
        return val - 65536 if val & 0x8000 else val

    # === magnetometer ===
    def _write_mag(self, reg, val):
        self._select_bank(3)
        self._write_reg(I2C_SLV0_ADDR, MAG_ADDR)
        self._write_reg(I2C_SLV0_REG, reg)
        self._write_reg(I2C_SLV0_DO, val)
        self._write_reg(I2C_SLV0_CTRL, 0x81)  # enable, 1 byte write
        utime.sleep_ms(10)

    def _init_magnetometer(self):
        self._select_bank(3)

        # I2C master clock 400kHz
        self._write_reg(I2C_MST_CTRL, 0x07)
        # Enable I2C master mode
        self._write_reg(I2C_MST_ODR_CFG, 0x20)
        utime.sleep_ms(10)

        # Soft reset magnetometer
        self._write_mag(MAG_REG_CNTL2, 0x01)
        utime.sleep_ms(100)

        # Continuous mode 4 (100Hz)
        self._write_mag(MAG_REG_CNTL2, 0x08)
        utime.sleep_ms(10)

    def read_mag(self):
        self._select_bank(3)

        # Configure slave 0 to read 7 bytes from AK09916 HXL
        self._write_reg(I2C_SLV0_ADDR, MAG_ADDR | 0x80)  # read flag
        self._write_reg(I2C_SLV0_REG, MAG_REG_HXL)
        self._write_reg(I2C_SLV0_CTRL, 0x87)  # enable, 7 bytes

        utime.sleep_ms(10)

        # Read from EXT_SLV_SENS_DATA_00 in Bank 0
        self._select_bank(0)
        data = self._read_reg(EXT_SLV_SENS_DATA_00, 7)

        mx = self._to_signed(data[1], data[0]) * MAG_SCALE
        my = self._to_signed(data[3], data[2]) * MAG_SCALE
        mz = self._to_signed(data[5], data[4]) * MAG_SCALE

        return mx, my, mz

    # === accelerometer ===

    def read_accel(self):
        self._select_bank(0)
        data = self._read_reg(ACCEL_XOUT_H, 6)

        ax = self._to_signed(data[0], data[1]) / ACCEL_SCALE
        ay = self._to_signed(data[2], data[3]) / ACCEL_SCALE
        az = self._to_signed(data[4], data[5]) / ACCEL_SCALE

        return ax, ay, az

    # === gyroscope ===

    def read_gyro(self):
        self._select_bank(0)
        data = self._read_reg(GYRO_XOUT_H, 6)

        gx = self._to_signed(data[0], data[1]) / GYRO_SCALE
        gy = self._to_signed(data[2], data[3]) / GYRO_SCALE
        gz = self._to_signed(data[4], data[5]) / GYRO_SCALE

        return gx, gy, gz

    # === temperature ===

    def read_temp(self):
        self._select_bank(0)
        raw = self._to_signed(*self._read_reg(TEMP_OUT_H, 2))
        return (raw / 333.87) + 21.0


def compute_attitude_tilt_compensated(
    ax, ay, az,
    mx, my, mz,
    prev_pitch=0.0,
    prev_roll=0.0,
    alpha=0.3
):
    """
    Compute pitch, roll, yaw with tilt compensation.

    Args:
        ax, ay, az : accel (g)
        mx, my, mz : mag (uT)
        prev_pitch : previous pitch (deg)
        prev_roll  : previous roll (deg)
        alpha      : low-pass filter weight for accel

    Returns:
        pitch, roll, yaw (degrees)
    """

    # === pitch / roll (degrees) ===
    raw_pitch = math.degrees(math.atan2(-ax, (ay**2 + az**2) ** 0.5))
    raw_roll  = math.degrees(math.atan2(ay, az))

    pitch = alpha * raw_pitch + (1 - alpha) * prev_pitch
    roll  = alpha * raw_roll  + (1 - alpha) * prev_roll

    # === tilt compensation ===
    pitch_rad = math.radians(pitch)
    roll_rad  = math.radians(roll)

    sin_p = math.sin(pitch_rad)
    cos_p = math.cos(pitch_rad)
    sin_r = math.sin(roll_rad)
    cos_r = math.cos(roll_rad)

    mx_comp = mx * cos_p + mz * sin_p
    my_comp = mx * sin_r * sin_p + my * cos_r - mz * sin_r * cos_p

    yaw = math.degrees(math.atan2(my_comp, mx_comp))
    if yaw < 0:
        yaw += 360

    return pitch, roll, yaw


def compute_attitude_complementary(
    ax, ay, az,
    gx, gy, gz,
    mx, my, mz,
    prev_pitch,
    prev_roll,
    prev_yaw,
    dt,
    alpha=0.98
):
    """
    Complementary filter for 9-axis IMU.

    Args:
        ax, ay, az : accel (g)
        gx, gy, gz : gyro (deg/s)
        mx, my, mz : mag (uT)
        prev_*     : previous angles (deg)
        dt         : delta time (sec)
        alpha      : gyro weight (0.95 - 0.99)

    Returns:
        pitch, roll, yaw (deg)
    """

    # === 1. accel-based angles ===
    pitch_acc = math.degrees(math.atan2(-ax, (ay**2 + az**2) ** 0.5))
    roll_acc  = math.degrees(math.atan2(ay, az))

    # === 2. gyro integration ===
    pitch_gyro = prev_pitch + gx * dt
    roll_gyro  = prev_roll  + gy * dt
    yaw_gyro   = prev_yaw   + gz * dt

    # === 3. complementary filter ===
    pitch = alpha * pitch_gyro + (1 - alpha) * pitch_acc
    roll  = alpha * roll_gyro  + (1 - alpha) * roll_acc

    # === 4. tilt-compensated yaw ===
    pitch_rad = math.radians(pitch)
    roll_rad  = math.radians(roll)

    sin_p = math.sin(pitch_rad)
    cos_p = math.cos(pitch_rad)
    sin_r = math.sin(roll_rad)
    cos_r = math.cos(roll_rad)

    mx_comp = mx * cos_p + mz * sin_p
    my_comp = mx * sin_r * sin_p + my * cos_r - mz * sin_r * cos_p

    yaw_mag = math.degrees(math.atan2(my_comp, mx_comp))
    if yaw_mag < 0:
        yaw_mag += 360

    # Blend gyro yaw with mag yaw (weak correction to reduce drift)
    yaw = 0.98 * yaw_gyro + 0.02 * yaw_mag

    return pitch, roll, yaw


# === test code ===
if __name__ == "__main__":
    from machine import I2C, Pin

    from tdk_icm20948 import ICM20948
    from stmicro_lps22hb import LPS22HB
    from micro_logger import log_status, LEVEL_ERROR

    # === config ===
    I2C_ID   = 1
    SDA_PIN  = 6
    SCL_PIN  = 7
    I2C_FREQ = 400000

    imu = None
    lps = None

    # === I2C initialization ===
    try:
        i2c = I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)

        devices = i2c.scan()
        print("[I2C SCAN]", devices)

        imu = ICM20948(i2c)
        lps = LPS22HB(i2c)

        # IMU warm-up (important for stable output)
        for _ in range(5):
            imu.read_accel()
            utime.sleep_ms(50)

    except Exception as e:
        log_status(f"[INIT] I2C init failed: {e}", LEVEL_ERROR)

    # === state variables ===
    pitch = 0.0
    roll  = 0.0
    yaw   = 0.0

    pres = 0.0
    temp = 0.0

    prev_time = utime.ticks_ms()

    # === main loop ===
    while True:

        # === IMU ===
        if imu is not None:
            try:
                now = utime.ticks_ms()
                dt = utime.ticks_diff(now, prev_time) / 1000.0
                prev_time = now

                ax, ay, az = imu.read_accel()
                gx, gy, gz = imu.read_gyro()
                mx, my, mz = imu.read_mag()

                pitch, roll, yaw = compute_attitude_complementary(
                    ax, ay, az,
                    gx, gy, gz,
                    mx, my, mz,
                    pitch, roll, yaw,
                    dt
                )

            except Exception as e:
                log_status(f"[IMU] read error: {e}", LEVEL_ERROR)

        # === pressure sensor ===
        if lps is not None:
            try:
                pres = lps.pressure()
                temp = lps.temperature()

            except Exception as e:
                log_status(f"[LPS] read error: {e}", LEVEL_ERROR)

        # === output ===
        print(
            f"Pres:{pres:.1f}hPa / "
            f"Temp:{temp:.1f}C / "
            f"Pitch:{pitch:.1f} "
            f"Roll:{roll:.1f} "
            f"Yaw:{yaw:.1f}"
        )

        utime.sleep_ms(1000)