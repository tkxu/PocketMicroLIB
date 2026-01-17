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
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#ublox_sara_r.py
import utime
from machine import UART, Pin, RTC
from micro_modem import MicroModem
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR

class SaraR(MicroModem):
    """MicroModem subclass for SARA-R410/R510 LTE modules."""
    
    def __init__(self, uart = None, led_pin=Pin(25, Pin.OUT), debug=False):
        """Initialize SaraR modem instance."""
        super().__init__(uart, led_pin, debug)
        self.imsi = ""
        self.imei = ""
        self.rssi = -1
        self.modem_initialized = False
        
        # --- connection state ---
        self.connect_state = "idle"
        self.connect_start = utime.ticks_ms()
 
        self._rx_pending = {}
        self._rx_buffer = bytearray()

    def initialize(self, max_retries=3) -> bool:
        """Initialize the modem and detect model. Returns True on success."""
        if self.modem_initialized:
            log_status("[SARA] Modem already initialized", level=LEVEL_DEBUG)
            if self.uart.any():
                rx = self.uart.read()
                if rx:
                    log_status(b"[SARA] rx_data:" + rx, level=LEVEL_WARN)
            return True

        log_status("[SARA] Modem initializing...", level=LEVEL_INFO)

        if not self.send_at_retry(b'AT', retries=7):
            return False

        for attempt in range(1, max_retries + 1):
            log_status(f"[SARA] Initialization attempt {attempt}/{max_retries}", level=LEVEL_INFO)
            utime.sleep(1)

            if not self.send_at_retry(b'ATI', timeout=15000, retries=3):
                log_status("[SARA] ATI command failed", level=LEVEL_ERROR)
                continue

            resp = self.last_response
            #log_status(f"ATI response: {resp}", level=LEVEL_DEBUG)

            if b"R510" in resp:
                self.modem_model = "R510"
            elif b"R410" in resp:
                self.modem_model = "R410"
            else:
                self.modem_model = "Unknown_model"
                log_status("[SARA]Unknown modem model", level=LEVEL_ERROR)

            log_status("[SARA] Detected modem: " + self.modem_model, level=LEVEL_INFO)

            utime.sleep(1)
            

            if not self.send_at(b'AT+CFUN=0', timeout=15000):
                log_status("[SARA] Timeout at AT+CFUN=0", level=LEVEL_ERROR)
                continue

            self.modem_initialized = True
            log_status("[SARA] Modem initialized", level=LEVEL_INFO)
            return True

        log_status("[SARA] Modem failed to initialize after retries", level=LEVEL_ERROR)
        
        
        modem.get_imsi()
        
        return False


    def get_time(self):

        if not self.send_at(b'AT+CCLK?', timeout=3000):
            log_status("[SARA] get_time read failed", level=LEVEL_ERROR)
            utime.sleep(1)
            return None

        for line in self.last_response.split(b"\r\n"):
            s = line.decode().strip()

            if not s.startswith("+CCLK:"):
                continue

            start = s.find('"')
            end = s.find('"', start + 1)
            if start < 0 or end < 0:
                continue

            cclk = s[start + 1:end]
            date_part, time_part = cclk.split(",")

            year_short, month, day = map(int, date_part.split("/"))
            time_part = time_part.split("+")[0]
            hour, minute, second = map(int, time_part.split(":"))

            full_year = 2000 + year_short
            # R410 は JST +9 補正が必要
            if self.modem_model == "R410":
                hour = (hour + 9) % 24

            return (full_year, month, day, hour, minute, second)

        log_status("[SARA] get_time failed: +CCLK not found", level=LEVEL_WARN)
        return None


    def init_rtc(self, max_retries=5) -> bool:

        rtc = RTC()

        for attempt in range(max_retries):

            dt = self.get_time()
            if not dt:
                log_status(
                    f"[SARA] get_time failed ({attempt+1}/{max_retries})",
                    LEVEL_WARN
                )
                utime.sleep(2)
                continue

            full_year, month, day, hour, minute, second = dt

            try:
                # --- normalize via mktime ---
                epoch = utime.mktime(
                    (full_year, month, day, hour, minute, second, 0, 0)
                )
                y, m, d, h, mi, s, w, _ = utime.localtime(epoch)

                rtc.datetime((y, m, d, w, h, mi, s, 0))
                self.rtc_initialized = True

                log_status(
                    f"[SARA] initialized: {y:04}-{m:02}-{d:02} "
                    f"{h:02}:{mi:02}:{s:02}",
                    LEVEL_INFO
                )
                return True

            except Exception as e:
                log_status(
                    f"[SARA] init failed ({attempt+1}/{max_retries}): {e}",
                    LEVEL_WARN
                )
                utime.sleep(2)

        log_status("[SARA] initialization failed.", LEVEL_ERROR)
        return False


    def detected_model(self) -> bool:
        """Detect modem model via ATI command. Returns True if detected."""
        if self.modem_model == "Unknown_model":
            if not self.send_at(b'ATI', timeout=20000):
                log_status("[SARA] Failed to initialize modem", level=LEVEL_ERROR)
                return False

            resp = self.last_response
            log_status("[SARA] ATI response: " + resp.decode(errors="ignore"), level=LEVEL_DEBUG2)

            if b"R510" in resp:
                self.modem_model = "R510"
            elif b"R410" in resp:
                self.modem_model = "R410"
            else:
                log_status("[SARA] Unknown modem model", level=LEVEL_ERROR)
                self.modem_model = "Unknown_model"

            log_status("[SARA] Detected modem: " + self.modem_model, level=LEVEL_INFO)

        return True

    def active(self):
        """Placeholder: activate modem if needed."""
        pass

    def deactive(self):
        """Set modem to low power (CFUN=0)."""
        self.send_at(b"AT+CFUN=0", timeout=2000)
        log_status("[SARA] Modem set to low power (CFUN=0)", level=LEVEL_INFO)


    def connect(self, apn: str, user: str, key: str, pdp: int) -> bool:
        
        if self.initialize():
            for _ in range(300):  # 300 * 100ms = 30 sec
                if self.connect_step(apn, user, key, pdp) is True:
                    utime.sleep_ms(100)
                    if self.init_rtc():
                        log_status("[SARA] Successfully to connect ", level=LEVEL_INFO)
                        return True
                utime.sleep_ms(1000)
        return False          

    def connect_step(self, apn: str, user: str, key: str, pdp: int, retries=60, delay=500) -> bool:
        def error(msg, fatal=False):
            log_status(msg, level=LEVEL_ERROR)
            if fatal:
                self.led.on()
                self.connect_state = "idle"
                self.connect_start = utime.ticks_ms()
            return False
        
        now = utime.ticks_ms()
        

        if self.connect_state == "idle":
            log_status("[SARA] Start connection sequence")
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
            elif utime.ticks_diff(now, self.connect_start) > 20000:
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
            elif utime.ticks_diff(now, self.connect_start) > 60000:
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
            elif utime.ticks_diff(now, self.connect_start) > 120000:
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
                if not self.send_at(auth):
                    return error("[R410] Failed UAUTHREQ")
                self.send_at(b'AT+COPS=0', async_mode=True)
                self.connect_state = "r410_done_wait"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 60000:
                return error("[SARA] Timeout CGDCONT")

        elif self.connect_state == "r410_done_wait":
            if self.wait_response_async("OK"):
                log_status("[SARA] R410 Connection complete")
                self.connect_state = "cereg_check_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 20000:
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
            elif utime.ticks_diff(now, self.connect_start) > 40000:
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
            elif utime.ticks_diff(now, self.connect_start) > 40000:
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
            elif utime.ticks_diff(now, self.connect_start) > 20000:
                return error("[R510] Failed CGDCONT")

        elif self.connect_state == "r510_cfun1_send":
            self.send_at(b'AT+CFUN=1', async_mode=True)
            self.connect_state = "r510_cfun1_wait"
            self.connect_start = now

        elif self.connect_state == "r510_cfun1_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "cereg_check_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 20000:
                return error("[R510] Timeout AT+CFUN=1")

        # common (CEREG / CGATT)
        elif self.connect_state == "cereg_check_send":
            if utime.ticks_diff(now, self.connect_start) > 1000:
                self.send_at(b'AT+CEREG?', async_mode=True)
                self.connect_state = "cereg_check_wait"
                self.connect_start = now

        elif self.connect_state == "cereg_check_wait":
            if self.wait_response_async("OK"):
                if b"+CEREG: 0,1" in self.last_response or b"+CEREG: 0,5" in self.last_response:
                    log_status("[SARA] Registered to network")
                    self.connect_state = "cgatt_check_send"
                    self.connect_start = now
                else:
                    self.connect_state = "cereg_check_send"
                    self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 1200:
                self.connect_state = "cereg_check_send"
                return error("[SARA] Timeout CEREG")

        elif self.connect_state == "cgatt_check_send":
            if utime.ticks_diff(now, self.connect_start) > 1000:
                self.send_at(b'AT+CGATT?', async_mode=True)
                self.connect_state = "cgatt_check_wait"
                self.connect_start = now

        elif self.connect_state == "cgatt_check_wait":
            if self.wait_response_async("OK"):
                if b"+CGATT: 1" in self.last_response:
                    log_status("[SARA] Attached to network")
                    if self.modem_model == "R410":
                        self.connect_state = "done"
                    else:
                        self.connect_state = "udsd0_send"
                        self.connect_start = now
                else:
                    self.connect_state = "cgatt_check_send"
                    self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 30000:
                return error("[SARA] Timeout CGATT")

        elif self.connect_state == "udsd0_send":
            self.send_at(b'AT+UPSD=0,0,0', async_mode=True)
            self.connect_state = "udsd0_wait"
            self.connect_start = now

        elif self.connect_state == "udsd0_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "udsd100_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 20000:
                return error("[SARA] Timeout AT+UPSD=0,0,0")

        elif self.connect_state == "udsd100_send":
            self.send_at(b'AT+UPSD=0,100,1', async_mode=True)
            self.connect_state = "udsd100_wait"
            self.connect_start = now

        elif self.connect_state == "udsd100_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "udsda_send"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 20000:
                return error("[SARA] Timeout AT+UPSD=0,100,1")

        elif self.connect_state == "udsda_send":
            self.send_at(b'AT+UPSDA=0,3', async_mode=True)
            self.connect_state = "udsda_wait"
            self.connect_start = now

        elif self.connect_state == "udsda_wait":
            if self.wait_response_async("OK"):
                self.connect_state = "done"
                self.connect_start = now
            elif utime.ticks_diff(now, self.connect_start) > 20000:
                return error("[SARA] Timeout AT+UPSDA=0,3")

        elif self.connect_state == "done":
            return True

        else:
            return error("No state")

        return False

    def socket_create(self) -> int:
        if not self.send_at(b"AT+USOCR=6", timeout=5000):
            log_status(f"[SARA] USOCR failed: last_response = {self.last_response}", LEVEL_ERROR)
            return -1
        return self._parse_socket_id(self.last_response)

    def _parse_socket_id(self, resp: bytes) -> int:

        log_status(f"[SARA] parse_socket_number: {resp}", level=LEVEL_DEBUG2)
        if not resp:
            log_status(f"[SARA] Failed to parse socket_num: not resp")
            return -1

        for line in resp.split(b"\r\n"):
            if b"+USOCR:" in line:
                try:
                    socket_num = int(line.split(b":")[1].strip())
                    log_status(f"[SARA] Get socket_num = {socket_num}")
                    return socket_num
                except Exception as e:
                    log_status(f"[SARA] Failed to parse socket_num: {e}" + line)
                    pass
        log_status(f"[SARA] _parse_socket_id failed: last_response = {self.last_response}", LEVEL_ERROR)
        return -1

    def socket_connect(self, sock_num, host, port) -> bool:
        cmd = f'AT+USOCO={sock_num},"{host}",{port}\r'.encode()
        if not self.send_at(cmd, timeout=15000):
            log_status(f"[SARA] USOCO failed: last_response = {self.last_response}", LEVEL_ERROR)
            self.socket_close(sock_num)
            return False

        self.sock_num = sock_num
        log_status(f"[SARA] Socket connected: {sock_num}", LEVEL_INFO)
        return True

    def socket_connect_step(self, sock_num, host, port) -> bool | None:
        now = utime.ticks_ms()

        if self.socket_state == "idle":
            cmd = f'AT+USOCO={sock_num},"{host}",{port}\r'.encode()
            self.send_at(cmd, async_mode=True)
            self.socket_state = "usoco_wait"
            self.socket_start = now
            return None

        elif self.socket_state == "usoco_wait":
            if self.wait_response_async("OK"):
                self.sock_num = sock_num
                self.socket_state = "done"
                log_status(f"[SARA] Socket connected: {sock_num}", LEVEL_INFO)
                return True

            # +UUSOCL が先に来た場合
            if b"+UUSOCL" in self.last_response:
                log_status(
                    f"[SARA] USOCO failed: socket closed early {self.last_response}",
                    LEVEL_ERROR
                )
                self.socket_close(sock_num)
                self.socket_state = "idle"
                return False

            if utime.ticks_diff(now, self.socket_start) > 15000:
                log_status(
                    f"[SARA] USOCO timeout: last_response={self.last_response}",
                    LEVEL_ERROR
                )
                self.socket_close(sock_num)
                self.socket_state = "idle"
                return False

            return None


    def socket_send(self, data: bytes) -> int:
        if self.sock_num < 0:
            log_status("[SARA] send(): socket not connected", LEVEL_ERROR)
            return -1

        total = 0
        mv = memoryview(data)
        MAX_RETRIES = 20

        while total < len(data):
            retries = 0

            while retries < MAX_RETRIES:
                sent = self._send_once(mv[total:])
                if sent < 0:
                    retries += 1
                    wait = 200 + retries * 200
                    log_status(f"[SARA] send failed retry={retries}/{MAX_RETRIES}, wait={wait}ms", LEVEL_DEBUG2)
                    utime.sleep_ms(wait)
                    continue

                if sent == 0:
                    retries += 1
                    log_status("[SARA] USOWR: sent=0, retry after 100ms", LEVEL_DEBUG)
                    utime.sleep_ms(100)
                    continue

                # partial send
                if sent < len(mv[total:]):
                    log_status(f"[SARA] USOWR: partial send {sent}/{len(mv[total:])}, wait 1000ms", LEVEL_DEBUG2)
                    utime.sleep_ms(1000)

                total += sent
                break  # sent > 0

            else:
                # MAX_RETRIES
                log_status("[SARA] socket_send failed after retries", LEVEL_ERROR)
                return -1

        return total


    def _send_once(self, data: memoryview) -> int:
        length = len(data)
        cmd = f"AT+USOWR={self.sock_num},{length}".encode()

        raw = self.send_at(
            cmd,
            expect_prompt=b"@",
            data_after_prompt=data,
            return_raw=True,
            timeout=1000,
        )

        if not raw:
            log_status("[SARA] USOWR: no response", LEVEL_ERROR)
            return -1

        #log_status(f"[SARA] USOWR: {raw}", LEVEL_DEBUG)
        sent = self._parse_usowr_len(raw)

        if sent < 0:
            log_status(f"[SARA] USOWR: parse failed raw={raw}", LEVEL_ERROR)
            return -1

        if sent != length:
            log_status(
                f"[SARA] USOWR: partial send: requested={length}, sent={sent}",
                LEVEL_WARN,
            )

        return sent

    def socket_recv(self, sock_num: int, size: int = 512) -> bytes:
        """
        Receive data from socket using +UUSORD URC.
        Returns bytes received, may be empty if no data.
        Handles multiple URC in last_response safely.
        """
        if self._rx_buffer:
            data = self._rx_buffer[:size]
            self._rx_buffer = self._rx_buffer[size:]
            return bytes(data)

        if not self.wait_response("+UUSORD:", timeout=3000):
            # Timeout
            return b""

        resp = self.last_response
        ok_received, uusocl_received = self._handle_uusord(resp, sock_num_expected=sock_num)

        if ok_received:
            data = self._rx_buffer[:size]
            self._rx_buffer = self._rx_buffer[size:]
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
        Returns:
            ok_received (bool)
            uusocl_received (bool)
        """
        ok_received = False
        uusocl_received = False

        log_status(f"[SARA] _handle_uusord: {decoded}", level=LEVEL_DEBUG)

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

                    cmd = f"AT+USORD={sock_num},{length}\r"
                    if not self.send_at(cmd):
                        log_status("[SARA] send_at failed for USORD", LEVEL_WARN)
                        continue

                    resp = self.last_response
                    payload = self.extract_usord_data(resp)
                    if payload:
                        self._rx_buffer.extend(payload)

                    for resp_line in resp.split(b"\r\n"):
                        resp_line = resp_line.strip()
                        if resp_line == b"OK":
                            ok_received = True
                        elif resp_line.startswith(b"+UUSOCL:"):
                            uusocl_received = True

                except Exception as e:
                    log_status(f"[SARA] _handle_uusord parse error: {e}", LEVEL_WARN)
                    continue

        log_status(f"[SARA] _rx_buffer: {self._rx_buffer}", level=LEVEL_DEBUG2)
        return ok_received, uusocl_received


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
        start = resp.find(b'"', idx)
        if start < 0:
            return None

        # find the matching closing double-quote
        end = resp.find(b'"', start + 1)
        if end < 0:
            return None

        return resp[start + 1 : end]

    def socket_close(self, sock_num: int):
        """
        Close the specified socket.
        """
        # Send socket close command
        if not self.send_at(f"AT+USOCL={sock_num}\r".encode(), timeout=5000):
                log_status("[SARA] USOCL:Timeout", LEVEL_ERROR)

        # Clear any pending data for this socket
        self._rx_pending[sock_num] = 0


    def disconnect(self):
        
        utime.sleep(1)
        ret = self.send_at(b"AT+CFUN=0", timeout=30000)
        if not ret:
            log_status("[SARA] disconnect:Timeout send AT+CFUN=0 failed", LEVEL_ERROR)
            self.connect_state = "idle"
            return
        resp = self.last_response
        log_status(f"[SARA] disconnect:Modem CFUN=0 OK {resp}", level=LEVEL_INFO)

        self.connect_state = "idle"

        
# TEST CODE
if __name__ == "__main__":
    from micro_socket import MicroSocket
    from micro_http_client import MicroHttpClient
    import os
    
    log_status("=== SARA-R410/R510 LTE modules TEST START ===", LEVEL_INFO)
    
    modem = SaraR(debug=True)

    modem.initialize()
    modem.get_imsi()
    modem.get_imei()
    modem.get_signal_strength()

    # --- Network connection ---
    while True:
        result = modem.connect_step('soracom.io', 'sora', 'sora', 1)
        if result is True:
            log_status("Connect!")
            break
        elif result is None:
            log_status("Connection failed")
            raise SystemExit
        utime.sleep_ms(10)

    modem.init_rtc()
    socket = MicroSocket(modem)
    http_client = MicroHttpClient(socket)

    # --- test payload ---
    path = "/test_file.txt"
    with open(path, "wb") as f:
        f.write(b"HELLO MicroSocket\n" * 20)

    filesize = os.stat(path)[6]

    # --- socket ---
    HOST = "harvest-files.soracom.io"
    socket = MicroSocket(modem)

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

    socket.poll()
    socket.poll()
    socket.recv()

    socket.close()
    modem.disconnect()


