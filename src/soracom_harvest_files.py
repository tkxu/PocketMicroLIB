"""
File        : soracom_harvest_files.py
Description :Non-blocking, chunked file uploader for SORACOM Harvest Files on MicroPython. Supports retries, wait handling, and robust HTTP response processing.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# soracom_harvest_files.py
import os
import utime
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR


class SoracomHarvestFiles:
    """
    Non-blocking Harvest Files uploader (state machine)

    - start() + tick()
    - chunked body send
    - retry / wait / abort handling
    """

    HOST = "harvest-files.soracom.io"
    PORT = 80
    CHUNK_SIZE = 1024

    # --- States ---
    HF_IDLE     = 0
    HF_PREPARE  = 1
    HF_OPEN     = 2
    HF_SENDING  = 3
    HF_CLOSING  = 4
    HF_DONE     = 5
    HF_ABORT    = 6
    HF_WAIT     = 7

    def __init__(self, http_client):
        
        self.http = http_client

        self.state = self.HF_IDLE

        self.filename = ""
        self.file = None
        self.filesize = 0

        self.buf = b""
        self.buf_offset = 0

        self.sent_bytes = 0

        self.retry = 0
        self.header_retry = 0
        self.next_time = 0

        self.last_response = b""

    # Public API
    def start(self, filename) -> bool:
        if self.state != self.HF_IDLE:
            log_status("[SORA] start called but not IDLE", LEVEL_WARN)
            return False

        self.filename = filename
        self.sent_bytes = 0
        self.state = self.HF_PREPARE
        return True

    def close(self):
        self.http.close()

    def _send_chunk(self, data: bytes) -> int:
        try:
            return self.http.send_body(data)
        except Exception as e:
            log_status(f"[SORA] send chunk error {e}", LEVEL_WARN)
            return 0
    
    def tick(self):
        now = utime.time()

        if self.state == self.HF_IDLE:
            return

        elif self.state == self.HF_PREPARE:
            log_status("[SORA] PREPARE start", LEVEL_DEBUG)

            # --- close existing file ---
            if getattr(self, "file", None):
                try:
                    self.file.close()
                except Exception as e:
                    log_status(f"[SORA] file close error {e}", LEVEL_WARN)
                self.file = None

            # --- stat & open with retry ---
            for attempt in range(5):
                try:
                    st = os.stat(self.filename)
                    self.filesize = st[6]

                    log_status(
                        f"[SORA] PREPARE stat ok size={self.filesize}",
                        LEVEL_DEBUG,
                    )

                    if self.filesize <= 0:
                        log_status("[SORA] file size is zero", LEVEL_WARN)
                        self.state = self.HF_DONE
                        return

                    self.file = open(self.filename, "rb")
                    log_status("[SORA] File opened", LEVEL_DEBUG)
                    self.state = self.HF_OPEN
                    return

                except OSError as e:
                    log_status(
                        f"[SORA] PREPARE attempt {attempt+1}/5 failed {e}",
                        LEVEL_WARN,
                    )
                    utime.sleep_ms(50)

            log_status("[SORA] PREPARE failed after retries", LEVEL_ERROR)
            self.state = self.HF_WAIT
            self.next_time = now + 60

        elif self.state == self.HF_OPEN:
            log_status("[SORA] OPEN sending headers", LEVEL_DEBUG)

            if self._post():
                self.buf = b""
                self.buf_offset = 0
                self.sent_bytes = 0
                self.retry = 0
                log_status("[SORA] Upload start", LEVEL_INFO)
                self.state = self.HF_SENDING
            else:
                self.header_retry += 1
                log_status(
                    f"[SORA] OPEN failed retry={self.header_retry}",
                    LEVEL_WARN,
                )
                if self.header_retry >= 3:
                    self.state = self.HF_ABORT
                else:
                    self.state = self.HF_WAIT
                    self.next_time = now + 3

        elif self.state == self.HF_SENDING:
            if not self.buf:
                self.buf = self.file.read(self.CHUNK_SIZE)
                self.buf_offset = 0

                if not self.buf:
                    log_status(
                        f"[SORA] Upload finished {self.sent_bytes}/{self.filesize}",
                        LEVEL_INFO,
                    )
                    self.state = self.HF_CLOSING
                    return

            sent = self._send_chunk(self.buf[self.buf_offset:])

            if sent > 0:
                self.buf_offset += sent
                self.sent_bytes += sent
                self.retry = 0

                log_status(
                    f"[SORA] SEND {self.sent_bytes}/{self.filesize}",
                    LEVEL_DEBUG2,
                )

                if self.buf_offset >= len(self.buf):
                    self.buf = b""
                    self.buf_offset = 0

            else:
                self.retry += 1
                log_status(
                    f"[SORA] SEND failed retry={self.retry}",
                    LEVEL_WARN,
                )
                if self.retry >= 20:
                    self.state = self.HF_ABORT

        elif self.state == self.HF_CLOSING:
            log_status("[SORA] CLOSING wait response", LEVEL_DEBUG)

            try:
                self.last_response = self.http.read_response(timeout_ms=10000)
                log_status(f"[SORA] read response: {self.last_response}", LEVEL_DEBUG2)
            except Exception as e:
                log_status(f"[SORA] response read error {e}", LEVEL_WARN)
                self.last_response = b""

            self.state = self.HF_DONE

        elif self.state == self.HF_DONE:
            log_status(f"[SORA] HTTP done: {self.last_response}", level=LEVEL_DEBUG)

            try:
                if self.file:
                    self.file.close()
                    self.file = None

                if self.last_response.startswith(b"HTTP/1.1 200") or \
                   self.last_response.startswith(b"HTTP/1.1 201"):
                    log_status("[SORA] HTTP Response OK", LEVEL_INFO)
                else:
                    log_status(
                        f"[SORA] HTTP Response NG ={self.last_response[:64]}",
                        LEVEL_WARN,
                    )
                self.http.close()

            except Exception as e:
                log_status(f"[SORA] DONE cleanup error {e}", LEVEL_WARN)

            self.state = self.HF_IDLE

        elif self.state == self.HF_ABORT:
            log_status(
                f"[SORA] ABORT sent={self.sent_bytes}/{self.filesize}",
                LEVEL_ERROR,
            )

            try:
                if self.file:
                    self.file.close()
            except:
                pass

            self.http.close()
            self.state = self.HF_WAIT
            self.next_time = now + 300

        elif self.state == self.HF_WAIT:
            if now >= self.next_time:
                log_status("[SORA] WAIT timeout -> PREPARE", LEVEL_DEBUG)
                self.retry = 0
                self.header_retry = 0
                self.state = self.HF_PREPARE


    def is_busy(self) -> bool:
        return self.state != self.HF_IDLE

    def get_progress_bytes(self):
        return self.sent_bytes, self.filesize


    # Internal helpers
    def _post(self, path="/") -> bool:
        sock = self.http.connect(self.HOST, self.PORT)
        if sock < 0:
            return False

        header = (
            f"Host: {self.HOST}\r\n"
            "Content-Type: application/octet-stream\r\n"
            f"Content-Length: {self.filesize}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
    
        ok = self.http.send_header(
            method="POST",
            path=path,
            header=header,
        )

        if not ok:
            self.http.close()
            return False

        return True


# TEST CODE
if __name__ == "__main__":
    from machine import UART, Pin
    import utime
    import os

    from micro_socket import MicroSocket
    from ublox_sara_r import SaraR
    from micro_http_client import MicroHttpClient
    from soracom_harvest_files import SoracomHarvestFiles
    from micro_logger import log_status, LEVEL_INFO, LEVEL_ERROR

    log_status("soracom_harvest_files.py: start")
    
    modem = SaraR(debug=True)
    modem.connect('soracom.io', 'sora', 'sora', 1)

    # Socket / HTTP / HarvestFiles
    socket = MicroSocket(modem)
    http_client = MicroHttpClient(socket)
    harvest = SoracomHarvestFiles(http_client)

    # Prepare test file
    test_filename = "/test_file.txt"

    try:
        with open(test_filename, "wb") as f:
            f.write(b"HELLO SORACOM HARVEST FILES\n" * 50)
        log_status("Test file created", LEVEL_INFO)
    except Exception as e:
        log_status(f"File create failed: {e}", LEVEL_ERROR)
        raise SystemExit

    # Start upload
    if not harvest.start(test_filename):
        log_status("SoracomHarvestFiles start failed", LEVEL_ERROR)
        raise SystemExit

    log_status("SoracomHarvestFiles upload started", LEVEL_INFO)

    # Tick loop
    start_time = utime.time()
    TIMEOUT_SEC = 60  # 1 minutes

    while True:
        harvest.tick()
        utime.sleep_ms(100)

        if harvest.state == harvest.HF_IDLE:
            log_status("SoracomHarvestFiles upload finished", LEVEL_INFO)
            break

        if utime.time() - start_time > TIMEOUT_SEC:
            log_status("SoracomHarvestFiles upload timeout", LEVEL_ERROR)
            break

    modem.disconnect()
