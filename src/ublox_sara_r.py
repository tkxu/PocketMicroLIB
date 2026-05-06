"""
File        : ublox_sara_r.py
Description : MicroModem subclass for SARA-R410/R510 LTE modules.
              Provides AT command-based initialization, RTC setup, network connection, and basic socket API.
              AT+UMNOPROF=20 is used to select the preconfigured NTT DOCOMO (Japan) MNO profile.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
              Rev. 0.93  2026-01-17
              Rev. 0.94  2026-04-19
              Rev. 0.96  2026-05-06
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#ublox_sara_r.py
import utime
from machine import UART, Pin, RTC
from micro_modem import MicroModem
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR

SOCKET_CLOSED      = 0
SOCKET_CREATED     = 1
SOCKET_CONNECTING  = 2
SOCKET_OPENED      = 3
SOCKET_CLOSING     = 4


class SaraR(MicroModem):
    """MicroModem subclass for SARA-R410/R510 LTE modules."""

    # --- Connection sequence timeouts (ms) ---
    TIMEOUT_UMNOPROF  = 20_000
    TIMEOUT_CFUN      = 40_000   # CFUN=15/16/0/1
    TIMEOUT_COPS      = 120_000  # COPS=2 (deregister) can take up to 2 min
    TIMEOUT_CGDCONT   = 60_000
    TIMEOUT_COPS0     = 20_000   # COPS=0 (reregister)
    TIMEOUT_CEREG     = 1_200
    TIMEOUT_CGATT     = 30_000
    TIMEOUT_UPSD      = 20_000
    TIMEOUT_SOCKET_CONNECT = 15_000
   
   
    def __init__(self, uart = None, led_pin=Pin(25, Pin.OUT), debug=False):
        """Initialize SaraR modem instance."""
        super().__init__(uart, led_pin, debug)

        self.sock_num = -1
        self.modem_initialized = False
        self.rtc_initialized = False
        self._wait_state = None

        # --- connection state ---
        self.connect_state = "idle"
        self.connect_start = utime.ticks_ms()
 
        self._rx_pending = {}
        self._rx_buffer = {}   # sock_num -> bytearray (per-socket receive buffer)
        self._rx_line_buf = bytearray()
        self._last_cereg = b""
        self._last_cgatt = b""
        
        self._uusocl_received = set()
        
        self.socket_create_fail_count = 0
        self.socket_state = {}  # sock_num -> state
        self.socket_start = utime.ticks_ms()

    def _read(self) -> bytes:
        if not self.uart.any():
            return b""

        raw = self.uart.read()
        if not raw:
            return b""

        self._log(f"[RECV] {raw}", level=LEVEL_DEBUG)
        
        self._rx_line_buf.extend(raw)

        idx = self._rx_line_buf.find(b"@")
        if idx >= 0:
            before = self._rx_line_buf[:idx]
            self._rx_line_buf = self._rx_line_buf[idx+1:]

            if before:
                self._handle_urc_chunk(before)

            return b"@"

        at_lines  = bytearray()
        urc_lines = bytearray()

        while b"\r\n" in self._rx_line_buf:
            line, _, rest = self._rx_line_buf.partition(b"\r\n")
            self._rx_line_buf = bytearray(rest)

            stripped = line.strip()
            
            if not stripped:
                continue

            if self._is_urc(stripped):
                urc_lines += line + b"\r\n"
            else:
                at_lines += line + b"\r\n"

        if urc_lines:
            self._handle_urc_chunk(urc_lines)

        return bytes(at_lines)

    def _handle_urc_chunk(self, data: bytes):

        for line in data.split(b"\r\n"):
            line = line.strip()
            if not line:
                continue

            # --- UUSORD ---
            if line.startswith(b"+UUSORD:"):
                self._handle_uusord(line + b"\r\n")
                continue

            # --- UUSOCL ---
            if line.startswith(b"+UUSOCL:"):
                try:
                    sock_num = int(line.split(b":")[1].strip())
                    self._uusocl_received.add(sock_num)
                except Exception:
                    pass
                continue

            # --- CEREG ---
            if line.startswith(b"+CEREG:"):
                self._last_cereg = line
                continue

            if line.startswith(b"+CGATT:"):
                self._last_cgatt = line
                continue


    def initialize(self, max_retries=3) -> bool:
        """Initialize the modem and detect model. Returns True on success."""
        if self.modem_initialized:
            self._log("[SARA] Modem already initialized", level=LEVEL_DEBUG)
            if self.uart.any():
                rx = self._read()
                if rx:
                    self._log(f"[SARA] rx_data: {rx}", level=LEVEL_WARN)
            return True

        self._log("[SARA] Modem initializing...", level=LEVEL_INFO)

        if not self.send_at_retry(b'AT', retries=7):
            return False

        for attempt in range(1, max_retries + 1):
            self._log(f"[SARA] Initialization attempt {attempt}/{max_retries}", level=LEVEL_INFO)
            utime.sleep(1)

            if not self.send_at_retry(b'ATI', timeout=15000, retries=3):
                self._log("[SARA] ATI command failed", level=LEVEL_ERROR)
                continue

            resp = self.last_response
            self._log(f"ATI response: {resp}", level=LEVEL_DEBUG)

            if b"R510" in resp:
                self.modem_model = "R510"
            elif b"R410" in resp:
                self.modem_model = "R410"
            else:
                self.modem_model = "Unknown_model"
                self._log("[SARA]Unknown modem model", level=LEVEL_ERROR)

            self._log("[SARA] Detected modem: " + self.modem_model, level=LEVEL_INFO)

            utime.sleep(1)
            

            if not self.send_at(b'AT+CFUN=0', timeout=15000):
                self._log("[SARA] Timeout at AT+CFUN=0", level=LEVEL_ERROR)
                continue

            self.modem_initialized = True
            self._log("[SARA] Modem initialized", level=LEVEL_INFO)
            return True

        self._log("[SARA] Modem failed to initialize after retries", level=LEVEL_ERROR)
        
        return False

    def init_rtc(self, max_retries=5) -> bool:

        rtc = RTC()

        for attempt in range(max_retries):

            dt = self.get_time()
            if not dt:
                self._log(
                    f"[SARA] get_time failed ({attempt+1}/{max_retries})",
                    level=LEVEL_WARN
                )
                utime.sleep(2)
                continue

            full_year, month, day, hour, minute, second = dt

            epoch = utime.mktime((full_year, month, day, hour, minute, second, 0, 0))
            if self.modem_model == "R410":
                epoch += 9 * 3600  # R410 returns UTC; convert to JST (UTC+9)

            try:
                y, m, d, h, mi, s, w, _ = utime.localtime(epoch)
                rtc.datetime((y, m, d, w, h, mi, s, 0))
                self.rtc_initialized = True

                self._log(
                    f"[SARA] initialized: {y:04}-{m:02}-{d:02} "
                    f"{h:02}:{mi:02}:{s:02}",
                    level=LEVEL_INFO
                )
                return True

            except Exception as e:
                self._log(
                    f"[SARA] init failed ({attempt+1}/{max_retries}): {e}",
                    level=LEVEL_WARN
                )
                utime.sleep(2)

        self._log("[SARA] initialization failed.", level=LEVEL_ERROR)
        return False


    def detected_model(self) -> bool:
        """Detect modem model via ATI command. Returns True if detected."""
        if self.modem_model == "Unknown_model":
            if not self.send_at(b'ATI', timeout=20000):
                self._log("[SARA] Failed to initialize modem", level=LEVEL_ERROR)
                return False

            resp = self.last_response
            # NOTE: MicroPython 1.26.0 decode() has no errors= keyword support
            # using errors="ignore" causes TypeError → intentionally not used
            self._log("[SARA] ATI response: " + resp.decode(), level=LEVEL_DEBUG2)

            if b"R510" in resp:
                self.modem_model = "R510"
            elif b"R410" in resp:
                self.modem_model = "R410"
            else:
                self._log("[SARA] Unknown modem model", level=LEVEL_ERROR)
                self.modem_model = "Unknown_model"

            self._log("[SARA] Detected modem: " + self.modem_model, level=LEVEL_INFO)

        return True

    def activate(self):
        """Placeholder: activate modem if needed."""
        pass

    def deactivate(self):
        """Set modem to low power (CFUN=0)."""
        self.send_at(b"AT+CFUN=0", timeout=15000)
        self._log("[SARA] Modem set to low power (CFUN=0)", level=LEVEL_INFO)

    def connect(self, apn: str, user: str, key: str, pdp: int) -> bool:

        if not self.modem_initialized:
            if not self.initialize():
                return False

        start = utime.ticks_ms()
        last_progress = start
        prev_state = self.connect_state

        while utime.ticks_diff(utime.ticks_ms(), start) < 60000:
            result = self.connect_step(apn, user, key, pdp)

            if result is True:
                self.init_rtc()
                return True

            elif result is None:

                if self.connect_state != prev_state:
                    last_progress = utime.ticks_ms()
                    prev_state = self.connect_state

                if utime.ticks_diff(utime.ticks_ms(), last_progress) > 15000:
                    self._log("[SARA] connect stalled → reset", level=LEVEL_WARN)
                    self.disconnect()
                    utime.sleep(5)
                    self.connect_state = "idle"
                    self._wait_state = None
                    last_progress = utime.ticks_ms()
            else:
                self._log("[SARA] connect_step error → abort (state={})".format(self.connect_state), level=LEVEL_ERROR)
                break

            utime.sleep_ms(100)

        return False

    def connect_step(self, apn: str, user: str, key: str, pdp: int) -> bool:
        
        def error(msg, fatal=False):
            self._log(msg, level=LEVEL_ERROR)
            
            self.connect_state = "idle"
            self.connect_start = utime.ticks_ms()
            self._wait_state = None
            
            if fatal:
                self.led.on()
                return False
            return None

        now = utime.ticks_ms()
        if self.connect_state == "idle":
            self._log("[SARA] Start connection sequence")
            self._wait_state = None
            self._last_cereg = b""
            self._last_cgatt = b""
            self.send_at(b'AT+UMNOPROF=20', async_mode=True) #NTT DOCOMO(Japan) MNO profile
            self.connect_state = "umnoprof_wait"
            self.connect_start = now

        elif self.connect_state == "umnoprof_wait":
            if self.wait_response_async("OK"):
                if self.modem_model == "R410":
                    self.connect_state = "r410_cfun15_send"
                else:
                    self.connect_state = "r510_cfun16_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_UMNOPROF:
                self.disconnect()
                return error("Timeout UMNOPROF")

        # R410 sequence
        elif self.connect_state == "r410_cfun15_send":
            if utime.ticks_diff(now, self.connect_start) > 2000:
                self.send_at(b'AT+CFUN=15', async_mode=True)
                self.connect_state = "r410_cfun15_wait"
                self.connect_start = now

        elif self.connect_state == "r410_cfun15_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "r410_cops2_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CFUN:
                return error("Timeout CFUN=15")

        elif self.connect_state == "r410_cops2_send":
            if utime.ticks_diff(now, self.connect_start) > 10000:
                self.send_at(b'AT+COPS=2', async_mode=True)
                self.connect_state = "r410_cops2_wait"
                self.connect_start = now

        elif self.connect_state == "r410_cops2_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "r410_cgdcont_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_COPS:
                self.connect_state = "r410_cops2_send"
                return error("Timeout COPS=2")

        elif self.connect_state == "r410_cgdcont_send":
            cmd = f'AT+CGDCONT={pdp},"IP","{apn}"'.encode()
            if not self.send_at(cmd, async_mode=True):
                return error("[R410] CGDCONT failed", fatal=True)
            self.connect_state = "r410_cgdcont_wait"
            self.connect_start = now


        elif self.connect_state == "r410_cgdcont_wait":
            if self.wait_response_async("OK"):
                auth = f'AT+UAUTHREQ={pdp},1,"{user}","{key}"'.encode()
                if not self.send_at(auth, timeout=2000):
                    return error("[R410] Failed UAUTHREQ")
                self.send_at(b'AT+COPS=0', async_mode=True)
                self.connect_state = "r410_done_wait"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CGDCONT:
                return error("[SARA] Timeout CGDCONT")

        elif self.connect_state == "r410_done_wait":
            if self.wait_response_async("OK"):
                self._log("[SARA] R410 Connection complete")
                self.connect_state = "cereg_check_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_COPS0:
                return error("[SARA] Timeout final COPS=0")

        # R510 sequence
        elif self.connect_state == "r510_cfun16_send":
            self.send_at(b'AT+CFUN=16', async_mode=True)
            self.connect_state = "r510_cfun16_wait"
            self.connect_start = now

        elif self.connect_state == "r510_cfun16_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "r510_cfun0_send_wait"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CFUN:
                return error("[R510] Timeout AT+CFUN=16")

        elif self.connect_state == "r510_cfun0_send_wait":
            if utime.ticks_diff(now, self.connect_start) > 10000:
                self.connect_state = "r510_cfun0_send"

        elif self.connect_state == "r510_cfun0_send":
            self.send_at(b'AT+CFUN=0', async_mode=True)
            self.connect_state = "r510_cfun0_wait"
            self.connect_start = now

        elif self.connect_state == "r510_cfun0_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "r510_cgdcont_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CFUN:
                return error("[R510] Timeout AT+CFUN=0")

        elif self.connect_state == "r510_cgdcont_send":
            cmd = f'AT+CGDCONT={pdp},"IPV4V6","{apn}"'.encode()
            self.send_at(cmd, async_mode=True)
            self.connect_state = "r510_cgdcont_wait"
            self.connect_start = now

        elif self.connect_state == "r510_cgdcont_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "r510_cfun1_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CGDCONT:
                return error("[R510] Failed CGDCONT")

        elif self.connect_state == "r510_cfun1_send":
            self.send_at(b'AT+CFUN=1', async_mode=True)
            self.connect_state = "r510_cfun1_wait"
            self.connect_start = now

        elif self.connect_state == "r510_cfun1_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "cereg_check_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CFUN:
                return error("[R510] Timeout AT+CFUN=1")

        # common (CEREG / CGATT)
        elif self.connect_state == "cereg_check_send":
            if utime.ticks_diff(now, self.connect_start) > 1000:
                self._last_cereg = b""
                self.send_at(b'AT+CEREG?', async_mode=True)
                self.connect_state = "cereg_check_wait"
                self.connect_start = now

        elif self.connect_state == "cereg_check_wait":
            if self.wait_response_async("OK"):
                #e.g. "+CEREG: 0,1" or "+CEREG: 0,5"
                resp = self._last_cereg
                if (b"+CEREG:" in resp) and (b",1" in resp or b",5" in resp):
                    self._log("[SARA] Registered to network")
                    self.connect_state = "cgatt_check_send"
                    self.connect_start = now
                else:
                    self.connect_state = "cereg_check_send"
                    self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CEREG:
                self.connect_state = "cereg_check_send"
                return error("[SARA] Timeout CEREG")

        elif self.connect_state == "cgatt_check_send":
            if utime.ticks_diff(now, self.connect_start) > 1000:
                self._last_cgatt = b""
                self.send_at(b'AT+CGATT?', async_mode=True)
                self.connect_state = "cgatt_check_wait"
                self.connect_start = now

        elif self.connect_state == "cgatt_check_wait":
            if self.wait_response_async("OK"):
                if b"+CGATT: 1" in self._last_cgatt:
                    self._log("[SARA] Attached to network")
                    if self.modem_model == "R410":
                        self.connect_state = "done"
                    else:
                        self.connect_state = "udsd0_send"
                        self.connect_start = now
                else:
                    self.connect_state = "cgatt_check_send"
                    self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_CGATT:
                return error("[SARA] Timeout CGATT")

        elif self.connect_state == "udsd0_send":
            self.send_at(b'AT+UPSD=0,0,0', async_mode=True)
            self.connect_state = "udsd0_wait"
            self.connect_start = now

        elif self.connect_state == "udsd0_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "udsd100_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_UPSD:
                return error("[SARA] Timeout AT+UPSD=0,0,0")

        elif self.connect_state == "udsd100_send":
            self.send_at(b'AT+UPSD=0,100,1', async_mode=True)
            self.connect_state = "udsd100_wait"
            self.connect_start = now

        elif self.connect_state == "udsd100_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "udsda_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_UPSD:
                return error("[SARA] Timeout AT+UPSD=0,100,1")

        elif self.connect_state == "udsda_send":
            self.send_at(b'AT+UPSDA=0,3', async_mode=True)
            self.connect_state = "udsda_wait"
            self.connect_start = now

        elif self.connect_state == "udsda_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "done"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > self.TIMEOUT_UPSD:
                return error("[SARA] Timeout AT+UPSDA=0,3")

        elif self.connect_state == "done":
            self.connect_state = "idle"
            return True

        else:
            return error("No state")

        return None

    def socket_create(self) -> int:
        if not self.send_at(b"AT+USOCR=6", timeout=5000):
            self._log(f"[SARA] USOCR failed: {self.last_response}", level=LEVEL_ERROR)
            return self._handle_socket_create_fail()

        sock_num = self._parse_socket_id(self.last_response)

        if sock_num < 0:
            return self._handle_socket_create_fail()

        self.socket_create_fail_count = 0
        self.socket_state[sock_num] = SOCKET_CREATED
        return sock_num

    def _handle_socket_create_fail(self) -> int:
        self.socket_create_fail_count += 1

        self._log(
            f"[SARA] socket_create failed count={self.socket_create_fail_count}",
            level=LEVEL_WARN
        )

        if self.socket_create_fail_count < 3:
            utime.sleep_ms(500)
            return -1

        if self.socket_create_fail_count < 5:
            self._log("[SARA] closing all sockets", level=LEVEL_WARN)
            self.send_at(b"AT+USOCL=0")
            self.send_at(b"AT+USOCL=1")
            utime.sleep(1)
            return -1

        if self.socket_create_fail_count < 8:
            self._log("[SARA] reconnect PDP", level=LEVEL_ERROR)
            self.disconnect()
            utime.sleep(2)
            self.connect_state = "idle"
            return -1

        self._log("[SARA] modem reset (CFUN)", level=LEVEL_ERROR)
        if self.modem_model == "R410":
            self.send_at(b"AT+CFUN=15", timeout=30000)
        else:
            self.send_at(b"AT+CFUN=16", timeout=30000)
        utime.sleep(5)
        self.send_at(b"AT+CFUN=1", timeout=30000)

        self.socket_create_fail_count = 0
        self.connect_state = "idle"

        return -1

    def _parse_socket_id(self, resp: bytes) -> int:

        self._log(f"[SARA] parse_socket_number: {resp}", level=LEVEL_DEBUG2)
        if not resp:
            self._log(f"[SARA] Failed to parse socket_num: not resp")
            return -1

        for line in resp.split(b"\r\n"):
            if b"+USOCR:" in line:
                try:
                    socket_num = int(line.split(b":")[1].strip())
                    self._log(f"[SARA] Get socket_num = {socket_num}")
                    return socket_num
                except Exception as e:
                    self._log(f"[SARA] Failed to parse socket_num: {e} line ={line}")
                    pass
        self._log(f"[SARA] _parse_socket_id failed: last_response = {self.last_response}", level=LEVEL_ERROR)
        return -1

    def socket_connect(self, sock_num, host, port) -> bool:
        cmd = f'AT+USOCO={sock_num},"{host}",{port}'.encode()
        if not self.send_at(cmd, timeout=15000):
            self._log(f"[SARA] USOCO failed: last_response = {self.last_response}", level=LEVEL_ERROR)
            self.socket_close(sock_num)
            return False

        self.sock_num = sock_num
        self.socket_state[sock_num] = SOCKET_OPENED
        self._log(f"[SARA] Socket connected: {sock_num}")
        return True

    def socket_connect_step(self, sock_num, host, port) -> bool | None:
        now = utime.ticks_ms()
        
        state = self.socket_state.get(sock_num, SOCKET_CLOSED)

        if state == SOCKET_CLOSED:
            cmd = f'AT+USOCO={sock_num},"{host}",{port}'.encode()
            self.send_at(cmd, async_mode=True)
            self.socket_state[sock_num] = SOCKET_CONNECTING
            self.socket_start = now
            return None

        elif state == SOCKET_CONNECTING:
            wait_result = self.wait_response_async("OK")
            if wait_result is True:
                self.sock_num = sock_num
                self.socket_state[sock_num] = SOCKET_OPENED
                self._log(f"[SARA] Socket connected: {sock_num}", level=LEVEL_INFO)
                return True

            # +UUSOCL
            if sock_num in self._uusocl_received:
                self._log(
                    f"[SARA] USOCO failed: socket closed early {self.last_response}",
                    level=LEVEL_ERROR
                )
                self._uusocl_received.discard(sock_num)
                self.socket_close(sock_num)
                return False

            if utime.ticks_diff(now, self.socket_start) > self.TIMEOUT_SOCKET_CONNECT:
                self._log(
                    f"[SARA] USOCO timeout: last_response={self.last_response}",
                    level=LEVEL_ERROR
                )
                self.socket_close(sock_num)
                self.socket_state[sock_num] = SOCKET_CLOSED
                return False

            return None


    def socket_send(self, sock_num: int, data: bytes) -> int:
        if sock_num < 0:
            self._log("[SARA] send(): socket not connected", level=LEVEL_ERROR)
            return -1

        total = 0
        mv = memoryview(data)
        MAX_RETRIES = 20

        while total < len(data):
            retries = 0

            while retries < MAX_RETRIES:
                sent = self._send_once(sock_num, mv[total:])
                if sent < 0:
                    retries += 1
                    wait = 200 + retries * 200
                    self._log(f"[SARA] send failed retry={retries}/{MAX_RETRIES}, wait={wait}ms", level=LEVEL_DEBUG2)
                    utime.sleep_ms(wait)
                    continue

                if sent == 0:
                    retries += 1
                    self._log("[SARA] USOWR: sent=0, retry after 100ms", level=LEVEL_DEBUG)
                    utime.sleep_ms(100)
                    continue

                # partial send
                if sent < len(mv[total:]):
                    self._log(f"[SARA] USOWR: partial send {sent}/{len(mv[total:])}, wait 1000ms", level=LEVEL_DEBUG2)
                    utime.sleep_ms(1000)

                total += sent
                break  # sent > 0

            else:
                # MAX_RETRIES
                self._log("[SARA] socket_send failed after retries", level=LEVEL_ERROR)
                return -1

        return total


    def _send_once(self, sock_num: int, data: memoryview) -> int:
        length = len(data)
        cmd = f"AT+USOWR={sock_num},{length}".encode()

        raw = self.send_at(
            cmd,
            expect_prompt=b"@",
            data_after_prompt=data,
            return_raw=True,
            timeout=1000,
        )

        if not raw:
            self._log("[SARA] USOWR: no response", level=LEVEL_ERROR)
            return -1

        self._log(f"[SARA] USOWR: {raw}", level=LEVEL_DEBUG)
        sent = self._parse_usowr_len(raw)

        if sent < 0:
            self._log(f"[SARA] USOWR: parse failed raw={raw}", level=LEVEL_ERROR)
            return -1

        if sent != length:
            self._log(
                f"[SARA] USOWR: partial send: requested={length}, sent={sent}",
                level=LEVEL_WARN,
            )

        return sent

    def socket_recv(self, sock_num: int, size: int = 512) -> bytes:
        """
        Safe receive:
        - No AT during URC handling
        - Use _rx_pending as trigger
        - Per-socket buffer to prevent data mixing across sockets
        """
        # Opportunistic URC poll to catch any pending +UUSORD before checking buffer
        self.poll_urc()

        buf = self._rx_buffer.get(sock_num)

        # --- If there is remaining data in per-socket buffer, return it first ---
        if buf:
            data = buf[:size]
            self._rx_buffer[sock_num] = buf[size:]
            return bytes(data)

        pending = self._rx_pending.get(sock_num, 0)
        if pending <= 0:
            return b""

        length = min(pending, 1024)
        remaining = pending - length
        self._rx_pending[sock_num] = remaining

        cmd = f"AT+USORD={sock_num},{length}".encode()
        if not self.send_at(cmd, timeout=3000):
            self._rx_pending[sock_num] = pending
            return b""

        payload = self.extract_usord_data(self.last_response)
        if payload:
            buf = self._rx_buffer.setdefault(sock_num, bytearray())
            buf.extend(payload)
            self._rx_pending[sock_num] = max(0, pending - len(payload))
    
        buf = self._rx_buffer.get(sock_num)
        if buf:
            data = buf[:size]
            self._rx_buffer[sock_num] = buf[size:]
            return bytes(data)

        return b""

    def _parse_usowr_len(self, resp: bytes) -> int:
        sent = None

        for line in resp.split(b"\r\n"):
            line = line.strip()
            if line.startswith(b"+USOWR:"):
                try:
                    parts = line.split(b":", 1)[1].strip().split(b",")
                    if len(parts) != 2:
                        return -1
                    sent = int(parts[1])
                except Exception:
                    return -1

        return sent if sent is not None else -1

    def _handle_uusord(self, decoded: bytes, sock_num_expected: int = None):
        """
        Handle +UUSORD URC and issue AT+USORD command.

        decoded: bytes containing UART-received data including +UUSORD
        sock_num_expected: optional, restrict to a specific socket number
        """

        self._log(f"[SARA] _handle_uusord: {decoded}", level=LEVEL_DEBUG)

        for line in decoded.split(b"\r\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith(b"+UUSORD:"):
                try:
                    parts = line.split(b":", 1)[1].split(b",")
                    sock_num = int(parts[0])
                    length = int(parts[1])

                    if sock_num_expected is not None and sock_num != sock_num_expected:
                        continue
                         
                    self._rx_pending[sock_num] = self._rx_pending.get(sock_num, 0) + length

                except Exception as e:
                    self._log(f"[SARA] _handle_uusord parse error: {e}", level=LEVEL_WARN)
                    continue



    def extract_usord_data(self, resp: bytes) -> bytes | None:
        """
        Extract <data> from +USORD: <sock>,<len>,"<data>"
        Robust against CRLF inside payload.
        """
        key = b"+USORD:"
        idx = resp.find(key)
        if idx < 0:
            return None

        # find first double-quote after +USORD:
        # WARNING: payload must not contain double-quote (0x22).
        # Binary data with 0x22 will be truncated. Use AT+UDCONF=1 (hex mode) for binary safety.
        start = resp.find(b'"', idx)
        if start < 0:
            return None

        # find the matching closing double-quote
        end = resp.find(b'"', start + 1)
        if end < 0:
            return None

        return resp[start + 1 : end]


    def _is_urc(self, line: bytes) -> bool:
        if not line.startswith(b"+"):
            return False

        if line.startswith(b"+USORD:") or line.startswith(b"+USOWR:"):
            return False

        return (
            line.startswith(b"+UUS") or
            line.startswith(b"+CEREG:") or
            line.startswith(b"+CGATT:")
        )

    def poll_urc(self):
        while self.uart.any() or self._rx_line_buf:
            self._read()
            if not self.uart.any():
                break

    def socket_close(self, sock_num: int):

        utime.sleep_ms(300)

        self.poll_urc()
        
        state = self.socket_state.get(sock_num, SOCKET_CLOSED)

        # --- peer already closed ---
        if state == SOCKET_CLOSED:
            self._log(f"[SARA] socket {sock_num} already closed (state), skip USOCL")

            self._rx_pending[sock_num] = 0
            self._rx_buffer.pop(sock_num, None)
            return

        # --- set state FIRST ---
        self.socket_state[sock_num] = SOCKET_CLOSING

        self.send_at(f"AT+USOCL={sock_num}".encode(), async_mode=True)
        self._log(f"[SARA] Closing socket: {sock_num}", level=LEVEL_DEBUG)

        start = utime.ticks_ms()
        ok_received = False

        # --- wait OK ---
        while utime.ticks_diff(utime.ticks_ms(), start) < 10000:
            if self.wait_response_async("OK"):
                self._rx_pending[sock_num] = 0
                self._rx_buffer.pop(sock_num, None)
                self._uusocl_received.discard(sock_num)
                self.socket_state[sock_num] = SOCKET_CLOSED
                return
            utime.sleep_ms(100)

        # --- wait URC ---
        start = utime.ticks_ms()
        while utime.ticks_diff(utime.ticks_ms(), start) < 3000:
            self._read()
            if sock_num in self._uusocl_received:
                self._rx_pending[sock_num] = 0
                self._rx_buffer.pop(sock_num, None)
                self._uusocl_received.discard(sock_num)
                self.socket_state[sock_num] = SOCKET_CLOSED
                return
            utime.sleep_ms(50)

        # --- timeout fallback ---
        self._log(f"[SARA] socket close timeout: {sock_num}")
        self._rx_pending[sock_num] = 0
        self._rx_buffer.pop(sock_num, None)
        self._uusocl_received.discard(sock_num)
        self.socket_state[sock_num] = SOCKET_CLOSED
    
    def reset_socket_state(self):
        """
        Reset all socket state after MicroSocket.close().
        Clears sock_num, all per-socket RX buffers, and pending data.
        Called by MicroSocket.close() via MicroModem.reset_socket_state().
        """
        self.sock_num = -1
        self._rx_buffer.clear()
        self._rx_pending.clear()

    def disconnect(self):
        
        utime.sleep(1)
        ret = self.send_at(b"AT+CFUN=0", timeout=30000)
        if not ret:
            self._log("[SARA] disconnect:Timeout send AT+CFUN=0 failed", level=LEVEL_ERROR)
            self.connect_state = "idle"
            return
        resp = self.last_response
        self._log(f"[SARA] disconnect:Modem CFUN=0 OK {resp}")

        self.connect_state = "idle"

        
# TEST CODE
if __name__ == "__main__":
    from micro_socket import MicroSocket
    import os
    
    print("=== SARA-R410/R510 LTE modules TEST START ===")
    
    modem = SaraR(debug=True)

    modem.initialize()
    modem.get_imsi()
    modem.get_imei()
    modem.get_signal_strength()

    # --- Network connection ---
    while True:
        result = modem.connect_step('soracom.io', 'sora', 'sora', 1)
        if result is True:
            print("Connect!")
            break
        elif result is False:
            raise SystemExit("Socket connect failed")

        utime.sleep_ms(10)

    modem.init_rtc()
    socket = MicroSocket(modem)
    HOST = "harvest-files.soracom.io"

    # --- test payload ---
    path = "/test_file.txt"
    with open(path, "wb") as f:
        f.write(b"HELLO MicroSocket\n" * 20)

    filesize = os.stat(path)[6]


    if socket.connect(HOST, 80) < 0:
        raise SystemExit("Socket connect failed")

    # --- HTTP ---
    method = "POST / HTTP/1.1\r\n"
    header = (
        f"Host: {HOST}\r\n"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {filesize}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    print("Header:", method + header)
    socket.send(method.encode() + header.encode())
    utime.sleep_ms(1000)

    # --- body ---
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            socket.send(chunk)
            utime.sleep_ms(200)

    while socket.poll():
        socket.recv()
        utime.sleep_ms(200)

    socket.close()
    modem.disconnect()
