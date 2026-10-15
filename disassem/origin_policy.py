"""Explicit build-bound GS audit for the owned mutex's bounded origin subset.

This is admission, not a security sandbox. No writable kernel symbol is granted
by name alone. A module entry needs a reviewed manifest identifying its exact
ELF, source audit and live Build ID; other modules/IRQs/NMIs must not access it.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from miasm.expression.expression import ExprId, ExprInt
import normal
from context_registers import static_address

KERNEL_BUILD_ID = '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
MAX_INSTRUCTIONS = 256
ORIGIN_SPIN = 1


@dataclass(frozen=True)
class Entry:
    symbol: str
    offset: int
    size: int
    operations: frozenset


def build_id(notes):
    offset = 0
    while offset + 12 <= len(notes):
        namesz, descsz, kind = struct.unpack_from('<III', notes, offset)
        offset += 12
        name = notes[offset:offset + namesz]
        offset += (namesz + 3) & ~3
        desc = notes[offset:offset + descsz]
        offset += (descsz + 3) & ~3
        if name == b'GNU\0' and kind == 3 and len(desc) == descsz:
            return desc.hex()
    raise ValueError('missing GNU build identity')


def elf_symbol(path, symbol):
    with Path(path).open('rb') as stream:
        elf = ELFFile(stream)
        note = elf.get_section_by_name('.notes') or elf.get_section_by_name('.note.gnu.build-id')
        identity = build_id(note.data()) if note else None
        symbols = elf.get_section_by_name('.symtab').get_symbol_by_name(symbol) or []
        if len(symbols) != 1 or symbols[0]['st_info']['type'] != 'STT_OBJECT':
            raise ValueError('ambiguous GS object bounds')
        s = symbols[0]
        section = elf.get_section(s['st_shndx'])
        if section.name != '.data..percpu':
            raise ValueError('GS object is not in static per-CPU storage')
        return identity, s['st_value'], s['st_size']


def load_allowlist(lookup):
    """No manifest means CPU-number reads only, on the captured kernel build."""
    if build_id(Path('/sys/kernel/notes').read_bytes()) != KERNEL_BUILD_ID:
        raise ValueError('origin GS audit does not cover this live kernel')
    kernel = os.environ.get('KD_GS_VMLINUX', '/root/linux-6.1.159-kdclobber2/vmlinux')
    identity, offset, size = elf_symbol(kernel, 'cpu_number')
    if identity != KERNEL_BUILD_ID or size != 4 or lookup('cpu_number') != offset:
        raise ValueError('CPU-number audit bounds/build mismatch')
    entries = [Entry('cpu_number', offset, 4, frozenset({'read'}))]
    manifest_path = os.environ.get('KD_GS_AUDIT')
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text())
        # Fixed subset: manifests cannot invent additional mutable symbols or
        # operations. The test driver records the reviewed source digest.
        if manifest['schema'] != 1 or manifest['symbol'] != 'kd_origin_test_counter' or manifest['module'] != 'kd_origin_gs':
            raise ValueError('unknown GS audit entry')
        root = Path(__file__).resolve().parents[1]
        source = root / 'tests/kernel/mutex/origin_gs/module.c'
        audit = json.loads((root / 'tests/kernel/mutex/origin_gs/audit.json').read_text())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != audit['source_sha256'] or digest != manifest['source_sha256']:
            raise ValueError('mutable GS source audit mismatch')
        elf = Path(manifest['elf'])
        if hashlib.sha256(elf.read_bytes()).hexdigest() != manifest['elf_sha256']:
            raise ValueError('mutable GS ELF digest mismatch')
        identity, _, size = elf_symbol(elf, manifest['symbol'])
        live = Path('/sys/module/kd_origin_gs/notes/.note.gnu.build-id').read_bytes()
        if identity != build_id(live) or identity != manifest['build_id'] or size != 8:
            raise ValueError('mutable GS live build/bounds mismatch')
        offset = lookup(manifest['symbol'])
        if not offset or offset != manifest['offset']:
            raise ValueError('mutable GS relocated bounds mismatch')
        entries.append(Entry(manifest['symbol'], offset, 8, frozenset({'read', 'write', 'rmw'})))
    return entries


def requirements(blocks, databases, root, unlocks, allowlist):
    """Validate every emitted instruction and CFG edge; return image needs."""
    instructions = {line.offset: (line, databases[block])
                    for block in blocks.values() for line in block.lines}
    sensitive = False
    for line, db in instructions.values():
        for index, operand in enumerate(line.args):
            segment, address = normal.segment_operand(operand)
            if segment != 'GS' or normal.is_current_task_operand(operand) or line.name.upper() == 'NOP':
                continue
            sensitive = True
            address = static_address(address, db, line.offset + line.l)
            if address is None:
                raise ValueError('dynamic GS address is outside the origin audit')
            operation = ('read' if line.name.upper() in {'MOV', 'MOVZX', 'MOVSX'} and index == 1 else
                         'write' if line.name.upper() == 'MOV' and index == 0 else
                         'rmw' if line.name.upper() in {'INC', 'DEC', 'ADD', 'SUB', 'AND', 'OR', 'XOR'} and index == 0 else None)
            if not any(address == entry.offset and operand.size == entry.size * 8
                       and operation in entry.operations for entry in allowlist):
                raise ValueError('GS symbol, width or operation lacks an explicit audit')
            if line.name.upper() == 'MOV' and (len(line.args) != 2 or
                not isinstance(line.args[1-index], (ExprId, ExprInt))):
                raise ValueError('GS operation is not an explicit scalar access')
    if not sensitive:
        return 0
    if len(instructions) > MAX_INSTRUCTIONS:
        raise ValueError('origin GS body exceeds 256 decoded instructions')
    scalar = {'MOV', 'MOVZX', 'MOVSX', 'MOVSXD', 'LEA', 'ADD', 'SUB', 'INC', 'DEC',
              'AND', 'OR', 'XOR', 'CMP', 'TEST', 'SHL', 'SHR', 'SAR', 'SAL', 'IMUL',
              'NEG', 'NOT', 'NOP', 'ENDBR64', 'PUSH', 'POP'}
    edges = {}
    for offset, (line, db) in instructions.items():
        name = line.name.upper()
        next_ip = offset + line.l
        if name == 'CALL':
            if static_address(line.args[0], db, next_ip) not in unlocks:
                raise ValueError('origin GS body may only call its terminal outer unlock')
            edges[offset] = []
        elif name.startswith('J'):
            target = static_address(line.args[0], db, next_ip)
            if target is None:
                raise ValueError('origin GS body has indirect control flow')
            edges[offset] = [target] + ([] if name == 'JMP' else [next_ip])
        elif name in scalar or name.startswith(('CMOV', 'SET')):
            edges[offset] = [next_ip]
        else:
            raise ValueError('origin GS body has unsupported or blocking instruction: ' + name)
    active, done = set(), set()
    def visit(offset):
        if offset in active:
            raise ValueError('origin GS body must be acyclic')
        if offset in done:
            return
        if offset not in edges:
            raise ValueError('origin GS path does not end at its outer unlock')
        active.add(offset)
        for target in edges[offset]:
            visit(target)
        active.remove(offset)
        done.add(offset)
    visit(root)
    if done != set(instructions):
        raise ValueError('origin GS image contains an unverified disconnected path')
    return ORIGIN_SPIN
