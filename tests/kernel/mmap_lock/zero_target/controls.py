#!/usr/bin/env python3
"""Negative controls use the current real run, not hand-constructed pass fixtures."""
import copy
import re


def check(row, log, validate):
    mutations = []
    absent = row.get('absent_target_test', 0)
    missing = row.get('missing_table_test',0)
    boundary = row.get('boundary_edge_test',0)
    private = row.get('boundary_private_test',0)
    broken = copy.deepcopy(row); broken['counts']['native'] += 1
    mutations.append(('destructive-replay', broken, log))
    broken = copy.deepcopy(row); broken['pages_removed'] += 1
    mutations.append(('mapping-accounting', broken, log))
    broken = copy.deepcopy(row)
    victim = next(p for o in broken['origins'] for p in o['layouts'] if p['mapped'])
    victim['hi'] += 4096
    mutations.append(('surviving-layout', broken, log))
    if not row['native'] or row['injection']:
        required = ('KD_MM_SPLIT inject' if row['native'] else
                    'KD_MM_UNMAP error' if row['injection'] else
                    'KD_MM_UNMAP ack' if row['busy'] else
                    'KD_MM_SPLIT retire' if row['cancel'] else (('KD_MM_BOUNDARY_INTERIOR_ZERO done' if row.get('boundary_zero_test',0) else 'KD_MM_BOUNDARY_INTERIOR_EMPTY done' if row.get('boundary_empty_test',0) else 'KD_MM_BOUNDARY_INTERIOR_MISSING done') if row.get('boundary_interior_test',0) else 'KD_MM_BOUNDARY_SHARED_PRIVATE done' if private else 'KD_MM_BOUNDARY_SHARED_EMPTY done' if row.get('boundary_empty_test',0) else 'KD_MM_BOUNDARY_SHARED_MISSING done' if row.get('boundary_shared_missing_test',0) else 'KD_MM_BOUNDARY_SHARED_ZERO done') if row.get('boundary_shared_test',0) else 'KD_MM_BOUNDARY_PRIVATE done' if private else 'KD_MM_BOUNDARY_ZERO done' if row.get('boundary_zero_test',0) else 'KD_MM_BOUNDARY_EMPTY done' if row.get('boundary_empty_test',0) else 'KD_MM_BOUNDARY done' if boundary else 'KD_MM_MISSING_TABLE done' if missing else 'KD_MM_ABSENT_TARGET done' if absent else 'KD_MM_ZERO_TARGET done')
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
    broken = copy.deepcopy(row); broken['ptes_after'][0]['none'] ^= 1
    mutations.append(('unexpected-survivor-pte', broken, log))
    broken = copy.deepcopy(row)
    slot = next((i for i,p in enumerate(broken['pages_before']) if p['pfn'] == 0), None)
    if slot is None:
        broken['pages_before'][0]['pfn'] += 1
        mutations.append(('wrong-original-private-page', broken, log))
    else:
        broken['pages_before'][slot]['pfn'] = 1
        mutations.append(('reference-in-untouched-slot', broken, log))
    broken = copy.deepcopy(row); broken['shape'] = 'unknown'
    mutations.append(('wrong-shape', broken, log))
    broken = copy.deepcopy(row)
    victim = next(p for group in broken['residency'][1] for p in group if p['mapped'])
    victim['rss_kb'] += 4
    mutations.append(('resident-accounting-leak', broken, log))
    broken = copy.deepcopy(row)
    victim = next(p for group in broken['residency'][2] for p in group if p['mapped'])
    victim['anonymous_kb'] = 0
    mutations.append(('missing-local-write-population', broken, log))
    if not row['native'] and not row['injection'] and not row['busy'] and not row['cancel']:
        key='resident_mask' if private else 'pmd_none' if missing else 'untouched_mask' if absent else 'zero_mask'
        mutations.append(('wrong-body-slot-mask',row,re.sub(key+r'=\d+',key+'=0',log)))
    broken = copy.deepcopy(row); broken['independent_after']['zero'] &= ~1
    mutations.append(('independent-zero-corrupted', broken, log))
    if row['writes']:
        broken = copy.deepcopy(row); broken['writes'][0]['state']['zero'] ^= 1
        mutations.append(('write-changed-another-slot', broken, log))
    broken = copy.deepcopy(row)
    if private: broken['masks'][-1] &= ~(1 << row['slice'])
    elif absent: broken['zero_masks'][-1] ^= 1 << row['slice']
    else: broken['zero_masks'][-1] = 0
    mutations.append(('zero-input-unproven', broken, log))
    if row['changing']:
        broken = copy.deepcopy(row)
        if boundary: broken['change_more']['table_after'] += 1
        elif row.get('changing_empty'): broken['change_more']['table_after'] += 1
        elif row.get('changing_zero'): broken['change']['zero_pfn'] += 1
        else: broken['change']['page'][0]['pfn'] += 1
        mutations.append(('stale-private-target',broken,log))
        broken = copy.deepcopy(row); broken['change']['pending'] += 1
        mutations.append(('change-not-before-execution',broken,log))
    if any(not mask for mask in row['masks']):
        broken = copy.deepcopy(row)
        victim = next(o for mask,o in zip(row['masks'],broken['origins']) if not mask)
        victim['original_anon'] = 0 if victim['original_anon'] else 1
        mutations.append(('wrong-initial-ancestry',broken,log))
        if not row['native'] and not any(row[k] for k in ('busy','cancel','injection')):
            mutations.append(('invented-private-holds',row,log.replace('held=0 released=0','held=1 released=1')))
        if not row['native']:
            changed = re.sub(r'(KD_MM_RMAP retire[^\n]* consumed=)0( freed=)3',r'\g<1>1\g<2>2',log,count=1)
            mutations.append(('unused-link-falsely-consumed',row,changed))
    if not row['native'] and not row['busy'] and not row['cancel'] and not row['injection']:
        key='target_owned' if absent or private else 'zero_owned'
        mutations.append(('target-ownership-changed',row,log.replace(key+('=1' if private else '=0'),key+('=0' if private else '=1'))))
        if row.get('changing_zero'):
            if row.get('boundary_shared_test',0):
                broken=copy.deepcopy(row);broken['change']['after_private']=1
                mutations.append(('faulted-zero-page-owned',broken,log))
            else: mutations.append(('faulted-zero-page-owned',row,log.replace('zero_owned=0','zero_owned=1')))
    if absent:
        broken=copy.deepcopy(row);broken['tables_before'][0]['leaf'] ^= 1
        mutations.append(('missing-table-claimed-leaf',broken,log))
        broken=copy.deepcopy(row);broken['tables_after'][0]['pfn'][0] += 1
        mutations.append(('retained-table-replaced',broken,log))
        broken=copy.deepcopy(row);g=1 if row['injection'] and not row['native'] else 0
        broken['ptes_before'][g]['none'] &= ~(1 << row['slice']);broken['ptes_before'][g]['zero'] |= 1 << row['slice']
        mutations.append(('target-populated-before-admission',broken,log))
        if row['changing']:
            broken=copy.deepcopy(row);broken['change_more']['table_after'] += 1
            mutations.append(('fault-changed-table',broken,log))
    passed = []
    for name, data, messages in mutations:
        try: validate(data, messages)
        except AssertionError: passed.append(name)
        else: raise AssertionError('corrupt evidence accepted: ' + name)
    return passed
