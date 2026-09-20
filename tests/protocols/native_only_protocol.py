"""Read the current device registry; shared by direct preparation and log oracles."""

import ctypes
import os

NATIVE_ONLY = -3


class Entry(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_int),
        ("pid", ctypes.c_int),
        ("tgid", ctypes.c_int),
        ("lock_kind", ctypes.c_int),
        ("rip", ctypes.c_ulong),
        ("code", ctypes.c_ulong),
        ("jump_from", ctypes.c_ulong),
        ("target", ctypes.c_ulong),
        ("entry_abi", ctypes.c_uint),
        ("padding", ctypes.c_byte * 12),
    ]


def entries():
    fd = os.open("/dev/kd_dev", os.O_RDONLY)
    try:
        data = os.read(fd, 511 * ctypes.sizeof(Entry))
    finally:
        os.close(fd)
    assert len(data) % ctypes.sizeof(Entry) == 0, "invalid entry layout"
    return [
        Entry.from_buffer_copy(data, i)
        for i in range(0, len(data), ctypes.sizeof(Entry))
    ]
