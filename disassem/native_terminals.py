"""Exact Native/context C-call boundaries, independent of source-trust policy."""
from pathlib import Path
import re


def load_specs(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[1] / "include/kd_native_terminals.def"
    source = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="ascii"), flags=re.S)
    specs = {}
    pattern = re.compile(r"KD_NATIVE_TERMINAL\(([A-Za-z_][A-Za-z0-9_]*),\s*([A-Z_]+)\)")
    for line in source.splitlines():
        if not line.strip():
            continue
        match = pattern.fullmatch(line.strip())
        if not match or match[1] in specs:
            raise ValueError("invalid or duplicate Native terminal declaration: " + line)
        specs[match[1]] = match[2]
    if not specs:
        raise ValueError("empty Native terminal manifest")
    return specs


def resolve(symbol_lookup, path=None):
    resolved = {}
    for name, purpose in load_specs(path).items():
        address = symbol_lookup(name, 0)
        if address:
            resolved.setdefault(address, (name, purpose))
    return resolved


def indirect_call_length(raw):
    """Canonical near FF /2, optionally one REX; no far/prefixed state model."""
    raw = bytes(raw)
    index = int(bool(raw) and 0x40 <= raw[0] <= 0x4f)
    if len(raw) < index + 2 or raw[index] != 0xff:
        return None
    modrm = raw[index + 1]
    if (modrm >> 3) & 7 != 2:
        return None
    index += 2
    mode, rm = modrm >> 6, modrm & 7
    sib_base = None
    if mode != 3 and rm == 4:
        if len(raw) <= index:
            return None
        sib_base = raw[index] & 7
        index += 1
    index += (1 if mode == 1 else 4 if mode == 2 or
              (mode == 0 and (rm == 5 or sib_base == 5)) else 0)
    return index if index == len(raw) else None
