#!/usr/bin/env python3
"""Negative controls use the current real run, not hand-constructed pass fixtures."""
import copy
import re


def check(row, log, validate):
    mutations = []
    broken = copy.deepcopy(row); broken['counts']['native'] += 1
    mutations.append(('destructive-replay', broken, log))
    broken = copy.deepcopy(row); broken['pages_removed'] += 1
    mutations.append(('mapping-accounting', broken, log))
    broken = copy.deepcopy(row)
    victim = next(p for o in broken['origins'] for p in o['layouts'] if p['mapped'])
    victim['hi'] += 4096
    mutations.append(('surviving-layout', broken, log))
    required = ('KD_MM_SPLIT inject' if row['native'] else
                'KD_MM_UNMAP error' if row['injection'] else
                'KD_MM_UNMAP ack' if row['busy'] else
                'KD_MM_SPLIT retire' if row['cancel'] else 'KD_MM_RESIDENT_PARTIAL done')
    lines = log.splitlines(True)
    index = next(i for i, line in enumerate(lines) if required in line)
    mutations.append(('missing-body-or-retirement', row, ''.join(lines[:index] + lines[index + 1:])))
    changed = list(lines)
    changed[index] = re.sub(r'executor=\d+', 'executor=0', changed[index]) if 'executor=' in changed[index] else re.sub(r'consumed=\d+', 'consumed=7', changed[index])
    mutations.append(('wrong-executor-or-transfer', row, ''.join(changed)))
    if row['resident']:
        broken = copy.deepcopy(row)
        victim = next(p for o in broken['origins'] for p in o['layouts'] if p['mapped'])
        victim['active'] += 1
        mutations.append(('reverse-map-leak', broken, log))
        broken = copy.deepcopy(row); broken['pins_released'] -= 1
        mutations.append(('reference-leak', broken, log))
    passed = []
    for name, data, messages in mutations:
        try: validate(data, messages)
        except AssertionError: passed.append(name)
        else: raise AssertionError('corrupt evidence accepted: ' + name)
    return passed
