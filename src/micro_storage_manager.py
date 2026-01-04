"""
File        : rpi_pico2_utils.py
Description : Unified storage manager for MicroPython environments (Raspberry Pi Pico2 etc).
              Provides mounting/unmounting, file append, log rotation, directory utilities, and
              size management for SD cards on Raspberry Pi Pico or compatible boards.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01
              Rev. 0.91  2026-01-04
Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# micro_storage_manager.py
from machine import Pin, SPI
import os
import utime
import sdcard
import _thread
from micro_logger import log_status, LEVEL_DEBUG2, LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR


class MicroStorageManager:
    """Thread-safe SD card storage manager."""

    def __init__(
        self,
        mount_path="/sd",
        log_dir="log",
        filename="temp.log",
        spi_pins_list=None,
        spi_id=0,
        spi_baudrate=25_000_000,
    ):
        """Initialize storage manager with optional SPI configurations."""
        self.mount_path = mount_path
        self.log_dir = log_dir
        self.filename = filename
        self.spi_id = spi_id
        self.spi_baudrate = spi_baudrate
        self.spi_pins_list = spi_pins_list or [
            {"sck": 2, "mosi": 3, "miso": 4, "cs": 5, "type": "B1"},
            {"sck": 18, "mosi": 19, "miso": 16, "cs": 17, "type": "B2"},
        ]
        self.sd = None
        self.mounted = False
        self._lock = _thread.allocate_lock()

    def mount(self) -> bool:
        """Attempt to mount SD card. Returns True if successful."""
        if self.mounted:
            return True
        for pins in self.spi_pins_list:
            try:
                spi = SPI(
                    self.spi_id,
                    baudrate=self.spi_baudrate,
                    sck=Pin(pins["sck"]),
                    mosi=Pin(pins["mosi"]),
                    miso=Pin(pins["miso"]),
                )
                self.sd = sdcard.SDCard(spi, Pin(pins["cs"]))
                os.mount(self.sd, self.mount_path)
                self._ensure_dir(self.mount_path)
                self._ensure_dir(self.log_path)
                self.mounted = True
                log_status(f"[STMG] SD mounted: {pins}", LEVEL_INFO)
                return True
            except Exception as e:
                log_status(f"[STMG] SD mount failed {pins}: {e}", LEVEL_WARN)
        log_status("[STMG] SD mount failed: no valid SPI configuration", LEVEL_ERROR)
        return False

    def unmount(self) -> bool:
        """Unmount SD card. Returns True if successful."""
        if not self.mounted:
            return True
        try:
            with self._lock:
                os.umount(self.mount_path)
                self.mounted = False
            log_status("[STMG] SD unmounted", LEVEL_INFO)
            return True
        except Exception as e:
            log_status(f"[STMG] SD unmount failed: {e}", LEVEL_ERROR)
            return False

    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    @property
    def log_path(self) -> str:
        """Return log directory path."""
        return f"{self.mount_path}/{self.log_dir}"

    @property
    def temp_file(self) -> str:
        """Return temporary log file path."""
        return f"{self.log_path}/{self.filename}"

    def get_log_path(self, filename) -> str:
        """Return full path for a log file."""
        return f"{self.log_path}/{filename}"

    def append_file(self, path: str, data) -> int:
        """Append data to a file. Returns bytes written."""
        if not self.mounted:
            log_status("[STMG] append_file: SD not mounted", LEVEL_ERROR)
            return 0
        try:
            with self._lock:
                mode = "ab" if isinstance(data, (bytes, bytearray)) else "a"
                with open(path, mode) as f:
                    written = f.write(data)
            return written if written else 0
        except Exception as e:
            log_status(f"[STMG] append_file failed {path}: {e}", LEVEL_ERROR)
            return 0

    def rotate(self, new_filename="new.log") -> str | None:
        """Rename temp log file to a new file. Returns new path or None."""
        if not self.mounted:
            return None
        if not self.file_exists(self.temp_file):
            log_status(f"[STMG] rotate_temp: {self.temp_file} not found", LEVEL_WARN)
            return None
        dst = f"{self.log_path}/{new_filename}"
        log_status(f"[STMG] Renaming {self.temp_file} -> {dst}", LEVEL_DEBUG2)
        try:
            with self._lock:
                self._ensure_dir(self.log_path)
                utime.sleep_ms(20)
                os.rename(self.temp_file, dst)
                utime.sleep_ms(20)
            log_status(f"[STMG] Rotated temp file {self.temp_file} -> {dst}", LEVEL_INFO)
            return dst
        except Exception as e:
            log_status(f"[STMG] rotate_temp failed: {e}", LEVEL_ERROR)
            return None

    def list_dir(self, path=None):
        """Return list of files and directories."""
        path = path or self.mount_path
        try:
            return os.listdir(path)
        except Exception as e:
            log_status(f"[STMG] list_dir failed {path}: {e}", LEVEL_ERROR)
            return []

    def get_dir_size(self, path: str) -> int:
        """Return total size of files in directory."""
        total = 0
        try:
            for name in os.listdir(path):
                full = f"{path}/{name}"
                st = os.stat(full)
                if (st[0] & 0x4000) == 0:  # not a directory
                    total += st[6]
        except Exception as e:
            log_status(f"get_dir_size failed {path}: {e}", LEVEL_ERROR)
        return total

    def cleanup_dir(self, path: str, max_bytes: int) -> bool:
        """Delete files if total size exceeds max_bytes."""
        size = self.get_dir_size(path)
        if size <= max_bytes:
            return True
        log_status(f"[STMG] cleanup_dir: size exceeded {size} > {max_bytes}", LEVEL_WARN)
        try:
            with self._lock:
                for name in os.listdir(path):
                    full = f"{path}/{name}"
                    st = os.stat(full)
                    if (st[0] & 0x4000) == 0:
                        os.remove(full)
                        log_status(f"Deleted {full}", LEVEL_INFO)
            return True
        except Exception as e:
            log_status(f"cleanup_dir failed: {e}", LEVEL_ERROR)
            return False

    def _ensure_dir(self, path: str):
        """Create directory if it does not exist."""
        try:
            os.mkdir(path)
        except OSError:
            pass

    def directry(self, path="."):
        """Print directory listing with size and modification time."""
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        try:
            os.stat(path)
        except Exception as e:
            print(f"[STMG] Error: Path '{path}' does not exist. {e}")
            return
        try:
            for name in os.listdir(path):
                full = f"{path}/{name}" if path != "/" else "/" + name
                try:
                    st = os.stat(full)
                    is_dir = (st[0] & 0x4000) != 0
                    if is_dir:
                        print(f"<DIR>  {name}")
                    else:
                        size = st[6]
                        mtime = st[8]
                        timestr = utime.localtime(mtime)
                        print(f"{size:10d}  {timestr[0]:04d}-{timestr[1]:02d}-{timestr[2]:02d} "
                              f"{timestr[3]:02d}:{timestr[4]:02d}:{timestr[5]:02d}  {name}")
                except Exception as e:
                    print(f"Error stat '{name}': {e}")
        except Exception as e:
            print(f"Error listing directory '{path}': {e}")



# Embedded TEST CODE (debug-first, mixed-in by design)
if __name__ == "__main__":
    import utime

    log_status("=== MicroStorageManager TEST START ===", LEVEL_INFO)

    if state.sd_mounted:
        os.umount("/sd")
    storage = MicroStorageManager()


    test_data = (
        f"/sd/log"
        f"test_"
        f"2026.log"
    )

    if not storage.mount():
        log_status("SD mount failed. Abort test.", LEVEL_ERROR)
    else:
        
        storage.directry(path="/sd/log")
        
        log_status("Writing temp file...", LEVEL_INFO)

        test_data = b"TEST_DATA_" * 100

        for i in range(3):
            written = storage.append_file(storage.temp_file, test_data)
            log_status(f"Write #{i}: {written} bytes", LEVEL_INFO)
            utime.sleep(1)

        if storage.file_exists(storage.temp_file):
            log_status("temp.log exists OK", LEVEL_INFO)
        else:
            log_status(f"{storage.temp_file} not found!", LEVEL_ERROR)

        log_status("Rotating temp file...", LEVEL_INFO)
        rotated = storage.rotate("new.log")

        if rotated:
            log_status(f"Rotated file: {rotated}", LEVEL_INFO)

        size = storage.get_dir_size(storage.log_path)
        log_status(f"Log directory size: {size} bytes", LEVEL_INFO)

        #log_status("Running cleanup_dir (force)...", LEVEL_WARN)
        #storage.cleanup_dir(storage.log_path, max_bytes=1)

        size_after = storage.get_dir_size(storage.log_path)
        log_status(f"Log directory size after cleanup: {size_after}", LEVEL_INFO)

        storage.unmount()

