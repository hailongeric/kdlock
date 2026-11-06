"""Retain the device writer and pin source residency before real text reads.

Source pins outlive the writer, until terminal retirement drains every holder.
Mutex images use a separately negotiated immutable publication contract.
"""

import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import re
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
CAPS_VERSION = 20
CAP_MUTEX_STACK = 1
CAP_PERCPU_MODULE = 2
CAP_MUTEX_IMAGES = 8
CAP_MUTEX_EXCLUSIVE = 16
CAP_NATIVE_ESCAPE = 32
CAP_ADDRESS_GUARD = 64
CAP_STRING_SERVICES = 128
CAP_STRING_WRITE = 256
CAP_AUDITED_STRINGS = 512
CAP_DIRECT_STRINGS = 1024
CAP_ROOT_NATIVE_ESCAPE = 2048
CAP_INDIRECT_CALL = 4096
CAP_ORIGIN_INSTRUCTION = 8192
CAP_ORIGIN_CALL = 16384
CAP_ORIGIN_MEMORY = 32768
CAP_ORIGIN_CONTEXT_READ = 65536
CAP_INDIRECT_TAIL = 131072
CAP_SOURCE_FRONTIER = 262144
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
_native_escape = False
_address_guard = False
_string_services = False
_string_write = False
_audited_strings = False
_direct_strings = False
_root_native_escape = False
_indirect_call = False
_origin_instruction = False
_origin_call = False
_origin_memory = False
_origin_context_read = False
_indirect_tail = False
_source_frontier = False
_source_frontier_extensions = False
_source_frontier_controls = False


class SourceRefused(RuntimeError):
    """A source dependency cannot remain resident for this JIT session."""

    def __init__(self, message, *, errno=None):
        super().__init__(message)
        self.errno = errno


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
    disabled = {"mutex_stack_bytes": 0, "percpu_module_bytes": 0,
                "mutex_images": False, "mutex_exclusive": False,
                "native_escape": False, "address_guard": False,
                "string_services": False, "string_write": False,
                "audited_strings": False, "direct_strings": False,
                "root_native_escape": False, "indirect_call": False,
                "origin_instruction": False, "origin_call": False,
                "origin_memory": False, "origin_context_read": False,
                "indirect_tail": False, "source_frontier": False}
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
        known = CAP_MUTEX_STACK | (CAP_PERCPU_MODULE if 2 <= version <= CAPS_VERSION else 0)
        if version == 3:
            known |= 4  # historical owned-image capability, not this backend
        if 4 <= version <= CAPS_VERSION:
            known |= CAP_MUTEX_IMAGES
        if 5 <= version <= CAPS_VERSION:
            known |= CAP_MUTEX_EXCLUSIVE
        if 6 <= version <= CAPS_VERSION:
            known |= CAP_NATIVE_ESCAPE
        if 7 <= version <= CAPS_VERSION:
            known |= CAP_ADDRESS_GUARD
        if 8 <= version <= CAPS_VERSION:
            known |= CAP_STRING_SERVICES
        if 9 <= version <= CAPS_VERSION:
            known |= CAP_STRING_WRITE
        if 10 <= version <= CAPS_VERSION:
            known |= CAP_AUDITED_STRINGS
        if 11 <= version <= CAPS_VERSION:
            known |= CAP_DIRECT_STRINGS
        if 12 <= version <= CAPS_VERSION:
            known |= CAP_ROOT_NATIVE_ESCAPE | CAP_INDIRECT_CALL
        if 13 <= version <= CAPS_VERSION:
            known |= CAP_ORIGIN_INSTRUCTION
        if 14 <= version <= CAPS_VERSION:
            known |= CAP_ORIGIN_CALL
        if 15 <= version <= CAPS_VERSION:
            known |= CAP_ORIGIN_MEMORY
        if 16 <= version <= CAPS_VERSION:
            known |= CAP_ORIGIN_CONTEXT_READ
        if 17 <= version <= CAPS_VERSION:
            known |= CAP_INDIRECT_TAIL
        if 18 <= version <= CAPS_VERSION:
            known |= CAP_SOURCE_FRONTIER
        if (
            1 <= version <= CAPS_VERSION
            and not features & ~known
            and (not features & CAP_AUDITED_STRINGS
                 or features & (CAP_STRING_SERVICES | CAP_STRING_WRITE))
            and (not features & CAP_DIRECT_STRINGS
                 or features & CAP_AUDITED_STRINGS)
            and (not features & CAP_ROOT_NATIVE_ESCAPE
                 or features & CAP_NATIVE_ESCAPE)
            and (not features & CAP_ORIGIN_INSTRUCTION
                 or features & CAP_NATIVE_ESCAPE)
            and (not features & CAP_ORIGIN_CALL
                 or features & (CAP_MUTEX_IMAGES | CAP_MUTEX_EXCLUSIVE)
                    == CAP_MUTEX_IMAGES | CAP_MUTEX_EXCLUSIVE)
            and (not features & CAP_ORIGIN_MEMORY
                 or features & CAP_ORIGIN_CALL)
            and (not features & CAP_ORIGIN_CONTEXT_READ
                 or features & CAP_ORIGIN_MEMORY)
            and (not features & CAP_INDIRECT_TAIL
                 or features & CAP_ORIGIN_CALL)
            and (not features & CAP_SOURCE_FRONTIER
                 or features & CAP_ORIGIN_CALL)
            and stack_bytes == (MUTEX_STACK_BYTES if features & CAP_MUTEX_STACK else 0)
            and module_bytes
            == (PERCPU_MODULE_BYTES if features & CAP_PERCPU_MODULE else 0)
        ):
            return {
                "mutex_stack_bytes": stack_bytes,
                "percpu_module_bytes": module_bytes,
                "mutex_images": bool(features & CAP_MUTEX_IMAGES),
                "mutex_exclusive": bool(features & CAP_MUTEX_EXCLUSIVE),
                "native_escape": bool(features & CAP_NATIVE_ESCAPE),
                "address_guard": bool(features & CAP_ADDRESS_GUARD),
                "string_services": bool(features & CAP_STRING_SERVICES),
                "string_write": bool(features & CAP_STRING_WRITE),
                "audited_strings": bool(features & CAP_AUDITED_STRINGS),
                "direct_strings": bool(features & CAP_DIRECT_STRINGS),
                "root_native_escape": bool(features & CAP_ROOT_NATIVE_ESCAPE),
                "indirect_call": bool(features & CAP_INDIRECT_CALL),
                "origin_instruction": bool(features & CAP_ORIGIN_INSTRUCTION),
                "origin_call": bool(features & CAP_ORIGIN_CALL),
                "origin_memory": bool(features & CAP_ORIGIN_MEMORY),
                "origin_context_read": bool(features & CAP_ORIGIN_CONTEXT_READ),
                "indirect_tail": bool(features & CAP_INDIRECT_TAIL),
                "source_frontier": bool(features & CAP_SOURCE_FRONTIER),
                "source_frontier_extensions": bool(version >= 19 and features & CAP_SOURCE_FRONTIER),
                "source_frontier_controls": bool(version >= 20 and features & CAP_SOURCE_FRONTIER),
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


def native_escape():
    """The original waiter's flags restore must be negotiated on this lease."""
    require()
    return _native_escape


def root_native_escape():
    """ABI1/3 retain one physical root until the original waiter's final ACK."""
    require()
    return _root_native_escape


def address_guard():
    """Use-site guards require the negotiated native-resume image contract."""
    require()
    return _address_guard


def string_services():
    """Read-only string API effects require this same provider lease."""
    require()
    return _string_services


def string_write():
    """The 64-byte writing effect is distinct from readonly strcmp."""
    require()
    return _string_write


def audited_strings():
    """Original string APIs rely on native caller guarantees, without preflight."""
    require()
    return _audited_strings


def direct_strings():
    """One pristine immutable spin invocation can call original APIs directly."""
    require()
    return _direct_strings


def indirect_call():
    """This leased provider validates CALL-only FULL exit 11 provenance."""
    require()
    return _indirect_call


def indirect_tail():
    """An owned near JMP can return a declared service to retained ABI2 code."""
    require()
    return _indirect_tail


def origin_instruction():
    """Only this v13 lease authorizes same-image original-task instructions."""
    require()
    return _origin_instruction


def origin_memory():
    """Only this lease authorizes original-CPU GS memory transactions."""
    require()
    return _origin_memory


def origin_context_read():
    """Guard exact origin preempt-count aliases before ordinary GS reads."""
    require()
    return _origin_context_read


def parse_service_calls(text, *, max_bytes=4096):
    """Parse one bounded registry snapshot, without inventing call contracts."""
    result, cookies = {}, set()
    if not isinstance(text, str) or len(text) > max_bytes or max_bytes > 32768:
        raise ValueError("invalid returning CALL registry snapshot")
    for line in text.splitlines():
        fields = line.split()
        if (len(fields) != 6 or
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", fields[-1])):
            raise ValueError("invalid returning CALL registry row")
        cookie, target = (int(value, 16) for value in fields[:2])
        nargs, result_kind, context_kind = (int(value, 10) for value in fields[2:5])
        if (not 0 < cookie < 1 << 64 or not 0 < target < 1 << 64 or
                cookie in cookies or target in result or not 0 <= nargs <= 6 or
                result_kind not in (1, 2) or context_kind not in range(1, 15) or
                (context_kind == 11 and
                 (nargs != 0 or result_kind != 2 or fields[-1] != '__stack_chk_fail')) or
                (context_kind in (12, 13) and (nargs != 1 or result_kind != 2)) or
                (context_kind == 14 and nargs == 0)):
            raise ValueError("inconsistent returning CALL registry row")
        cookies.add(cookie)
        result[target] = dict(cookie=cookie, nargs=nargs, result_kind=result_kind,
                              context_kind=context_kind, symbol=fields[-1])
    return result


def read_service_call_table(directory=None):
    """Read one exact bounded registry, with an old-provider alternative."""
    directory = Path(directory) if directory is not None else Path('/sys/module/kdlock_km/parameters')
    state_path = directory / 'service_call_table_state'
    try:
        before = state_path.read_text(encoding='ascii')
    except FileNotFoundError:
        text = (directory / 'service_call_table').read_text(encoding='ascii')
        parse_service_calls(text)
        return text
    fields = before.split()
    if len(fields) != 3 or not all(re.fullmatch(r'[0-9]+', value) for value in fields):
        raise ValueError('invalid Native discovery state')
    generation, slots, active = map(int, fields)
    if not 0 <= active <= slots <= 128 or not 0 <= generation <= 256:
        raise ValueError('Native discovery state exceeds its bounds')
    texts, cookies, targets, symbols = [], set(), set(), set()
    for page in range(8):
        text = (directory / f'service_call_page_{page}').read_text(encoding='ascii')
        rows = parse_service_calls(text)
        for target, row in rows.items():
            cookie = row['cookie']
            if (not page * 16 < cookie <= min(slots, (page + 1) * 16) or
                    cookie in cookies or target in targets or row['symbol'] in symbols):
                raise ValueError('Native discovery page membership differs')
            cookies.add(cookie); targets.add(target); symbols.add(row['symbol'])
        texts.append(text)
    if state_path.read_text(encoding='ascii') != before:
        raise ValueError('Native discovery changed while being read')
    if len(cookies) != active:
        raise ValueError('Native discovery active count differs')
    text = ''.join(texts)
    parse_service_calls(text, max_bytes=32768)
    return text


def service_calls():
    """Read exact declarations from the provider pinned by this device lease."""
    require()
    if not _origin_call:
        return {}
    return parse_service_calls(read_service_call_table(), max_bytes=32768)


def parse_rwsem_controls(text):
    """The facade declares operation identities; runtime resolves its object."""
    result = {}
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError('invalid rwsem control registry snapshot')
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError('invalid rwsem control registry row')
        target, operation, flags = int(fields[0], 16), int(fields[1]), int(fields[2])
        if (not 0 < target < 1 << 64 or target in result or
                operation not in range(1, 19) or flags & ~7 or
                not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$]*', fields[3])):
            raise ValueError('inconsistent rwsem control registry row')
        result[target] = dict(operation=operation, flags=flags, symbol=fields[3])
    return result


def rwsem_controls():
    require()
    if not _origin_call:
        return {}
    path = Path('/sys/module/kdlock_km/parameters/rwsem_control_table')
    return parse_rwsem_controls(path.read_text(encoding='ascii'))


def runtime_rwsem_controls(controls, returning_services):
    """Separate compiled state queries from ownership-changing controls.

    The provider exports synthetic row labels. Operation identities, rather
    than display names, keep these ordinary helpers out of every control and
    callee-exclusion set. Their actual downstream calls keep their own policy.
    """
    result = {}
    for target, control in controls.items():
        if control['operation'] in (14, 15, 16):
            if control['flags'] != 4:
                raise ValueError('compiled rwsem state query has incompatible control flags')
            if target in returning_services:
                raise ValueError('compiled rwsem state query is registered as a Native service')
            continue
        result[target] = control
    return result


def source_frontier():
    """Only this validated lease permits a permanent source frontier."""
    require()
    return _source_frontier


def source_frontier_extensions():
    """Revision 19 also recognizes the two added task-state instructions."""
    require()
    return _source_frontier_extensions


def source_frontier_controls():
    """Revision 20 adds exact CLI/STI terminal continuations."""
    require()
    return _source_frontier_controls


def pin_range(address, size):
    """The writer lease spans this ioctl and the following kcore read."""
    try:
        fcntl.ioctl(require(), PIN, RANGE_STRUCT.pack(address, size))
    except OSError as error:
        if error.errno not in {errno.EPERM, errno.ESTALE, errno.ENOSPC, errno.EINVAL}:
            raise
        raise SourceRefused(
            f"source range cannot be pinned: address={address:#x} bytes={size} "
            f"errno={error.errno} ({error.strerror})", errno=error.errno
        ) from error


@contextmanager
def session():
    global _fd, _mutex_stack_bytes, _percpu_module_bytes, _native_escape, _address_guard, _string_services, _string_write, _audited_strings, _direct_strings, _root_native_escape, _indirect_call, _origin_instruction, _origin_call, _origin_memory, _origin_context_read, _indirect_tail, _source_frontier, _source_frontier_extensions, _source_frontier_controls
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
        if not caps["mutex_exclusive"]:
            raise RuntimeError("exclusive KD mutex object capability required")
        if not caps["mutex_images"]:
            raise RuntimeError("immutable legacy mutex image publication capability required")
        _mutex_stack_bytes = caps["mutex_stack_bytes"]
        _percpu_module_bytes = caps["percpu_module_bytes"]
        _native_escape = caps["native_escape"]
        _address_guard = caps["address_guard"]
        _string_services = caps["string_services"]
        _string_write = caps["string_write"]
        _audited_strings = caps["audited_strings"]
        _direct_strings = caps["direct_strings"]
        _root_native_escape = caps["root_native_escape"]
        _indirect_call = caps["indirect_call"]
        _origin_instruction = caps["origin_instruction"]
        _origin_call = caps["origin_call"]
        _origin_memory = caps["origin_memory"]
        _origin_context_read = caps["origin_context_read"]
        _indirect_tail = caps["indirect_tail"]
        _source_frontier = caps["source_frontier"]
        _source_frontier_extensions = caps.get("source_frontier_extensions", False)
        _source_frontier_controls = caps.get("source_frontier_controls", False)
        _fd = fd
        print(f"Translation device session: inherited={int(inherited is not None)}")
        print(
            f"Translation runtime capability: mutex_stack_bytes={_mutex_stack_bytes} "
            f"percpu_module_bytes={_percpu_module_bytes} "
            f"native_escape={int(_native_escape)} address_guard={int(_address_guard)} "
            f"string_services={int(_string_services)} "
            f"string_write={int(_string_write)} audited_strings={int(_audited_strings)} "
            f"direct_strings={int(_direct_strings)} "
            f"root_native_escape={int(_root_native_escape)} indirect_call={int(_indirect_call)} "
            f"origin_instruction={int(_origin_instruction)} "
            f"origin_call={int(_origin_call)} origin_memory={int(_origin_memory)} "
            f"origin_context_read={int(_origin_context_read)} indirect_tail={int(_indirect_tail)}"
        )
        yield fd
    finally:
        _fd = None
        _mutex_stack_bytes = 0
        _percpu_module_bytes = 0
        _native_escape = False
        _address_guard = False
        _string_services = False
        _string_write = False
        _audited_strings = False
        _direct_strings = False
        _root_native_escape = False
        _indirect_call = False
        _origin_instruction = False
        _origin_call = False
        _origin_memory = False
        _origin_context_read = False
        _indirect_tail = False
        _source_frontier = False
        _source_frontier_extensions = False
        _source_frontier_controls = False
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
