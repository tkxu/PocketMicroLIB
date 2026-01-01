"""
File        : micro_socket.py
Description : 
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#micro_socket.py
import utime
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR
from ublox_sara_r import SaraR

class MicroSocket:
    def __init__(self, modem):
        self.modem = modem
        self.sock_num = -1
        self._rx_buffer = bytearray()

    def connect(self, host: str, port: int) -> int:
        """
        Create and connect a socket via modem.
        Returns socket number on success, -1 on failure.
        """
        sock_num = self.modem.socket_create()
        if sock_num < 0:
            log_status("[SOCK] socket_create failed", LEVEL_ERROR)
            return -1

        if not self.modem.socket_connect(sock_num, host, port):
            log_status("[SOCK] socket_connect failed", LEVEL_ERROR)
            self.modem.socket_close(sock_num)
            return -1

        self.sock_num = sock_num
        log_status(f"[SOCK] Connected: host: {host}, port: {port}", LEVEL_INFO)
        return sock_num

    def send(self, data: bytes) -> int:
        res = self.modem.socket_send(data)
        #log_status(f"[SOCK] send body: {res}", LEVEL_INFO)
        return res

    # receive
    def poll(self):
        data = self.modem.socket_recv(self.sock_num, 1024)
        #log_status(f"[SOCK] poll", LEVEL_DEBUG)
        if data:
            log_status(f"[SOCK] poll = {data.decode()}", LEVEL_DEBUG2)
            self._rx_buffer.extend(data)
            return True
        return False

    def recv(self, size=1024):
        if not self._rx_buffer:
            return b""
        data = self._rx_buffer[:size]
        self._rx_buffer = self._rx_buffer[size:]
        return data

    def available(self) -> int:
        return len(self._rx_buffer)

    def clear(self):
        self._rx_buffer[:] = b""

    def close(self):
        log_status(f"[SOCK] close", LEVEL_INFO)
        if self.sock_num >= 0:
            self.modem.socket_close(self.sock_num)
        self.sock_num = -1
        self.clear()


# TEST CODE
if __name__ == "__main__":
    import utime, os
    from ublox_sara_r import SaraR
    from micro_logger import log_status, LEVEL_INFO

    log_status("=== MicroSocket TEST START ===", LEVEL_INFO)

    modem = SaraR(debug=True)
    modem.initialize()

    # --- Network connection ---
    while True:
        result = modem.connect_step('soracom.io', 'sora', 'sora', 1)
        if result is True:
            log_status("Soracom Connect!")
            break
        elif result is None:
            log_status("Connection failed")
            raise SystemExit
        utime.sleep_ms(1000)

    # --- test payload ---
    path = "/test_file.txt"
    with open(path, "wb") as f:
        f.write(b"HELLO MicroSocket\n" * 20)

    filesize = os.stat(path)[6]

    # --- socket ---
    HOST = "harvest-files.soracom.io"
    micro_socket = MicroSocket(modem)

    if micro_socket.connect(HOST, 80) < 0:
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

    micro_socket.send(method.encode()+header.encode())
    print(method + header)

    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            micro_socket.send(chunk)
            utime.sleep_ms(100)

    start = utime.ticks_ms()

    while utime.ticks_diff(utime.ticks_ms(), start) < 10000:
        micro_socket.poll()
        data = micro_socket.recv()


#    utime.sleep_ms(10000)

    micro_socket.close()
    modem.disconnect()
