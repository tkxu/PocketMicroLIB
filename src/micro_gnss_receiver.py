"""
File        : micro_gnss_receiver.py
Description : MicroPython source code for interfacing a Raspberry Pi Pico2 with an F9P via UART.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
              Rev. 0.92  2026-04-19
              Rev. 0.93  2026-04-26
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# micro_gnss_receiver.py
import _thread
import utime
from machine import Pin, UART


class MicroGNSSReceiver:
    """
    Stable GNSS receiver for MicroPython (e.g. Raspberry Pi Pico 2)

    Features:
    - Background UART receive thread
    - Safe NMEA parsing (ASCII only, checksum verified)
    - GGA sentence support
    - No bytearray slice deletion (MicroPython safe)
    - Buffer overflow protection
    - Thread-safe position access
    - First fix wait support
    """

    # === constants ===
    MAX_BUFFER_SIZE = 64 * 1024
    TRIM_BUFFER_SIZE = 32 * 1024

    RX_THREAD_SLEEP_MS = 2
    WAIT_FIX_POLL_MS = 50
    MAIN_LOOP_SLEEP_MS = 200

    def __init__(self, uart, debug=False, min_fix_quality=1):
        """
        Args:
            uart: Configured UART instance
            debug: Enable debug output
            min_fix_quality:
                Minimum GGA fix quality to accept as valid
                0 = invalid
                1 = GPS
                2 = DGPS
                4 = RTK Fixed
                5 = RTK Float
        """
        self.uart = uart
        self.debug = debug
        self.min_fix_quality = min_fix_quality

        # Protects both buffer and gps_data
        self._lock = _thread.allocate_lock()

        self.buffer = bytearray()
        self._rx_running = False
        self.uart_bytes = 0

        self.gps_data = self._empty_gps_data()
        self.has_fix = False

        self._sentence_handlers = {
            b"GGA": self._handle_gga,
        }

    # === internal utility ===
    def _empty_gps_data(self):
        return {
            "lat": None,
            "lon": None,
            "alt": None,
            "hdop": None,
        }

    def _debug_print(self, *args):
        if self.debug:
            print(*args)

    # === uart ===
    def _uart_read(self):
        if self.uart.any():
            return self.uart.read()
        return b""

    def _uart_write(self, data):
        # Reserved for sending RTCM/UBX commands to the receiver.
        self.uart.write(data)

    # === thread ===
    def start(self):
        """
        Start background UART receiver thread.
        """
        if self._rx_running:
            return

        self._rx_running = True
        _thread.start_new_thread(self._receiver_thread, ())

    def stop(self):
        """
        Signal the receiver thread to stop.
        Note: The thread may still be running briefly after this call.
        Allow at least RX_THREAD_SLEEP_MS before accessing shared state.
        """
        self._rx_running = False

    def _receiver_thread(self):
        while self._rx_running:
            try:
                data = self._uart_read()

                if data:
                    with self._lock:
                        self.buffer.extend(data)
                        self.uart_bytes += len(data)

            except OSError as e:
                self._debug_print("[RX ERROR]", e)

            except RuntimeError as e:
                self._debug_print("[RX ERROR]", e)

            utime.sleep_ms(self.RX_THREAD_SLEEP_MS)

    # === buffer processing ===
    def check_buffer(self):
        """
        Process all complete NMEA sentences currently in buffer.

        Returns:
            True  -> at least one valid fix obtained
            False -> no valid fix
        """
        updated = False

        with self._lock:

            if len(self.buffer) > self.MAX_BUFFER_SIZE:
                self.buffer = bytearray(
                    self.buffer[-self.TRIM_BUFFER_SIZE:]
                )
                self._debug_print("[BUFFER TRIMMED]")

            while True:
                result = self._check_buffer_impl()

                if result is None:
                    break

                if result is True:
                    updated = True

                # Safety guard: avoid infinite loop if buffer is unexpectedly empty
                if not self.buffer:
                    break

        return updated

    def _check_buffer_impl(self):
        """
        Parse one NMEA sentence from the buffer.

        Returns:
            True  -> valid fix
            False -> parsed but no valid fix
            None  -> incomplete sentence
        """

        if not self.buffer:
            return None

        start = self.buffer.find(b"$")

        if start == -1:
            self.buffer = bytearray()
            return None

        if start > 0:
            self.buffer = bytearray(self.buffer[start:])

        try:
            end = self.buffer.index(b"\r\n") + 2

        except ValueError:
            return None

        line = bytes(self.buffer[:end])

        # Avoid:
        # TypeError: bytearray object doesn't support item deletion
        self.buffer = bytearray(self.buffer[end:])

        return self._process_nmea_line(line)

    # === nmea processing ===
    def _process_nmea_line(self, line):
        """
        Decode, validate and dispatch one NMEA sentence.
        """

        try:
            text = line.decode("ascii").strip()

        except UnicodeError:
            return False

        self._debug_print("[NMEA]", text)

        if not self._verify_nmea_checksum(text):
            self._debug_print("[CHECKSUM ERROR]", text)
            return False

        try:
            comma = text.index(",")
            sentence_id = text[3:comma].encode("ascii")

        except (ValueError, IndexError):
            return False

        handler = self._sentence_handlers.get(sentence_id)

        if handler is None:
            return False

        return handler(text)

    def _verify_nmea_checksum(self, sentence):
        """
        Verify NMEA checksum.

        Format:
            $<body>*XX
        """

        try:
            star = sentence.rfind("*")

            if star == -1:
                return False

            recv_sum = sentence[star + 1: star + 3]

            if len(recv_sum) != 2:
                return False

            body = sentence[1:star]

            calc = 0
            for c in body:
                calc ^= ord(c)

            return "{:02X}".format(calc) == recv_sum.upper()

        except (ValueError, TypeError):
            return False

    # === gga ===
    def _handle_gga(self, text):
        """
        Handle GGA sentence.
        """
        self._parse_nmea_gga(text)

        self._debug_print(
            "[PARSED GGA]",
            self.gps_data,
            "FIX:",
            self.has_fix
        )

        return self.has_fix

    def _parse_nmea_gga(self, text):
        """
        Parse GGA sentence.

        Format:
            $xxGGA,time,lat,N/S,lon,E/W,
            quality,sats,hdop,alt,M,...
        """

        try:
            parts = text.split(",")

            lat = self._convert(parts[2], parts[3])
            lon = self._convert(parts[4], parts[5])

            fix_quality = int(parts[6]) if parts[6] else 0
            hdop = float(parts[8]) if parts[8] else None
            alt = float(parts[9]) if parts[9] else None

            self.has_fix = (
                fix_quality >= self.min_fix_quality
                and lat is not None
                and lon is not None
            )

            if self.has_fix:
                self.gps_data["lat"] = lat
                self.gps_data["lon"] = lon
                self.gps_data["alt"] = alt
                self.gps_data["hdop"] = hdop

            # gps_data is preserved on fix loss to retain last known position.
            # Use has_fix to check validity before using gps_data.

        except (ValueError, IndexError) as e:
            self.has_fix = False
            self._debug_print("[GGA PARSE ERROR]", e)

    def _convert(self, coord, direction):
        """
        Convert NMEA coordinate to decimal degrees.

        Latitude:
            DDMM.MMMM

        Longitude:
            DDDMM.MMMM
        """

        try:
            if not coord:
                return None

            if direction in ("N", "S"):
                deg = float(coord[:2])
                minutes = float(coord[2:])

            elif direction in ("E", "W"):
                deg = float(coord[:3])
                minutes = float(coord[3:])

            else:
                return None

            value = deg + (minutes / 60.0)

            if direction in ("S", "W"):
                value = -value

            return value

        except (ValueError, IndexError, TypeError):
            return None

    # === wait for first fix ===
    def wait_first_fix(self, timeout_sec=30):
        """
        Wait until valid GNSS fix is obtained.

        Returns:
            True  -> fix acquired
            False -> timeout
        """
        start = utime.ticks_ms()

        while utime.ticks_diff(
            utime.ticks_ms(),
            start
        ) < timeout_sec * 1000:

            if not self._rx_running:
                data = self._uart_read()

                if data:
                    with self._lock:
                        self.buffer.extend(data)

            if self.check_buffer() and self.has_fix:
                return True

            utime.sleep_ms(self.WAIT_FIX_POLL_MS)

        return False

    # === public utility ===
    def get_position(self):
        """
        Return snapshot of latest GPS data.

        Thread-safe. Returns last known position even after fix loss.
        Use has_fix to check validity.
        """
        with self._lock:
            return self.gps_data.copy()


# === test code ===
if __name__ == "__main__":

    uart = UART(
        1,
        baudrate=115200,
        tx=Pin(8),
        rx=Pin(9)
    )

    gnss = MicroGNSSReceiver(
        uart,
        debug=True,
        min_fix_quality=1
    )

    gnss.start()

    print("Waiting for GNSS fix...")

    if not gnss.wait_first_fix(timeout_sec=60):
        print("Fix timeout. Continuing anyway.")

    while True:
        updated = gnss.check_buffer()

        if updated and gnss.has_fix:
            pos = gnss.get_position()

            print(
                "Lat:", pos["lat"],
                "Lon:", pos["lon"],
                "Alt:", pos["alt"],
                "HDOP:", pos["hdop"]
            )

        utime.sleep_ms(
            MicroGNSSReceiver.MAIN_LOOP_SLEEP_MS
        )