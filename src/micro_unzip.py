"""
File        : micro_unzip.py
Description : Minimal ZIP extractor for MicroPython supporting STORE-only archives.
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
#micro_unzip.py
import os
import utime


def read_le_uint16(b, offset=0):
    """
    Read a 16-bit unsigned integer from little-endian bytes.
    Args: b (bytes): Source byte buffer
          offset (int): Offset in buffer
    Returns: int: Parsed 16-bit integer
    """
    return b[offset] | (b[offset + 1] << 8)


def read_le_uint32(b, offset=0):
    """
    Read a 32-bit unsigned integer from little-endian bytes.
    Args: b (bytes): Source byte buffer
          offset (int): Offset in buffer
    Returns:
        int: Parsed 32-bit integer
    """
    return (
        b[offset] |
        (b[offset + 1] << 8) |
        (b[offset + 2] << 16) |
        (b[offset + 3] << 24)
    )


def make_dirs(path):
    """
    Recursively create directories (MicroPython compatible).
    This function mimics os.makedirs() behavior, which may not be
    available in some MicroPython environments.
    Args: path (str): Directory path to create
    """
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        subdir = "/".join(parts[:i])
        if not subdir:
            continue
        try:
            st = os.stat(subdir)
            if not (st[0] & 0x4000):
                continue  # Path exists but is not a directory
        except OSError:
            try:
                os.mkdir(subdir)
            except OSError:
                pass


def unzip(zip_path, extract_dir="."):
    """
    Extract a ZIP archive using STORE method only.
    Args: zip_path (str): Path to ZIP file
          extract_dir (str): Output directory
    Returns: bool: True on success, False on error
    Notes: - Only local file headers are parsed
           - Compression method must be 0 (STORE)
           - CRC is ignored
    """
    try:
        f = open(zip_path, "rb")
    except OSError as e:
        print("Failed to open ZIP file:", e)
        return False

    while True:
        sig = f.read(4)
        if len(sig) < 4 or sig != b"PK\x03\x04":
            break  # End of ZIP or invalid signature

        header = f.read(26)
        if len(header) < 26:
            print("Failed to read ZIP header")
            break

        compression_method = read_le_uint16(header, 4)
        compressed_size = read_le_uint32(header, 14)
        filename_len = read_le_uint16(header, 22)
        extra_len = read_le_uint16(header, 24)

        filename = f.read(filename_len).decode("utf-8")
        f.read(extra_len)

        if compression_method != 0:
            print("Unsupported compression:", compression_method, filename)
            f.read(compressed_size)
            continue

        data = f.read(compressed_size)

        out_path = extract_dir + "/" + filename
        dir_path = "/".join(out_path.split("/")[:-1])
        if dir_path:
            make_dirs(dir_path)

        try:
            with open(out_path, "wb") as out_f:
                out_f.write(data)
            print("Extracted:", out_path)
        except OSError as e:
            print("Write failed:", out_path, e)

    f.close()
    return True


def directory(path="."):
    """
    List files and directories in the specified path.
    Directories are shown as <DIR>.
    Files display size and last modification time.
    Args:
        path (str): Directory path
    """
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    try:
        print("Directory listing for '%s':" % path)
        os.stat(path)
    except Exception as e:
        print("Path error:", e)
        return

    try:
        for name in os.listdir(path):
            if path == "/":
                full_path = "/" + name
            else:
                full_path = path + "/" + name

            try:
                st = os.stat(full_path)
                is_dir = (st[0] & 0x4000) != 0

                if is_dir:
                    print("<DIR>  ", name)
                else:
                    size = st[6]
                    mtime = st[8]
                    t = utime.localtime(mtime)
                    ts = "%04d-%02d-%02d %02d:%02d:%02d" % t[0:6]
                    print("%10d  %s  %s" % (size, ts, name))
            except Exception as e:
                print("stat error:", name, e)

    except Exception as e:
        print("listdir error:", e)


if __name__ == "__main__":
    directory()
    unzip("fw.zip")
    directory()
