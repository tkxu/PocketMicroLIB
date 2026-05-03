"""
File        : micro_gnss_receiver.py
Description : MicroPython source code for interfacing a Raspberry Pi Pico2 with an GNSS Receiver via UART.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
              Rev. 0.92  2026-04-19
              Rev. 0.95  2026-05-03              
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# micro_gnss_receiver.py
import _thread
import utime
from machine import Pin, UART
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR


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
    """

    # === constants ===
    MAX_BUFFER_SIZE  = 64 * 1024
    TRIM_BUFFER_SIZE = 32 * 1024
    
    def __init__(self, uart, debug=False):
        """
        Args:
            uart: Configured UART instance
            debug: Enable debug output
            quality:
                0 = invalid
                1 = GPS
                2 = DGPS
                4 = RTK Fixed
                5 = RTK Float
        """
        self.uart = uart

        if debug:
            self.log_level = LEVEL_DEBUG
        else:
            self.log_level = LEVEL_INFO

        # Protects both buffer and gps_data
        self._lock = _thread.allocate_lock()

        self.buffer      = bytearray()
        self._rx_running = False
        self.uart_bytes  = 0

        self.gps_data  = self._empty_gps_data()
        self.quality = 0
        self.valid_fix   = False

        self._sentence_handlers = {
            b"GGA": self._handle_gga,
        }

    # === log ===
    def _log(self, msg, level=LEVEL_INFO):
        if level >= self.log_level:
            log_status(msg, level)

    def _empty_gps_data(self):
        return {
            "lat": None,
            "lon": None,
            "alt": None,
            "quality": None,
            "hdop": None,
        }

    # === uart ===
    def _uart_read(self):
        if self.uart.any():
            return self.uart.read(512)
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
        Waits long enough for the thread to complete its current iteration.
        """
        self._rx_running = False
        utime.sleep_ms(20)

    def _receiver_thread(self):
        while self._rx_running:
            try:
                data = self._uart_read()

                if data:
                    with self._lock:
                        self.buffer.extend(data)
                        self.uart_bytes += len(data)

                    # FIX: check_buffer() acquires _lock internally (non-reentrant).
                    # Call it outside the lock to avoid deadlock.
                    self.check_buffer()

            except OSError as e:
                self._log(f"[GNSS]RX ERROR{e}", level=LEVEL_ERROR)

            except RuntimeError as e:
                self._log(f"[GNSS]RX ERROR{e}", level=LEVEL_ERROR)

            utime.sleep_ms(2)

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
                self._log("[GNSS]BUFFER TRIMMED")

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

    # NMEA sentence ID characters: talker (2 chars) + sentence (3 chars) + ','
    # All must be ASCII uppercase letters or digits. Minimum total after '$': 4 chars + ','
    _NMEA_ID_CHARS = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

    @staticmethod
    def _is_valid_nmea_start(buf, pos):
        """
        Check whether buf[pos] == '$' is a genuine NMEA sentence start.

        A real NMEA '$' is immediately followed by:
          - 4 to 10 ASCII uppercase letters/digits  (talker + sentence id)
          - then a comma ','

        Any other pattern (e.g. 0x24 inside a UBX binary payload) is rejected.
        This test is protocol-agnostic: it relies only on the NMEA standard,
        with no knowledge of UBX or any other binary protocol.

        Args:
            buf: bytearray
            pos: index of '$' in buf

        Returns:
            True  -> looks like a real NMEA sentence start
            False -> not a valid NMEA start
        """
        # Need at least '$' + 4 id chars + ',' = 6 bytes to decide
        if len(buf) < pos + 6:
            return None  # inconclusive – need more data

        i = pos + 1
        count = 0

        while i < len(buf) and count < 10:
            b = buf[i]

            if b == ord(","):
                return count >= 4  # valid if we saw 4+ id chars before the comma
            elif b in MicroGNSSReceiver._NMEA_ID_CHARS:
                count += 1
                i += 1
            else:
                return False  # non-ASCII or non-uppercase → not a real NMEA start

        # Reached 10 chars without a comma → not valid NMEA
        return False

    def _check_buffer_impl(self):
        """
        Parse one NMEA sentence from the buffer.

        Robustly handles binary data mixed with NMEA (e.g. UBX+NMEA output)
        without any knowledge of the binary protocol.

        Strategy: when a '$' is found, validate that it is a genuine NMEA
        sentence start (talker/sentence id chars followed by ',') before
        treating it as a frame boundary. False '$' bytes inside binary
        payloads almost never satisfy this pattern, so they are skipped
        without any protocol-specific logic.

        Returns:
            True  -> valid fix
            False -> parsed but no valid fix
            None  -> incomplete sentence (need more data)
        """

        if not self.buffer:
            return None

        search_from = 0

        while True:
            # Find next '$' starting from search_from
            idx = self.buffer.find(b"$", search_from)

            if idx == -1:
                # No '$' at all – discard everything
                self.buffer = bytearray()
                return None

            valid = self._is_valid_nmea_start(self.buffer, idx)

            if valid is None:
                # Need more data to decide – keep buffer intact, wait
                if idx > 0:
                    self.buffer = bytearray(self.buffer[idx:])
                return None

            if valid:
                # Found a genuine NMEA start – discard bytes before it
                if idx > 0:
                    self._log(
                        f"[GNSS] Discarding {idx} non-NMEA byte(s)", level=LEVEL_DEBUG2)
                    self.buffer = bytearray(self.buffer[idx:])
                break

            # '$' failed validation – skip past it and keep searching
            self._log(f"[GNSS] False '$' at buf[{idx}], skipping", level=LEVEL_DEBUG2)
            search_from = idx + 1

        # buffer now starts with a validated '$'
        try:
            end = self.buffer.index(b"\r\n") + 2

        except ValueError:
            # Incomplete sentence – wait for more data
            return None

        line = bytes(self.buffer[:end])

        # MicroPython safe: avoid del self.buffer[:end]
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

        self._log(f"[GNSS][NMEA]{text}", level=LEVEL_DEBUG)

        if not self._verify_nmea_checksum(text):
            self._log(f"[GNSS][CHECKSUM ERROR]{text}", level=LEVEL_ERROR)
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

        self._log(f"[GNSS][PARSED GGA]{self.gps_data} ", level=LEVEL_DEBUG2)

        return self.valid_fix

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

            try:
                self.quality = int(parts[6]) if parts[6] else 0
            except (ValueError, TypeError):
                self.quality = 0

            hdop = float(parts[8]) if parts[8] else None
            alt  = float(parts[9]) if parts[9] else None

            self.valid_fix = (
                self.quality > 0
                and lat is not None
                and lon is not None
            )

            if self.valid_fix:
                self.gps_data["lat"]     = lat
                self.gps_data["lon"]     = lon
                self.gps_data["alt"]     = alt
                self.gps_data["hdop"]    = hdop
                self.gps_data["quality"] = self.quality

            else:
                # Detailed fix=False diagnosis logged at WARN so it is
                # visible without debug=True.
                if self.quality == 0:
                    self._log(
                        "[GNSS] quality=0: no satellites",
                        level=LEVEL_WARN
                    )

                if lat is None:
                    self._log(
                        f"[GNSS] lat=None: raw='{parts[2]}' dir='{parts[3]}'",
                        level=LEVEL_WARN
                    )
                if lon is None:
                    self._log(
                        f"[GNSS] lon=None: raw='{parts[4]}' dir='{parts[5]}'",
                        level=LEVEL_WARN
                    )

        except (ValueError, IndexError) as e:
            self.quality = 0
            self.valid_fix   = False    # ensure valid_fix is cleared on parse error
            self._log(f"[GNSS] GGA PARSE ERROR: {e}", level=LEVEL_ERROR)

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

    # === public utility ===
    def get_position(self):
        """
        Return snapshot of latest GPS data.

        Thread-safe. Returns last known position even after fix loss.
        Use valid_fix to check validity before using the returned data.
        """
        with self._lock:
            return self.gps_data.copy()

    def get_raw_snapshot(self):
        """
        Return a snapshot of buffer and clear it atomically under lock.

        Thread-safe. Use this instead of accessing buffer directly
        from the main loop to avoid a race condition where the receiver
        thread writes to buffer while the main loop reassigns it.

        Returns:
            bytes: raw UART data received since last call
        """
        with self._lock:
            snapshot = bytes(self.buffer)
            self.buffer = bytearray()
        return snapshot


# === test code ===
if __name__ == "__main__":
    from micro_storage_manager import MicroStorageManager
    import board_rpi_pico2 as board

    # === Board + Storage setup ===
    # board.init() must be called first so board.sd_mounted is set correctly.
    board.init()

    storage = MicroStorageManager(sd_mounted=board.sd_mounted, filename="temp.nmea")
    if not storage.mounted:
        if not storage.mount():
            log_status("[MAIN] SD not available. Running without SD.", level=LEVEL_WARN)

    # === GNSS setup ===
    uart1 = UART(1, baudrate=115200, tx=Pin(8), rx=Pin(9))
    gnss = MicroGNSSReceiver(uart1, debug=True)
    gnss.start()

    # === Main loop ===
    SD_WRITE_INTERVAL_MS     = 2000  # flush NMEA data to SD every 2 s
    STATUS_PRINT_INTERVAL_MS = 1000  # print position every 1 s

    last_sd_write     = utime.ticks_ms()
    last_status_print = utime.ticks_ms()
    total_written     = 0

    while True:
        now = utime.ticks_ms()

        # === SD write ===
        if utime.ticks_diff(now, last_sd_write) >= SD_WRITE_INTERVAL_MS:
            last_sd_write = now

            if storage.mounted:
                # get_raw_snapshot() acquires _lock atomically,
                # snapshots buffer and clears it – race-condition free.
                snapshot = gnss.get_raw_snapshot()

                if snapshot:
                    written = storage.append_file(storage.temp_file, snapshot)
                    total_written += written
                    gnss._log(f"[MAIN] wrote {written} bytes (total {total_written})")
                else:
                    gnss._log("[MAIN] no data to write", level=LEVEL_DEBUG2)

        # === Status print ===
        if utime.ticks_diff(now, last_status_print) >= STATUS_PRINT_INTERVAL_MS:
            last_status_print = now

            if gnss.valid_fix:
                pos = gnss.get_position()
                gnss._log(
                    f"[MAIN] Lat:{pos['lat']} Lon:{pos['lon']}"
                    f" Alt:{pos['alt']} Q:{pos['quality']}",
                    level=LEVEL_INFO
                )
            else:
                gnss._log("[MAIN] Waiting for NMEA fix...", level=LEVEL_DEBUG2)

        utime.sleep_ms(100)
