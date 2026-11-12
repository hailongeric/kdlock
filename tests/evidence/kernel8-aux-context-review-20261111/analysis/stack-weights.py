#!/usr/bin/env python3
"""Inspect saved GNU x86-64 disassembly; never execute object or project code."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

HEADER = re.compile(r'^\s*([0-9a-f]+) <([^>]+)>:$')
INSN = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*([^\n]+)$')


def integer(text):
    return int(text, 0)


def stack_offset(text):
    value = integer(text)
    return value - (1 << 64) if value >= 1 << 63 else value


def functions(text):
    result = []
    current = None
    section = None
    for line in text.splitlines():
        if line.startswith('Disassembly of section ') and line.endswith(':'):
            section = line[len('Disassembly of section '):-1]
            current = None
            continue
        match = HEADER.match(line)
        if match:
            current = {'name': match[2], 'section': section, 'address': int(match[1], 16), 'instructions': []}
            result.append(current)
            continue
        match = INSN.match(line)
        if current is None or not match:
            continue
        body = match[3].strip()
        relocation = re.search(r'R_X86_64_\w+\s+(\S+)', body)
        code = re.split(r'\s+R_X86_64_|\s+#', body, maxsplit=1)[0].strip()
        fields = code.split(None, 1)
        current['instructions'].append({'address': int(match[1], 16), 'size': len(match[2].split()),
            'op': fields[0], 'args': fields[1].strip() if len(fields) > 1 else '',
            'relocation': relocation[1] if relocation else None, 'text': code})
    return result


def inspect(function):
    rows = function['instructions']
    positive = 0
    unknown = []
    for row in rows:
        op, args = row['op'], row['args']
        first = args.split(',', 1)[0]
        operands = args.split(',')
        if ((first in ('esp', 'sp', 'spl') and op not in ('cmp', 'test', 'push'))
                or (op in ('xchg', 'xadd') and any(arg in ('rsp', 'esp', 'sp', 'spl') for arg in operands))
                or (op.startswith(('push', 'pop')) and op not in ('push', 'pushf', 'pushfq', 'pop', 'popf', 'popfq'))
                or op in ('enter', 'enterw', 'leavew', 'lcall', 'lret', 'iret', 'iretq', 'sysret', 'sysretq')
                or (op == 'data16' and re.search(r'\b(?:push\w*|pop\w*|enter|leave|ret\w*|iret\w*)\b', args))):
            unknown.append(row)
        if op in ('push', 'pushf', 'pushfq'):
            positive += 8
        elif op in ('sub', 'add') and first == 'rsp':
            try:
                amount = stack_offset(args.split(',', 1)[1])
                positive += max(0, amount if op == 'sub' else -amount)
            except ValueError:
                unknown.append(row)
        elif op == 'and' and first == 'rsp':
            try:
                mask = integer(args.split(',', 1)[1]) & ((1 << 64) - 1)
                alignment = ((~mask) & ((1 << 64) - 1)) + 1
                if alignment & (alignment - 1):
                    raise ValueError('nonalignment mask')
                positive += alignment - 1
            except ValueError:
                unknown.append(row)
        elif op == 'lea' and first == 'rsp':
            match = re.fullmatch(r'rsp,\[rsp([+-]0x[0-9a-f]+)?\]', args)
            if match:
                positive += max(0, -integer(match[1] or '0'))
            elif not re.fullmatch(r'rsp,\[rbp(?:[+-]0x[0-9a-f]+)?\]', args):
                unknown.append(row)
        elif (first == 'rsp' and op not in ('cmp', 'test', 'mov', 'pop')) or op == 'enter' or (op == 'xchg' and re.search(r'\brsp\b', args)):
            unknown.append(row)
        elif (op == 'mov' and first == 'rsp' and args != 'rsp,rbp') or (op == 'pop' and args == 'rsp'):
            unknown.append(row)
    bound = 8 + positive
    addresses = {row['address']: index for index, row in enumerate(rows)}
    errors, exits, backedges = [], [], []
    states = collections.deque([(0, 8, None)]) if rows else collections.deque()
    seen = set()
    maximum = 8
    while states and not errors:
        index, depth, bp = states.popleft()
        state = (index, depth, bp)
        if state in seen:
            continue
        seen.add(state)
        if len(seen) > 65536 or depth < 0 or depth > bound:
            errors.append({'reason': 'stack accumulation/backedge or state bound', 'state': state})
            break
        row = rows[index]
        op, args = row['op'], row['args']
        if op in ('push', 'pushf', 'pushfq'):
            depth += 8
        elif op in ('pop', 'popf', 'popfq'):
            depth -= 8
            if args == 'rbp':
                bp = None
        elif op in ('sub', 'add') and args.startswith('rsp,'):
            try:
                amount = stack_offset(args.split(',', 1)[1])
                depth += amount if op == 'sub' else -amount
            except ValueError:
                errors.append({'reason': 'dynamic RSP arithmetic', 'instruction': row})
                break
        elif op == 'and' and args.startswith('rsp,'):
            mask = integer(args.split(',', 1)[1]) & ((1 << 64) - 1)
            depth += ((~mask) & ((1 << 64) - 1))
        elif op == 'mov' and args == 'rbp,rsp':
            bp = depth
        elif (args.split(',', 1)[0] in ('rbp', 'ebp', 'bp', 'bpl') and op not in ('push', 'cmp', 'test')) or (op in ('xchg', 'xadd') and any(arg in ('rbp', 'ebp', 'bp', 'bpl') for arg in args.split(','))):
            bp = None
        elif op == 'mov' and args == 'rsp,rbp':
            if bp is None:
                errors.append({'reason': 'unresolved RBP restoration', 'instruction': row})
                break
            depth = bp
        elif op == 'lea' and args.startswith('rsp,'):
            match = re.fullmatch(r'rsp,\[(rsp|rbp)([+-]0x[0-9a-f]+)?\]', args)
            if not match or (match[1] == 'rbp' and bp is None):
                errors.append({'reason': 'unresolved LEA RSP', 'instruction': row})
                break
            depth = (depth if match[1] == 'rsp' else bp) - integer(match[2] or '0')
        elif op == 'leave':
            if bp is None:
                errors.append({'reason': 'unresolved LEAVE', 'instruction': row})
                break
            depth, bp = bp - 8, None
        maximum = max(maximum, depth)
        if op in ('call', 'callq') and row['relocation'] in ('__stack_chk_fail-0x4', 'BUG_func-0x4'):
            exits.append({'address': row['address'], 'op': op, 'depth': depth,
                          'excluded_noreturn_failure': row['relocation']})
            continue
        if op in ('ret', 'retq', 'ud2', 'int3'):
            exits.append({'address': row['address'], 'op': op, 'depth': depth})
            if op in ('ret', 'retq') and depth != 8:
                errors.append({'reason': 'unbalanced return', 'instruction': row, 'depth': depth})
            continue
        target = re.match(r'^([0-9a-f]+)\s+<', args)
        branch = op.startswith('j') or op.startswith('loop')
        if branch:
            destination = addresses.get(int(target[1], 16)) if target and not row['relocation'] else None
            if destination is not None:
                if destination <= index:
                    backedges.append([row['address'], rows[destination]['address']])
                states.append((destination, depth, bp))
            else:
                exits.append({'address': row['address'], 'op': op, 'depth': depth,
                              'external_target': row['relocation'] or args})
            if op in ('jmp', 'jmpq'):
                continue
        if index + 1 < len(rows):
            states.append((index + 1, depth, bp))
        else:
            errors.append({'reason': 'reachable end-of-function fallthrough', 'instruction': row, 'depth': depth})
    return {'name': function['name'], 'section': function['section'], 'address': function['address'], 'instruction_count': len(rows),
            'conservative_fixed_stack_bytes': bound, 'observed_cfg_upper_depth': maximum,
            'positive_static_rsp_bytes': positive, 'unknown_rsp_instructions': unknown,
            'cfg_errors': errors, 'local_backedges': sorted(set(map(tuple, backedges))),
            'exits': exits, 'cfg_states': len(seen),
            'local_stack_checks_closed': bool(rows) and not unknown and not errors and bool(exits),
            'external_exit_resolution_required': [row for row in exits if 'external_target' in row],
            'calls': [{'address': row['address'], 'target': row['relocation'] or row['args']}
                      for row in rows if row['op'] in ('call', 'callq')],
            'scope': 'Entry return word plus all fixed positive stack operations; call-chain and external/cold exits require separate source closure.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instructions', type=Path)
    args = parser.parse_args()
    data = args.instructions.read_bytes()
    print(json.dumps({'path': str(args.instructions), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                      'functions': [inspect(function) for function in functions(data.decode())]}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
