"""Retain the device writer and pin source residency before real text reads.

Source pins outlive the writer, until terminal retirement drains every holder.
Mutex images use a separately negotiated immutable publication contract.
"""

import argparse
import errno
import fcntl
import json
import os
import stat
import struct
import sys
from contextlib import contextmanager

DEVICE = "/dev/kd_dev"
# x86-64 Linux ioctl layout, checked against include/kd_source_api.h in tests.
PIN = 0x40104B70
INFO = 0x80104B71
RETIRE = 0x4B72
CAPS = 0x80104B73
CAPS_VERSION = 4
CAP_MUTEX_STACK = 1
CAP_PERCPU_MODULE = 2
CAP_MUTEX_IMAGES = 8
MUTEX_STACK_BYTES = 256
PERCPU_MODULE_BYTES = 8192
PERCPU_ALIGNMENT = 4
OPEN, DRAINING, RETIRED = range(3)
INFO_STRUCT = struct.Struct("<IIII")
CAPS_STRUCT = struct.Struct("<IIII")
RANGE_STRUCT = struct.Struct("<QQ")
_fd = None
_mutex_stack_bytes = 0
_percpu_module_bytes = 0


class SourceRefused(RuntimeError):
    """A source dependency cannot remain resident for this JIT session."""


def info(fd):
    packet = bytearray(INFO_STRUCT.size)
    fcntl.ioctl(fd, INFO, packet, True)
    return dict(
        zip(("state", "modules", "frames", "writers"), INFO_STRUCT.unpack(packet))
    )


def require():
    """Do not allow a real kcore read outside the translator's device lease."""
    if _fd is None:
        raise RuntimeError("kernel text read requires an active kd_dev session")
    return _fd


def query_capabilities(fd):
    """Read one provider's guarantees; unknown contracts stay disabled.

    A sentinel catches a provider that returns success without a complete
    packet. ENOTTY means this otherwise valid source provider predates CAPS;
    I/O/device failures are not compatibility and must still abort inspection.
    Version 1 can still supply the optional mutex bound, never the module
    range required by current translation. Raw queries are not a lease; use
    the cached getters after session() validates the actual read/write cdev.
    """
    disabled = {"mutex_stack_bytes": 0, "percpu_module_bytes": 0, "mutex_images": False}
    packet = bytearray(b"\xff" * CAPS_STRUCT.size)
    try:
        result = fcntl.ioctl(fd, CAPS, packet, True)
    except OSError as error:
        if error.errno != errno.ENOTTY:
            raise
        print(
            "[KD_JIT][WARN] reason=JIT_CAPABILITY_UNAVAILABLE "
            "mutex_stack_bytes=0 percpu_module_bytes=0",
            file=sys.stderr,
        )
        return disabled
    if result == 0 and len(packet) == CAPS_STRUCT.size:
        version, features, stack_bytes, module_bytes = CAPS_STRUCT.unpack(packet)
        known = CAP_MUTEX_STACK | (CAP_PERCPU_MODULE if version in (2, 3, CAPS_VERSION) else 0)
        if version == 3:
            known |= 4  # historical owned-image capability, not this backend
        if version == CAPS_VERSION:
            known |= CAP_MUTEX_IMAGES
        if (
            version in (1, 2, 3, CAPS_VERSION)
            and not features & ~known
            and stack_bytes == (MUTEX_STACK_BYTES if features & CAP_MUTEX_STACK else 0)
            and module_bytes
            == (PERCPU_MODULE_BYTES if features & CAP_PERCPU_MODULE else 0)
        ):
            return {
                "mutex_stack_bytes": stack_bytes,
                "percpu_module_bytes": module_bytes,
                "mutex_images": bool(features & CAP_MUTEX_IMAGES),
            }
    print(
        f"[KD_JIT][WARN] reason=JIT_CAPABILITY_INVALID "
        f"mutex_stack_bytes=0 percpu_module_bytes=0 "
        f"result={result} packet={packet.hex()}",
        file=sys.stderr,
    )
    return disabled


def query_mutex_stack_bytes(fd):
    """Compatibility query for source-retirement observers, not admission."""
    return query_capabilities(fd)["mutex_stack_bytes"]


def mutex_stack_bytes():
    """Only this active lease's negotiated immutable bound may guide analysis."""
    require()
    return _mutex_stack_bytes


def percpu_module_bytes():
    """Do not let an older/unknown provider silently omit module range checks."""
    require()
    if not _percpu_module_bytes:
        raise RuntimeError(
            "module per-CPU range capability unavailable; "
            "translation requires a compatible kdlock provider"
        )
    return _percpu_module_bytes


def pin_range(address, size):
    """The writer lease spans this ioctl and the following kcore read."""
    try:
        fcntl.ioctl(require(), PIN, RANGE_STRUCT.pack(address, size))
    except OSError as error:
        if error.errno not in {errno.EPERM, errno.ESTALE, errno.ENOSPC, errno.EINVAL}:
            raise
        raise SourceRefused(
            f"source range cannot be pinned: address={address:#x} bytes={size} "
            f"errno={error.errno} ({error.strerror})"
        ) from error


@contextmanager
def session():
    global _fd, _mutex_stack_bytes, _percpu_module_bytes
    if _fd is not None:
        raise RuntimeError("kd_dev session is already active")
    inherited = os.environ.get("KD_DEVICE_FD")
    fd = None
    try:
        if inherited is None:
            # Direct CLI use must not leave inspection unleased either.
            fd = os.open(DEVICE, os.O_RDWR | os.O_CLOEXEC)
        else:
            parent_fd = int(inherited)
            if parent_fd < 3:
                raise ValueError("KD_DEVICE_FD must name a non-stdio descriptor")
            # An invalid inherited lease is an error, never permission to open
            # another provider. Later assembler/shell children need no lease.
            os.set_inheritable(parent_fd, False)
            fd = os.dup(parent_fd)
        opened, named = os.fstat(fd), os.stat(DEVICE)
        if (
            not stat.S_ISCHR(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_rdev)
            != (named.st_dev, named.st_ino, named.st_rdev)
            or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDWR
        ):
            raise RuntimeError("kd_dev session is not the current read/write device")
        # The source-session protocol is mandatory even when optional JIT
        # capabilities are absent. Reject incompatibility before reading text.
        # A previously leased writer can finish while closing; no new writer
        # opens or image publication are accepted once draining begins.
        if info(fd)["state"] not in (OPEN, DRAINING):
            raise RuntimeError("kd_dev source session is retired")
        # Query the same validated description once, before any text read.
        # Never reuse a prior session's capability or open another provider.
        caps = query_capabilities(fd)
        if not caps["mutex_images"]:
            raise RuntimeError("immutable legacy mutex image publication capability required")
        _mutex_stack_bytes = caps["mutex_stack_bytes"]
        _percpu_module_bytes = caps["percpu_module_bytes"]
        _fd = fd
        print(f"Translation device session: inherited={int(inherited is not None)}")
        print(
            f"Translation runtime capability: mutex_stack_bytes={_mutex_stack_bytes} "
            f"percpu_module_bytes={_percpu_module_bytes}"
        )
        yield fd
    finally:
        _fd = None
        _mutex_stack_bytes = 0
        _percpu_module_bytes = 0
        if fd is not None:
            os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect sources/runtime capability or terminally retire JIT sources"
    )
    parser.add_argument("command", choices=("status", "capabilities", "retire"))
    args = parser.parse_args(argv)
    # The control descriptor must be readonly, or it would keep retirement busy.
    fd = os.open(DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        if args.command == "capabilities":
            print(json.dumps(query_capabilities(fd), sort_keys=True))
            return 0
        if args.command == "retire":
            try:
                fcntl.ioctl(fd, RETIRE)
            except OSError:
                print(json.dumps(info(fd), sort_keys=True), file=sys.stderr)
                raise
        print(json.dumps(info(fd), sort_keys=True))
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as error:
        sys.exit(
            f"source control failed: {error}; retain modules until all holders drain"
        )
