"""
File        : micro_http_client.py
Description :This module provides a very small HTTP/1.1 helper designed for
             MicroPython environments. It focuses on constructing and sending
             HTTP request headers and receiving raw HTTP responses.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
              Rev. 0.91  2026-04-19
              Rev. 0.92  2026-05-06              
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# micro_http_client.py
import utime
import ujson
from micro_socket import MicroSocket
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR


class MicroHttpClient:
    """
    Minimal HTTP helper built on MicroSocket.

    Responsibility:
    - Build HTTP request line + headers
    - Send headers only
    - Receive raw HTTP response

    This class does NOT:
    - Send body (handled by caller / main.py)
    - Know chunk upload logic
    """

    def __init__(self, micro_socket: MicroSocket):
        """
        Initialize HTTP client.
        Args:micro_socket (MicroSocket): An initialized MicroSocket instance
        """
        self.sock = micro_socket
        self.host = None
        self.port = 80
        self._response_buffer = bytearray()

    def connect(self, host: str, port: int = 80) -> int:
        """
        Connect to HTTP server.
        """
        self.host = host
        self.port = port
        return self.sock.connect(host, port)

    def send_body(self, data: bytes) -> int:
        """
        Send raw HTTP body data.
        """
        return self.sock.send(data)

    def send_header(
        self,
        method: str = "POST",
        path: str = "/",
        header: str = None,
    ) -> bool:
        """
        Send HTTP request + header.
        Body must be sent by caller via MicroSocket.send().
        Injects Host header automatically if missing.
        """

        if not header:
            log_status("MicroHttpClient: header is empty", LEVEL_ERROR)
            return False

        # --- Guarantee Host header (HTTP/1.1 requirement) ---
        if self.host and "Host:" not in header:
            header = f"Host: {self.host}\r\n" + header

        # --- create request---
        data = (f"{method} {path}" + " HTTP/1.1\r\n" + header).encode()

        sent = self.sock.send(data)
        if sent != len(data):
            log_status("MicroHttpClient: header send failed", LEVEL_ERROR)
            return False

        log_status(f"[HTTP] headers sent:{data}", LEVEL_DEBUG2)
        return True

    def post_json(self, host, port, path, json_body: dict) -> bool:
        """
        Send a simple HTTP POST request with JSON body.
        """
        body = ujson.dumps(json_body).encode()

        if self.connect(host, port) < 0:
            return False

        header = (
            f"Host: {host}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )

        if not self.send_header(method="POST", path=path, header=header):
            self.close()
            return False

        sent = self.send_body(body)
        if sent != len(body):
            log_status("post_json: body send failed", LEVEL_ERROR)
            self.close()
            return False

        resp = self.read_response()
        self.close()
        return resp.startswith(b"HTTP/1.1 2")

    def read_response(self, timeout_ms: int = 10000) -> bytes:
        self._response_buffer = bytearray()
        start = utime.ticks_ms()
        last_recv = start

        while utime.ticks_diff(utime.ticks_ms(), start) < timeout_ms:

            self.sock.modem.poll_urc()
            self.sock.poll()
            data = self.sock.recv()

            if data:
                self._response_buffer.extend(data)
                last_recv = utime.ticks_ms()
            else:
                if utime.ticks_diff(utime.ticks_ms(), last_recv) > 3000:
                    break

            utime.sleep_ms(20)

        return bytes(self._response_buffer)

    def close(self):
        """
        Close underlying socket.
        """
        self.sock.close()
        
# TEST CODE
if __name__ == "__main__":
    import utime, os
    from ublox_sara_r import SaraR
    from micro_socket import MicroSocket
    from micro_logger import log_status, LEVEL_INFO

    modem = SaraR(debug=True)

    while True:
        r = modem.connect('soracom.io', 'sora', 'sora', 1)
        if r is True:
            log_status("Network connected", LEVEL_INFO)
            break
        elif r is None:
            raise SystemExit("Network failed")
        utime.sleep_ms(500)

    # --- test payload ---
    file_path = "/test_file.txt"
    with open(file_path, "wb") as f:
        f.write(b"HELLO MicroHttpClient\n" * 20)

    filesize = os.stat(file_path)[6]

    # --- socket / http ---
    HOST = "harvest-files.soracom.io"

    msock = MicroSocket(modem)
    http = MicroHttpClient(msock)

    if http.connect(HOST, 80) < 0:
        raise SystemExit("Socket connect failed")

    method="POST"
    path="/"

    header = (
        f"Host: {HOST}\r\n"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {filesize}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    # --- send headers only ---
    if not http.send_header( method, path, header):
        raise SystemExit("Send HTTP Header failed")

    # --- send body  ---
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            sent = http.send_body(chunk)
            if sent <= 0:
                raise SystemExit("send_body failed")
            utime.sleep_ms(50)

    # --- receive response ---
    utime.sleep_ms(1000)
    resp = http.read_response(timeout_ms=10000)
    if resp:
        print(resp.decode())

    modem.disconnect()