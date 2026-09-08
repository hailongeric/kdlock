"""Per-translation diagnostics; never change emitted code or error policy."""

import json
import sys

_pid = None
_entry = None
_rip = None
_instruction = None
_seen = set()


def begin(pid, entry):
    global _pid, _entry
    _pid, _entry = pid, entry
    _seen.clear()
    set_instruction(None, None)


def set_instruction(rip, instruction):
    global _rip, _instruction
    _rip = rip
    _instruction = str(instruction) if instruction is not None else None


def _address(value):
    return f"0x{value:x}" if value is not None else "n/a"


def _emit(level, reason, action, detail, fields):
    key = (level, reason, _rip)
    if key in _seen:
        return
    _seen.add(key)
    context = {
        "pid": _pid if _pid is not None else "n/a",
        "entry": _address(_entry),
        "rip": _address(_rip),
        "inst": _instruction if _instruction is not None else "n/a",
        "action": action,
        "detail": detail,
        **fields,
    }
    text = " ".join(f"{key}={json.dumps(value)}" for key, value in context.items())
    print(f"[KD_JIT][{level}] reason={reason} {text}", file=sys.stderr, flush=True)


def warn(reason, action, detail="", **fields):
    _emit("WARN", reason, action, detail, fields)


def error(reason, action, detail="", **fields):
    _emit("ERROR", reason, action, detail, fields)
