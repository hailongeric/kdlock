"""Guest-only checks of the real kd_dev rejection protocol (no code execution)."""

import argparse
import ctypes
import errno
import json
import os
import time

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
        ("padding", ctypes.c_byte * 16),
    ]


class Packet(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_int),
        ("pid", ctypes.c_int),
        ("rip", ctypes.c_ulong),
        ("offset", ctypes.c_ulong),
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


def send(entry, status, offset=0, payload=b"", expected_errno=None):
    packet = bytes(Packet(status, entry.pid, entry.rip, offset)) + payload
    fd = os.open("/dev/kd_dev", os.O_WRONLY)
    try:
        try:
            count = os.write(fd, packet)
        except OSError as error:
            assert expected_errno == error.errno, (expected_errno, error)
        else:
            assert expected_errno is None, "forbidden packet was accepted"
            assert count == len(packet), "short status write"
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--all",
        action="store_true",
        help="require every registered entry to be native-only",
    )
    parser.add_argument(
        "--protocol", action="store_true", help="also check malformed and stale packets"
    )
    parser.add_argument("--lock-kind", choices=("spin", "mutex"))
    args = parser.parse_args()
    assert ctypes.sizeof(Entry) == 64 and ctypes.sizeof(Packet) == 24
    assert Entry.lock_kind.offset == 12 and Entry.rip.offset == 16
    deadline = time.monotonic() + args.timeout
    while True:
        snapshot = entries()
        assert all(entry.lock_kind in (1, 2) for entry in snapshot), (
            "invalid entry kind"
        )
        if args.lock_kind:
            kind = 1 if args.lock_kind == "spin" else 2
            snapshot = [entry for entry in snapshot if entry.lock_kind == kind]
        rejected = [entry for entry in snapshot if entry.status == NATIVE_ONLY]
        if rejected and (not args.all or len(rejected) == len(snapshot)):
            break
        assert time.monotonic() < deadline, "native-only publication timed out"
        time.sleep(0.1)

    if args.protocol:
        for entry in rejected:
            send(entry, NATIVE_ONLY)
            send(entry, NATIVE_ONLY, offset=1, expected_errno=errno.EINVAL)
            send(entry, NATIVE_ONLY, payload=b"x", expected_errno=errno.EINVAL)
            for status in (-1, 0):
                send(entry, status, payload=b"\x90", expected_errno=errno.EPERM)
            send(entry, 0, expected_errno=errno.EINVAL)
        after = {(entry.pid, entry.rip): entry.status for entry in entries()}
        assert all(after[(entry.pid, entry.rip)] == NATIVE_ONLY for entry in rejected)

    print(
        json.dumps(
            {
                "rejected": [
                    {
                        "pid": entry.pid,
                        "entry": hex(entry.rip),
                        "lock_kind": entry.lock_kind,
                    }
                    for entry in rejected
                ],
                "registered": len(snapshot),
                "protocol_checked": args.protocol,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
