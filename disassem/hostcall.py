# Read the shared hostcall manifest and emit exact-address service exit stubs.
# A service retains the virtual CALL return word for the kernel dispatcher;
# it is not an arbitrary native callee or original-waiter context switch.
import os
import re
from collections import namedtuple
import strcmp_service
import strscpy_service

HostcallSpec = namedtuple("HostcallSpec", "name service_id symbol")

_HOSTCALL_RE = re.compile(
    r"^\s*KD_HOSTCALL\(\s*([A-Z0-9_]+)\s*,\s*([0-9]+)\s*,"
    r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*,"
)


def default_manifest_path():
    return os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "include",
            "kd_hostcalls.def",
        )
    )


def load_hostcall_specs(path=None):
    specs = []
    names = set()
    service_ids = set()
    symbols = set()

    with open(path or default_manifest_path(), "r", encoding="ascii") as manifest:
        for line_number, line in enumerate(manifest, 1):
            match = _HOSTCALL_RE.match(line)
            if not match:
                continue
            name, service_id_text, symbol = match.groups()
            service_id = int(service_id_text)
            if service_id == 0:
                raise ValueError("hostcall ID 0 is reserved")
            if name in names or service_id in service_ids or symbol in symbols:
                raise ValueError(
                    f"duplicate hostcall declaration at line {line_number}"
                )
            names.add(name)
            service_ids.add(service_id)
            symbols.add(symbol)
            specs.append(HostcallSpec(name, service_id, symbol))

    if not specs:
        raise ValueError("hostcall manifest contains no services")
    return specs


def resolve_hostcalls(symbol_lookup, path=None, *, string_services=False,
                      string_write=False, reader=None):
    resolved = {}

    for spec in load_hostcall_specs(path):
        address = symbol_lookup(spec.symbol, 0)
        if tuple(spec) == strcmp_service.SPEC:
            if (not string_services or reader is None or not address
                    or not strcmp_service.verified(
                        address, symbol_lookup("__x86_return_thunk", 0), reader)):
                continue
        if tuple(spec) == strscpy_service.SPEC:
            if (not string_write or reader is None or not address
                    or not strscpy_service.verified(address, symbol_lookup, reader)):
                continue
        if address and address not in resolved:
            resolved[address] = spec
    return resolved


def readonly_waiter_targets(resolved):
    """Exact typed services whose handlers only replace saved RAX.

    These audited helpers run on the executor stack and do not write waiter
    memory. strcmp additionally requires its negotiated exact-text, pointer
    screening and runtime string-bound checks. Keep future services opaque. This
    summarizes sequential effects only, not concurrent memory freshness.
    See kernel_module/execution/hostcalls.inc for the matching invocations.
    """
    audited = {("KTIME_GET", 1, "ktime_get"),
               ("KTIME_GET_NS", 2, "ktime_get_ns"),
               ("INT_SQRT", 3, "int_sqrt"), strcmp_service.SPEC}
    return {address for address, spec in resolved.items() if tuple(spec) in audited}
