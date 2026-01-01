"""
File        : micro_zip.py
Description : micro_zip.py is a minimal ZIP archive generator written for MicroPython environments where the standard zipfile module is unavailable.
              It supports creating store-only (no compression) ZIP files from existing files using raw ZIP structures.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#micro_zip.py
import os
import time

def write_le16(n):
    """
    Convert an integer to 2-byte little-endian format.
    Args: n (int): Integer value (0–65535)
    Returns: bytes: 2-byte little-endian representation
    """
    return bytes([n & 0xFF, (n >> 8) & 0xFF])


def write_le32(n):
    """
    Convert an integer to 4-byte little-endian format.
    Args: n (int): Integer value

    Returns: bytes: 4-byte little-endian representation
    """
    return bytes([
        n & 0xFF,
        (n >> 8) & 0xFF,
        (n >> 16) & 0xFF,
        (n >> 24) & 0xFF
    ])


def unix_to_dos_time(t=None):
    """
    Convert Unix time to DOS date/time format used in ZIP headers.
    Args: t (tuple | None): time.localtime() tuple.
          If None, current local time is used.

    Returns: tuple[int, int]: (dos_date, dos_time)
    """
    if t is None:
        t = time.localtime()

    year, month, day, hour, minute, second = t[0:6]

    if year < 1980:
        year = 1980

    dos_date = ((year - 1980) << 9) | (month << 5) | day
    dos_time = (hour << 11) | (minute << 5) | (second // 2)

    return dos_date, dos_time


def zip_create(zip_path, files):
    """
    Create a ZIP archive containing the specified files.
    This function writes a ZIP file using the STORE method (no compression).
    ZIP headers are written directly without using the zipfile module.
    Args:zip_path (str): Output ZIP file path
        files (list[str]): List of file paths to include in the archive
    Notes: - CRC32 is set to 0 (binascii.crc32 is not used)
           - Directory entries are not supported
          - File paths are stored as UTF-8 as-is
    """
    central_dir = []
    offset = 0

    with open(zip_path, "wb") as zf:

        for file in files:
            try:
                with open(file, "rb") as f:
                    data = f.read()
            except OSError as e:
                print("Read failed:", file, e)
                continue

            crc = 0
            size = len(data)
            name_bytes = file.encode("utf-8")
            dos_date, dos_time = unix_to_dos_time()

            # Local File Header
            zf.write(b"PK\x03\x04")
            zf.write(write_le16(20))      # version needed
            zf.write(write_le16(0))       # flags
            zf.write(write_le16(0))       # compression (STORE)
            zf.write(write_le16(dos_time))
            zf.write(write_le16(dos_date))
            zf.write(write_le32(crc))
            zf.write(write_le32(size))    # compressed size
            zf.write(write_le32(size))    # uncompressed size
            zf.write(write_le16(len(name_bytes)))
            zf.write(write_le16(0))       # extra field length
            zf.write(name_bytes)
            zf.write(data)

            central_dir.append((file, offset, size, crc, dos_date, dos_time))
            offset = zf.tell()

        cd_offset = offset

        # Central Directory
        for file, off, size, crc, dos_date, dos_time in central_dir:
            name_bytes = file.encode("utf-8")

            zf.write(b"PK\x01\x02")
            zf.write(write_le16(20))      # version made by
            zf.write(write_le16(20))      # version needed
            zf.write(write_le16(0))       # flags
            zf.write(write_le16(0))       # compression
            zf.write(write_le16(dos_time))
            zf.write(write_le16(dos_date))
            zf.write(write_le32(crc))
            zf.write(write_le32(size))
            zf.write(write_le32(size))
            zf.write(write_le16(len(name_bytes)))
            zf.write(write_le16(0))       # extra length
            zf.write(write_le16(0))       # comment length
            zf.write(write_le16(0))       # disk start
            zf.write(write_le16(0))       # internal attributes
            zf.write(write_le32(0))       # external attributes
            zf.write(write_le32(off))     # relative offset
            zf.write(name_bytes)

        cd_size = zf.tell() - cd_offset

        # End of Central Directory
        zf.write(b"PK\x05\x06")
        zf.write(write_le16(0))           # disk number
        zf.write(write_le16(0))           # disk start
        zf.write(write_le16(len(central_dir)))
        zf.write(write_le16(len(central_dir)))
        zf.write(write_le32(cd_size))
        zf.write(write_le32(cd_offset))
        zf.write(write_le16(0))           # comment length

    print("ZIP created:", zip_path)


# Test code
if __name__ == "__main__":

    files = []

    for name in os.listdir("/"):
        if name.endswith(".py") or name.endswith(".txt"):
            try:
                st = os.stat("/" + name)
                if st[0] & 0x4000:  # skip directories
                    continue
                files.append(name)
            except Exception as e:
                print("stat failed:", name, e)

    if not files:
        print("No target files")

    zip_create("fw.zip", files)
