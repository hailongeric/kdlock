"""Verify native qspinlock dispatch even after boot dmesg has rotated out.

Only the two lock dispatch pointers are read from live kernel memory.
Call after the exact source/config/build/live kernel identity check.
"""
from pathlib import Path
import re
import struct


def member_offset(text, declaration):
    pattern = r'\s+'.join(re.escape(word) for word in declaration.split())
    match = re.search(pattern + r'\s*/\*\s*(\d+)\s+\d+\s*\*/', text)
    if not match:
        raise ValueError('missing DWARF member offset: ' + declaration)
    return int(match[1])


def read_virtual(stream, address, size):
    header = struct.unpack('<16sHHIQQQIHHHHHH', stream.read(64))
    if header[0][:6] != b'\x7fELF\x02\x01' or header[9] != 56:
        raise ValueError('expected little-endian ELF64 kcore')
    for index in range(header[10]):
        stream.seek(header[5] + index * 56)
        kind, _, offset, virtual, _, length, _, _ = struct.unpack('<IIQQQQQQ', stream.read(56))
        if kind == 1 and virtual <= address and address + size <= virtual + length:
            stream.seek(offset + address - virtual)
            data = stream.read(size)
            if len(data) == size:
                return data
    raise ValueError('PV lock dispatch is outside readable kcore segments')


def dispatch_offsets(layout):
    offsets = []
    for name in ('queued_spin_lock_slowpath', 'queued_spin_unlock'):
        # Unlock is a paravirt_callee_save member (one pointer), whereas lock
        # is declared directly as a function pointer in this kernel's DWARF.
        match = re.search(r'\b' + name + r'\b[^;]*;\s*/\*\s*(\d+)\s+8\s*\*/', layout)
        if not match:
            raise ValueError('missing pv lock member: ' + name)
        offsets.append(int(match[1]))
    if offsets != [0, 8]:
        raise ValueError('unexpected pv lock function layout')
    return offsets


def capture(source, out, command):
    if 'nopvspin' not in Path('/proc/cmdline').read_text().split():
        raise ValueError('nopvspin is missing')
    symbols = {}
    for line in Path('/proc/kallsyms').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    locks = command(['pahole', '-C', 'pv_lock_ops', source / 'vmlinux'], out / 'pv-lock-ops.txt')
    if 'pv_ops_lock' in symbols:
        # Linux 7 keeps the same typed pair in a standalone object. Read the
        # live dispatch slots, rather than treating the boot argument as proof.
        base = symbols['pv_ops_lock']
        container = 'pv_ops_lock'
    else:
        template = command(['pahole', '-C', 'paravirt_patch_template', source / 'vmlinux'],
                           out / 'pv-template.txt')
        base = symbols['pv_ops'] + member_offset(template, 'struct pv_lock_ops lock;')
        container = 'pv_ops.lock'
    # Pahole spacing can vary with its version; parse member names independently.
    dispatch_offsets(locks)
    with open('/proc/kcore', 'rb', buffering=0) as core:
        actual = struct.unpack('<QQ', read_virtual(core, base, 16))
    names = ('native_queued_spin_lock_slowpath', '__raw_callee_save___native_queued_spin_unlock')
    expected = tuple(symbols[name] for name in names)
    if not all(expected) or actual != expected:
        raise ValueError('live spinlock dispatch is not native')
    return dict(method='live_pv_ops_two_function_pointers',
                container=container,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                pv_lock_address=hex(base), functions={name: hex(value) for name, value in zip(names, actual)})
