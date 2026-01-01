"""
File        : micro_modem.py
Description : MicroPython modem interface class.
              Provides AT command handling, retries, synchronous and asynchronous response parsing,
              basic info queries (IMEI, IMSI, CSQ), abstract socket API, and URC handling.
              Designed for Raspberry Pi Pico2 or similar boards.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#micro_modem.py
import utime
from machine import UART, Pin
import state
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR


class MicroModem:
    def __init__(self, uart = None, led_pin=Pin(25, Pin.OUT), debug=False):
        """Initialize modem with UART and optional debug LED."""
        if uart is None:
            uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))
        self.uart = uart
        self.urc_handlers = []
        
        self.led = led_pin

        # Debug
        self.last_response = b""
        self.rxdata = b""
        if debug:
            state.debug_level = LEVEL_DEBUG
        else:
            state.debug_level = LEVEL_INFO
        
        # Basic modem information
        self.modem_model = "Generic"

        # Initialize IMSI/IMEI/RSSI to None
        self.imsi = None
        self.imei = None
        self.rssi = None

    def _write(self, data: bytes):
        """Send bytes to the modem via UART.(easy to override in subclasses)"""
        self.uart.write(data)

    def _read(self) -> bytes:
        """Read available bytes from UART. Returns empty bytes if none."""
        if self.uart.any():
            return self.uart.read()
        return b""

    def send_at(self, cmd, timeout=5000,
                expect_prompt=None,        # b">" or b"@"
                data_after_prompt=None,    # bytes (chunk)
                async_mode=False,
                return_raw=False):

        """Send an AT command and wait for response."""
        cmd_bytes = cmd.encode() if isinstance(cmd, str) else cmd
        self._write(cmd_bytes + b"\r\n")
        log_status(f"[SEND] {cmd_bytes.decode()}", level=LEVEL_DEBUG2)

        if async_mode:
            return True

        # Wait for prompt (e.g., ">", "@")
        if expect_prompt:
            prompt_resp = self.wait_response(
                expected=expect_prompt,
                timeout=timeout,
                return_full=True
            )

            if prompt_resp is None:
                log_status("[PROMPT] Timeout waiting prompt", level=LEVEL_WARN)
                return None if return_raw else False

            log_status(f"[PROMPT DETECTED] {prompt_resp}", level=LEVEL_DEBUG2)

            if data_after_prompt is None:
                return prompt_resp if return_raw else True

            self._write(data_after_prompt)
            log_status(f"[SEND-DATA] {len(data_after_prompt)} bytes", level=LEVEL_DEBUG2)

        # Wait for OK
        final_resp = self.wait_response(
            expected=b"OK",
            timeout=timeout,
            return_full=True
        )
        
        log_status(f"[RECV] {final_resp}", level=LEVEL_DEBUG)

        if final_resp is None or b"ERROR" in final_resp:
            return final_resp if return_raw else False

        return final_resp if return_raw else True

    def send_at_retry(self, cmd, timeout=3000, retries=3, retry_delay=1000) -> bool:
        """Send AT command with retry mechanism."""
        for attempt in range(1, retries + 1):
            if self.send_at(cmd, timeout):
                return True
            if attempt < retries:
                utime.sleep_ms(retry_delay)
        return False

    def wait_response(self, expected=b"OK", timeout=3000, return_full=False):
        """Wait synchronously for expected response."""
        
        start = utime.ticks_ms()
        self.last_response = b""
        buffer = b""

        if isinstance(expected, str):  # For compatibility
            expected = expected.encode()

        while utime.ticks_diff(utime.ticks_ms(), start) < timeout:
            data = self._read()
            if data:
                self.last_response += data
                buffer += data

                # Error detection
                if b"ERROR" in buffer or b"+CME ERROR" in buffer or b"+CMS ERROR" in buffer:
                    return buffer if return_full else None

                # Stop if expected string found
                if expected in buffer:
                    return buffer if return_full else expected

            utime.sleep_ms(20)

        return None  # timeout

    def wait_response_async(self, expected=b"OK", timeout=2000):
        """Asynchronous response wait (stateful)"""
        
        now = utime.ticks_ms()

        if not hasattr(self, "_wait_state") or self._wait_state is None:
            self._wait_state = {
                "expected": expected,
                "timeout": timeout,
                "start": now,
                "buffer": b""
            }

        st = self._wait_state

        data = self._read()
        if data:
            st["buffer"] += data

        # Expected string found
        if st["expected"] in st["buffer"]:
            self.last_response = st["buffer"]
            self._wait_state = None
            
            log_status(f"[RECV] {self.last_response}", level=LEVEL_DEBUG)
            return True

        # Timeout
        if utime.ticks_diff(now, st["start"]) > st["timeout"]:
            self.last_response = st["buffer"]
            self._wait_state = None
            return None

        return False


    def get_imsi(self, retry=2, delay_ms=1000):
        """Return IMSI of SIM card, or status string if failed."""
        if self.imsi:
            return self.imsi

        for _ in range(retry):
            if self.send_at(b"AT+CIMI", timeout=3000):
                resp = self.last_response.split(b"\r\n")
                for line in resp:
                    s = line.strip().decode()
                    if s.isdigit() and len(s) >= 15:
                        self.imsi = s
                        return s
                    if "SIM failure" in s:
                        self.imsi = "SIM_FAIL"
                        log_status("SIM failure detected", level=LEVEL_WARN)
                        return self.imsi

            utime.sleep_ms(delay_ms)

        self.imsi = "UNKNOWN_IMSI"
        return self.imsi

    def get_imei(self, retry=3, delay_ms=1000):
        """Return IMEI number of modem or 'IMEI_UNKNOWN' if failed."""
        if self.imei:
            return self.imei

        for _ in range(retry):
            if self.send_at(b"AT+CGSN", timeout=3000):
                for raw in self.last_response.split(b"\r\n"):
                    s = raw.strip()
                    if s.isdigit() and len(s) >= 14:
                        self.imei = s.decode()
                        return self.imei
            utime.sleep_ms(delay_ms)

        self.imei = "IMEI_UNKNOWN"
        return self.imei

    def get_signal_strength(self):
        """Query CSQ and store RSSI."""
        if not self.send_at(b"AT+CSQ", timeout=3000):
            return False

        try:
            for line in self.last_response.decode().split("\r\n"):
                if "+CSQ:" in line:
                    rssi = line.split(":")[1].strip().split(",")[0]
                    self.rssi = int(rssi)
                    return True
        except:
            return False

# --- Socket API (abstract) ---
    def socket_create(self) -> int:
        raise NotImplementedError

    def socket_connect(self, sock: int, host: str, port: int) -> bool:
        raise NotImplementedError

    def socket_send(self, sock: int, data: bytes) -> bool:
        raise NotImplementedError

    def socket_recv(self, sock: int, size: int = 1024) -> bytes:
        """
        Receive data from a modem socket.
        Vendor-independent API.
        Returns received bytes, or b"" if no data is available.
        """
        raise NotImplementedError

    def has_rx_data(self, sock: int) -> bool:
        """
        Return True if receive data is available for the socket.
        Vendor-independent API.
        """
        raise NotImplementedError

    def socket_close(self, sock: int) -> None:
        raise NotImplementedError

    def detected_model(self) -> bool:
        if not self.send_at(b'ATI', timeout=20000):
            log_status("Failed to detect Model", level=LEVEL_ERROR)
            return False

        return True
    
    def register_urc_handler(self, handler):
        self.urc_handlers.append(handler)

    def notify_urc(self, event: str, sock: int, param=None):
        for h in self.urc_handlers:
            h(event, sock, param)
    
# TEST code
if __name__ == "__main__":
    from machine import UART, Pin, SPI, I2C, RTC, Timer

    # Initialize UART
    modem = MicroModem(debug=True)
    modem.send_at_retry(b'AT', retries=3)
    modem.send_at_retry(b'ATI', retries=3)
    modem.get_imsi()
    modem.get_imei()
    modem.get_signal_strength()
