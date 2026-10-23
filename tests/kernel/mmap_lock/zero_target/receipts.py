#!/usr/bin/env python3
"""Zero-target contract; clearing a special mapping never owns its page."""
import re


def require(ok, text):
    if not ok: raise AssertionError(text)


IDENT = r'mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+)'
SHAPES = {
    f'{shape}-{pair}': (target, sum(1 << p for p, kind in zip(survivors, pair) if kind == 'r'),
                       (1 << target) | sum(1 << p for p, kind in zip(survivors, pair) if kind == 'z'))
    for shape, target, survivors in [('prefix', 0, [1, 2]), ('middle', 1, [0, 2]), ('suffix', 2, [0, 1])]
    for pair in ('ru', 'ur', 'rz', 'zr', 'rr', 'zz', 'zu', 'uz', 'uu')}


def semantic_layout(row):
    victim = row['origins'][0 if row['native'] else 1]
    return [{k: p[k] for k in ('mapped', 'lo', 'hi', 'pgoff', 'flags')} for p in victim['layouts']]


def compare_native(native, delegated):
    require(native['native'] == 1 and delegated['native'] == 0 and
            all(native[k] == delegated[k] for k in ('resident', 'injection', 'slice')),
            'native comparison inputs differ')
    require(semantic_layout(native) == semantic_layout(delegated), 'native/delegated post-error VMA layout differs')
    require(native['origins'][0]['result'] == delegated['origins'][1]['result'] == -1 and
            native['origins'][0]['errno'] == delegated['origins'][1]['errno'] == 12,
            'native/delegated error differs')
    require(all(a[0] == b[1] for a, b in zip(native['residency'], delegated['residency'])),
            'native/delegated post-error resident accounting differs')


def compare_success(native, delegated):
    require(native['native'] == 1 and delegated['native'] == 0 and
            all(native[k] == delegated[k] for k in ('shape', 'resident', 'injection', 'slice')) and
            not any(native[k] or delegated[k] for k in ('injection', 'busy', 'cancel', 'free_first')),
            'native success comparison inputs differ')
    expected = semantic_layout(native)
    for g, origin in enumerate(delegated['origins']):
        require([{k: p[k] for k in ('mapped', 'lo', 'hi', 'pgoff', 'flags')} for p in origin['layouts']] == expected and
                origin['result'] == native['origins'][0]['result'] == 0 and
                delegated['masks'][g] == native['masks'][0] and delegated['zero_masks'][g] == native['zero_masks'][0], 'native/delegated mapping result differs')
        require(all(a[0] == b[g] for a, b in zip(native['residency'], delegated['residency'])),
                'native/delegated resident accounting differs')
    return dict(shape=native['shape'], origins=delegated['groups'], layouts_equal=True, residency_equal=True)


def validate(row, log):
    n, resident, native = row['groups'], row['resident'], row['native']
    require(row['zero_target_test'] == resident == 1, 'zero-target evidence required')
    masks, zeros = row['masks'], row['zero_masks']; target = 1 << row['slice']
    changing = row['changing']; change_group = 0 if native else 1
    require(len(masks) == len(zeros) == n and all(0 <= m <= 7 for m in masks), 'original slot masks missing')
    require(row['shape'] in SHAPES or row['shape'] in ('refusal', 'missing', 'cancel', 'free', 'change', 'change-empty', 'missing-empty', 'cancel-empty', 'inherited'), 'unknown input shape')
    empty = row.get('empty_control', 0); inherited = row.get('inherited', 0)
    require(empty == (row['shape'] in ('change-empty','missing-empty','cancel-empty')) and
            inherited == (row['shape']=='inherited') and not row['no_resident'], 'metadata fixture differs')
    wanted_slice, wanted_mask, wanted_zero = SHAPES.get(row['shape'], (1, 5, 2) if row['busy_page'] else (1, 4, 3) if changing else (1, 1, 6))
    if empty or inherited: wanted_slice, wanted_mask, wanted_zero = 1, 0, 7
    require(row['slice'] == wanted_slice and changing == (row['shape'] in ('change','change-empty')), 'declared target or transition differs')
    for g, (mask, zero) in enumerate(zip(masks, zeros)):
        if row['injection'] and not native and g == 0: expected_input = (7, 0)
        elif row['missing_target'] and g == 1: expected_input = (0, 5) if empty else (1, 4)
        else: expected_input = (wanted_mask, wanted_zero)
        require((mask, zero) == expected_input and not (mask & zero), 'declared residency combination differs')
        if not (row['injection'] and not native and g == 0 or row['missing_target'] and g == 1):
            require(zero & target and not (mask & target), 'target was privately populated before initial observation')
    require(row['busy'] == bool(row['busy_page'] or row['no_resident'] or row['missing_target']) and
            sum(row[k] for k in ('busy_page','no_resident','missing_target')) <= 1, 'refusal input differs')
    effective = [m | (target if changing and g == change_group else 0) for g,m in enumerate(masks)]
    effective_zero = [z & ~(target if changing and g == change_group else 0) for g,z in enumerate(zeros)]
    pins = sum(m.bit_count() for m in masks) + changing
    inject, busy, cancel, free = (row[k] for k in ('injection', 'busy', 'cancel', 'free_first'))
    require(n == (1 if native else 2 if inject or cancel or free else 3) and row['slice'] in (0, 1, 2), 'case shape differs')
    require(row['idle'] == 1 and row['errors'] == 0 and row['checks'] > 100 and row['mm'] and row['gate'] and
            row['reader_peak'] == (0 if native else 2) and row['cleanup_calls'] == n * 3 and
            row['fail_seen'] == bool(inject), 'business, injection, readers or cleanup missing')
    expected = dict(calls=0 if native else n, removed=0 if native else 1 if inject or busy or cancel else n,
                    delegated=0 if native or inject or busy or cancel else n - 1,
                    native=2 if busy else 0, post_ban=int(bool(busy)), handbacks=int(bool(busy)), acks=int(bool(busy)),
                    cancelled=int(bool(cancel)), refused=int(bool(busy)), failed=int(bool(inject and not native)), native_only=int(bool(busy)))
    require(row['counts'] == expected, 'operation/ACK/error balance differs; possible replay')
    clean = dict(expected)
    if not native:
        clean.update(calls=expected['calls'] + n * 3, native=expected['native'] + n * 3,
                     post_ban=expected['post_ban'] + n * 3 - (not busy), refused=1, native_only=1)
    require(row['after_cleanup'] == clean, 'cleanup replay or retirement imbalance')
    removed_pages = (0 if native else 3) if inject else 1 if cancel else n
    delta = inject - (not native) if inject else removed_pages if row['slice'] == 1 else 0
    require(row['pages_removed'] == removed_pages and row['maps_delta'] == delta, 'mapping accounting differs')
    origins = {str(o['tid']): (i, o) for i, o in enumerate(row['origins'])}
    require(len(origins) == n and all(int(t) > 0 for t in origins), 'exact origin tasks missing')

    def identity(r):
        mm, ident, origin, executor, start, end = r[:6]
        require(origin in origins and executor in origins and origin != executor and
                int(mm, 16) == row['mm'] and 0 < int(ident) <= n, 'wrong mm/request/different executor')
        i, o = origins[origin]
        require((int(start, 16), int(end, 16)) == (o['start'], o['end']), 'request range mismatch')
        return i, o

    rows = {}
    for kind, suffix, count in [('done', ' result=0', expected['delegated']), ('error', ' result=-12', expected['failed']),
                                 ('handback', '', expected['handbacks']), ('ack', '', expected['acks'])]:
        rows[kind] = re.findall(r'KD_MM_UNMAP ' + kind + ' ' + IDENT + suffix, log)
        require(len(rows[kind]) == len(set(rows[kind])) == len({r[1] for r in rows[kind]}) == count,
                'missing/duplicate ' + kind)
        for r in rows[kind]: identity(r)
    require(sorted(rows['handback']) == sorted(rows['ack']), 'wrong refusal ACK owner')
    rollback = re.findall(r'KD_MM_POPULATED_RANGE rollback ' + IDENT + r' held=1 released=1 effects=0', log)
    require(sorted(rollback) == ([] if empty else sorted(rows['handback'])), 'late-page refusal did not release its exact prefix before ACK')
    splits = re.findall(r'KD_MM_PARTIAL done ' + IDENT + r' old_start=([0-9a-f]+) old_end=([0-9a-f]+) splits=(\d+) maps_before=(\d+) maps_after=(\d+) pages_before=(\d+) pages_after=(\d+) tables_unchanged=1', log)
    require(sorted(r[:6] for r in splits) == sorted(rows['done']), 'split/body completion not paired')
    for r in splits:
        _, o = identity(r); s = 2 if row['slice'] == 1 else 1
        require(int(r[6], 16) == o['old_start'] and int(r[7], 16) == o['old_end'] and int(r[8]) == s and
                int(r[10]) - int(r[9]) == s - 1 and int(r[11]) - int(r[12]) == 1, 'native split accounting differs')
    private_rows = [r for r in rows['done'] if changing and identity(r)[0] == change_group]
    zero_done = [r for r in rows['done'] if r not in private_rows]
    physical = re.findall(r'KD_MM_RESIDENT_PARTIAL done ' + IDENT + r' pfn=([0-9a-f]+) held=(\d+) released=(\d+) pte_none=1 mapcount=0 tables_retained=1', log)
    require(sorted(r[:6] for r in physical) == sorted(private_rows), 'changed target not executed through the private-page path')
    for r in physical:
        i, _ = identity(r)
        require(int(r[6], 16) == row['change']['page'][0]['pfn'] and
                int(r[7]) == int(r[8]) == effective[i].bit_count(), 'changed target PFN/holds differ')
    kept = re.findall(r'KD_MM_ZERO_PARTIAL done ' + IDENT + r' resident_mask=(\d+) zero_mask=(\d+) untouched_mask=(\d+) held=(\d+) released=(\d+) zero_ptes_preserved=1', log)
    require(sorted(r[:6] for r in kept) == sorted(private_rows), 'changed target zero survivor lost')
    for r in kept:
        i,_=identity(r)
        require(tuple(map(int,r[6:])) == (effective[i], effective_zero[i], 7 ^ (effective[i] | effective_zero[i]), effective[i].bit_count(), effective[i].bit_count()), 'post-change slot state differs')
    cleared = re.findall(r'KD_MM_ZERO_TARGET done ' + IDENT + r' zero_pfn=([0-9a-f]+) resident_mask=(\d+) zero_mask=(\d+) untouched_mask=(\d+) held=(\d+) released=(\d+) target_pte_none=1 zero_owned=0 tables_retained=1 zero_survivors_preserved=1', log)
    require(sorted(r[:6] for r in cleared) == sorted(zero_done), 'actual zero-target clearing not bound to completion')
    for r in cleared:
        i, _ = identity(r)
        require(int(r[6],16)>0 and tuple(map(int,r[7:])) == (masks[i],zeros[i],7 ^ (masks[i] | zeros[i]),masks[i].bit_count(),masks[i].bit_count()), 'zero-target identity/ownership differs')
    require(len({r[6] for r in cleared}) <= 1, 'zero PFNs disagree on this captured x86 kernel')
    zero_errors = re.findall(r'KD_MM_ZERO_TARGET error ' + IDENT + r' resident_mask=(\d+) zero_mask=(\d+) untouched_mask=(\d+) held=(\d+) released=(\d+) zero_ptes_preserved=1 zero_owned=0 result=-12', log)
    require(sorted(r[:6] for r in zero_errors) == sorted(rows['error']), 'zero target after admitted error unproven')
    for r in zero_errors:
        i, _ = identity(r)
        require(tuple(map(int,r[6:])) == (masks[i],zeros[i],7 ^ (masks[i] | zeros[i]),masks[i].bit_count(),masks[i].bit_count()), 'zero target error holds/state differs')
    transitions = list(re.finditer(r'KD_MM_TEST target_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) before_zero=1 after_private=1 result=0',log))
    require(len(transitions)==changing, 'controlled target change missing/duplicated')
    c=row['change']
    if changing:
        require(c['done']==c['before_zero']==c['after_private']==1 and c['result']==0 and c['index']==change_group*3+row['slice'] and
                c['pending']==(0 if native else 3) and c['readers']==(1 if native else 2) and (native or c['admission']==-1), 'target change was not before queued execution')
        require(len(c['page'])==1 and c['actor']>0 and c['zero_pfn']>0, 'change identity missing')
        p=c['page'][0];o=row['origins'][change_group]
        require(p['address']==o['start'] and p['pfn']>0 and p['pfn']!=c['zero_pfn'] and p['maps']==1 and p['refs']==2 and
                p['hash']>0 and not p['locked'] and p['charged_same'], 'new private reference invalid')
        r=transitions[0].groups()
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:6]))==(c['index'],c['actor'],c['pending'],c['readers'],c['admission']) and
                int(r[6],16)==c['zero_pfn'] and int(r[7],16)==p['pfn'], 'transition log not bound to actual changed target')
        if not native:
            require(str(c['actor']) not in origins and all(int(r[6],16)==c['zero_pfn'] for r in cleared), 'local modifier or shared-zero identity differs')
            body=re.search(r'KD_MM_RESIDENT_PARTIAL done '+IDENT,log)
            require(body and transitions[0].end()<body.start(), 'body ran before the controlled change')
    else:
        require(not any(c[k] for k in ('done','before_zero','after_private','result','actor','pending','readers','zero_pfn')) and not c['page'], 'unexpected target transition')

    faults = re.findall(r'KD_MM_SPLIT inject mm=([0-9a-f]+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) splits=(\d+) native=(\d+) result=-12', log)
    require(len(faults) == bool(inject), 'injection was not reached exactly once')
    if inject:
        f = faults[0]; victim = row['origins'][0 if native else 1]
        require(int(f[0], 16) == row['mm'] and int(f[1]) == row['origins'][0]['tid'] and
                int(f[2], 16) == victim['start'] and int(f[3], 16) == victim['end'] and
                int(f[4]) == inject and int(f[5]) == native, 'injected error not bound to the actual route/range')
    aborted = re.findall(r'KD_MM_PARTIAL error ' + IDENT + r' splits=(\d+) held=(\d+) released=(\d+) result=-12', log)
    require(sorted(r[:6] for r in aborted) == sorted(rows['error']), 'admitted failure not paired with queue error')
    for r in aborted:
        require(identity(r)[0] == 1 and int(r[6]) == inject and int(r[7]) == int(r[8]) == masks[1].bit_count(),
                'failed body leaked a held page or executed the wrong split')

    for name, tag, objects, count in [('VMA', 'KD_MM_SPLIT', 'vma', 0 if native else 2 if busy else n + 1),
                                      ('reverse-map', 'KD_MM_RMAP', 'avc', 0 if native or not resident else 2 if busy else n + 1)]:
        retires = re.findall(tag + r' retire mm=([0-9a-f]+) origin=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) ' + objects + r'0=([0-9a-f]+) ' + objects + r'1=([0-9a-f]+) consumed=(\d+) freed=(\d+)', log)
        require(len(retires) == len(set(retires)) == len({r[1] for r in retires}) == count, name + ' retirement missing/duplicate')
        for mm, origin, start, end, obj0, obj1, used, freed in retires:
            cleanup = int(origin) == row['cleanup_tid']
            require(cleanup or origin in origins, 'unknown allocation owner')
            i, o = (None, dict(start=row['origins'][0]['old_start'], end=row['origins'][0]['old_end'])) if cleanup else origins[origin]
            mask = 0 if cleanup or (cancel and i == 1) or (busy and i == 1) or (inject and i == 0) else (1 << inject) - 1 if inject else 3 if row['slice'] == 1 else 1
            # With absent ancestry native cloning consumes no reverse-map
            # link. Both caller reserves must instead retire unused. A fault
            # after publication may create the simple ancestry before split.
            if name == 'reverse-map' and not cleanup and not (o['original_anon'] or changing and i == change_group): mask = 0
            require(int(mm, 16) == row['mm'] and int(start, 16) == o['start'] and int(end, 16) == o['end'] and
                    int(obj0, 16) > 0 and int(obj1, 16) > 0 and obj0 != obj1 and
                    int(used) == mask and int(freed) == (3 ^ mask), name + ' transfer/retirement mismatch')
            if name == 'reverse-map' and mask:
                # A surviving VMA must retain the exact caller-allocated link.
                if inject:
                    require(o['layouts'][2]['link'] == int(obj1 if inject == 2 else obj0, 16), 'post-error link ownership lost')
                elif row['slice'] != 2:
                    require(o['layouts'][2]['link'] == int(obj1 if row['slice'] == 1 else obj0, 16), 'surviving link ownership lost')

    for i, o in enumerate(row['origins']):
        require(bool(o['original_anon']) == bool(masks[i] or inherited) and
                bool(o['original_link']) == bool(o['original_anon']), 'initial ancestry was fabricated or lost')
        failed = inject and (native or i == 1)
        require(o['result'] == (-4 if cancel and i == 1 else -1 if failed else 0) and
                (not failed or o['errno'] == 12), 'origin error/cancellation result differs')
        if not cancel:
            require(o['fault'] == ((0 if resident else -2) if failed else 1), 'same-CPU translation result differs')
        gone = lambda p: (not native and i == 0) if inject else (not cancel or i != 1) and p == row['slice']
        s = inject if failed else 0 if inject or cancel and i == 1 else 2 if row['slice'] == 1 else 1
        for p, l in enumerate(o['layouts']):
            require(bool(l['mapped']) != bool(gone(p)), 'lost surviving or retained removed page')
            if not l['mapped']: continue
            bounds = [0, 3]
            if s: bounds.insert(1, row['slice'] if row['slice'] else 1)
            if s == 2: bounds.insert(2, 2)
            lo, hi = next((a, b) for a, b in zip(bounds, bounds[1:]) if a <= p < b)
            require(l['lo'] == lo * 4096 and l['hi'] == hi * 4096 and l['pgoff'] == lo, 'wrong harmless split layout')
            if o['original_anon'] or changing and i == change_group:
                active = 1 + s - sum(gone(q) for q in range(3))
                root = o['original_anon'] or next(x['anon'] for x in o['layouts'] if x['mapped'])
                require(root and l['anon'] == l['root'] == root and l['link'] and l['refs'] == 1 and l['active'] == l['intervals'] == active,
                        'reverse-map accounting/reference leak')
            else: require(all(l[k]==0 for k in ('anon','root','link','refs','active','intervals')), 'fabricated reverse map without private history')
    require(row['pins_released'] == pins and
            row['pins_released_before'] == (pins if free else 0), 'exact test reference release differs')
    require(len(row['pages_before']) == (n * 3 if resident else 0) and
            len(row['pages_after']) == (n * 3 if resident and not free else 0), 'page lifetime evidence missing')
    for i, a in enumerate(row['pages_before']):
        require(a['address'] == row['origins'][i // 3]['old_start'] + (i % 3) * 4096, 'original page slot differs')
        if masks[i // 3] & (1 << (i % 3)):
            require(a['pfn'] > 0 and a['hash'] > 0 and a['maps'] == 1 and a['refs'] == 2 and
                    not a['locked'] and a['charged_same'], 'original page ownership missing')
        else:
            require(all(a[k] == 0 for k in ('pfn','hash','maps','refs','locked','charged_same')), 'untouched input was pinned')
    for i, (a, b) in enumerate(zip(row['pages_before'], row['pages_after'])):
        require(a['address'] == b['address'] == row['origins'][i // 3]['old_start'] + (i % 3) * 4096, 'page reference slot differs')
        if changing and i == row['change']['index']: a = row['change']['page'][0]
        if not effective[i // 3] & (1 << (i % 3)):
            require(all(a[k] == b[k] == 0 for k in ('pfn','hash','maps','refs','locked','charged_same')), 'untouched slot gained a test reference')
            continue
        lost = (not native and i // 3 == 0) if inject else (not cancel or i // 3 != 1) and i % 3 == row['slice']
        require(a['maps'] == 1 and a['refs'] == 2 and a['pfn'] == b['pfn'] and a['hash'] == b['hash'] and
                b['maps'] == (not lost) and b['refs'] == 2 - lost and not b['locked'] and b['charged_same'], 'page identity/lock/reference/charge changed')
    fault_test = not native and not inject and not busy and not cancel
    require(len(row['ptes_before']) == len(row['ptes_after']) == n, 'PTE snapshots missing')
    for g, (a, b) in enumerate(zip(row['ptes_before'],row['ptes_after'])):
        gone = (7 if not native and g == 0 else 0) if inject else 0 if cancel and g == 1 else target
        zero = zeros[g]
        late = (1 << row['late_slot']) if fault_test and g == 1 and row['late_slot'] < 3 else 0
        require(not late or not ((masks[g] | zeros[g] | gone) & late), 'fault did not target an untouched survivor')
        for r, anon, z in ((a,masks[g],zero),(b,masks[g] & ~gone,(zero & ~gone) | late)):
            require(r['anon'] == anon and r['zero'] == z and r['none'] == (7 ^ (anon | z)) and r['other'] == 0,
                    'unexpected PTE creation, retention or removal')
            require(len(r['pfn']) == 3 and all(r['pfn'][p] == (row['pages_before'][g*3+p]['pfn'] if anon & (1<<p) else 0)
                    for p in range(3)), 'PTE physical slot identity differs')
    if fault_test:
        require(row['late_fault_blocked'] == 1 and row['late_fault_code'] == row['late_fault_value'] == 0 and
                'kd_mmap_down_read' in row['late_fault_stack'] and 'do_user_addr_fault' in row['late_fault_stack'],
                'real retained-neighbor fault ordering missing')
    require(len(row['residency']) == 3, 'before/body/writable resident accounting missing')
    for phase, observations in enumerate(row['residency']):
        require(len(observations) == n, 'resident accounting groups differ')
        for g, entries in enumerate(observations):
            require(len(entries) == 3, 'resident accounting slots differ')
            gone = (7 if not native and g == 0 else 0) if inject else 0 if cancel and g == 1 else target
            resident_mask = masks[g] if phase == 0 else masks[g] & ~gone if phase == 1 else 7 & ~gone
            for p, entry in enumerate(entries):
                expected_layout = dict(mapped=1, lo=0, hi=12288) if not phase else row['origins'][g]['layouts'][p]
                require(all(entry[k] == expected_layout[k] for k in ('mapped', 'lo', 'hi')), 'resident accounting VMA identity differs')
                expected_kb = 4 * sum(bool(resident_mask & (1 << q)) and entry['lo'] <= q * 4096 < entry['hi']
                                      for q in range(3)) if entry['mapped'] else 0
                require(entry['rss_kb'] == entry['anonymous_kb'] == expected_kb, 'unexpected resident population or accounting leak')
    def independent(r):
        require(r['zero'] & 1 and not ((r['anon'] | r['none'] | r['other']) & 1) and r['pfn'][0] == 0,
                'independent zero mapping changed')
    independent(row['independent_before']); independent(row['independent_after'])
    require(len(row['ptes_written']) == n, 'final private states missing')
    steps = iter(row['writes']); count = 0
    for g in range(n):
        gone = (7 if not native and g == 0 else 0) if inject else 0 if cancel and g == 1 else target
        written = 0
        for p in range(3):
            if (gone | masks[g]) & (1 << p): continue
            step = next(steps, None); require(step is not None, 'missing isolated write')
            require((step['group'], step['slot']) == (g, p), 'write order or identity differs')
            written |= 1 << p; anon = (masks[g] | written) & ~gone; r = step['state']
            require((r['anon'], r['zero'], r['none'], r['other']) == (anon, 7 & ~(anon | gone), gone, 0),
                    'write changed another survivor or failed private conversion')
            pfns = [r['pfn'][q] for q in range(3) if anon & (1 << q)]
            require(all(pfns) and len(set(pfns)) == len(pfns), 'private survivors alias')
            for q in range(3):
                if masks[g] & ~gone & (1 << q):
                    require(r['pfn'][q] == row['pages_before'][g * 3 + q]['pfn'], 'resident survivor moved during zero write')
            independent(step['independent']); count += 1
        r = row['ptes_written'][g]
        require((r['anon'], r['zero'], r['none'], r['other']) == (7 & ~gone, 0, gone, 0), 'final private survivor state differs')
    require(next(steps, None) is None, 'unexpected write evidence')
    return dict(zero_target_checks=True,isolated_private_writes=count,remote_zero_removals=len(zero_done),remote_without_private_holds=sum(not masks[identity(r)[0]] for r in zero_done),remote_changed_private_removals=len(private_rows),controlled_target_change=bool(changing),remote_resident_removals=len(private_rows),remote_post_split_errors=expected['failed'],
                native_error_control=bool(native and inject),native_success_control=bool(native and not inject),
                per_vma_residency_checks=True,matched_acks=expected['acks'],pre_effect_rollback=bool(busy),cancelled=expected['cancelled'],
                retained_mapping_and_reference_checks=True,cleanup_calls=n*3,readers_local=True,jit_bodies=0)
