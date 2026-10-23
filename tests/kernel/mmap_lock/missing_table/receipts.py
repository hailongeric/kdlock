#!/usr/bin/env python3
"""Bind a missing leaf table to native VMA removal and exact upper identity."""
from pathlib import Path
import re
import runpy

common = runpy.run_path(str(Path(__file__).parents[1] / 'zero_target/receipts.py'))
require = common['require']
IDENT = common['IDENT']
compare_native = common['compare_native']
compare_success = common['compare_success']
SHAPES = ('prefix-uu', 'middle-uu', 'suffix-uu')
MODES = {'change-table-empty': 3, 'change-table-zero': 4, 'change-table-private': 5}


def validate(row, log):
    evidence = common['validate'](row, log, absent=True, missing=True)
    require(row['page_size']==4096 and row['pmd_size']==2<<20 and row['pud_size']==1<<30 and
            row['pgdir_size'] in (1<<39,1<<48), 'captured x86 base-page geometry differs')
    n, native, inject = row['groups'], row['native'], row['injection']
    mode = MODES.get(row['shape'], 0)
    upper = row['upper_refusal']; fault = row['fault_interaction'] and not native
    group = 0 if native else 1
    require(row['shape'] in (*SHAPES, *MODES, 'upper-refusal', 'fault', 'cancel-empty') and
            upper == (row['shape'] == 'upper-refusal') and
            row['fault_interaction'] == (row['shape'] == 'fault') and
            row['changing_empty'] == (mode == 3) and row['changing_zero'] == (mode == 4) and
            row['changing'] == bool(mode) and not row['missing_table'] and
            not row['busy_page'], 'missing-table fixture or transition differs')
    require(row['table_bytes_before'] > 0 and
            row['table_bytes_after'] == row['table_bytes_before'] + 4096 * bool(mode or fault),
            'unexpected table allocation/free during body or controlled fault')
    require(all(len(row[k]) == n for k in ('anchors', 'tables_before', 'tables_after',
            'walks_before', 'walks_after', 'walks_accessed', 'walks_written', 'walks_cleanup')),
            'table lifetime observations missing')

    def walk(w, leaf, missing_upper):
        require(w['leaf'] == (7 if leaf else 0) and w['upper_none'] == (7 if missing_upper else 0) and
                w['pmd_none'] == (7 if not leaf and not missing_upper else 0), 'wrong page-table level classified')
        for key, present in (('parent_pfn', not missing_upper), ('table_pfn', leaf)):
            values = w[key]
            require(len(values) == 3 and (values[0] > 0 and len(set(values)) == 1 if present else values == [0, 0, 0]),
                    'table physical identity absent, aliased by slot or fabricated')

    for g, origin in enumerate(row['origins']):
        start, end = origin['old_start'], origin['old_end']; anchor = row['anchors'][g]
        require(end - start == 3 * 4096 and start >> 21 == (end - 1) >> 21 and
                anchor == start + (2 << 20) and anchor >> 21 != start >> 21 and anchor >> 30 == start >> 30,
                'impossible target/anchor table geometry')
        if g: require(start - row['origins'][g-1]['old_start'] == (1 << 30 if upper else 4 << 20), 'groups share the wrong table interval')
        old, after, accessed, written, cleaned = [row['walks_'+s][g] for s in ('before', 'after', 'accessed', 'written', 'cleanup')]
        old_leaf = bool(inject and not native and g == 0)
        after_leaf = old_leaf or bool(mode and g == group) or bool(fault and g == 1)
        absent_upper = bool(upper and g == 1)
        walk(old, old_leaf, absent_upper); walk(after, after_leaf, absent_upper)
        require(old['parent_pfn'] == after['parent_pfn'], 'unmap replaced or lost a required upper table')
        if old_leaf: require(old['table_pfn'] == after['table_pfn'], 'preservation-head table replaced')
        for w, t in ((old, row['tables_before'][g]), (after, row['tables_after'][g])):
            require(t == dict(leaf=w['leaf'], higher_none=7 ^ w['leaf'], pfn=w['table_pfn']), 'two page-table observations disagree')
        walk(accessed, True, False); walk(written, True, False)
        require(accessed == written, 'private writes freed or replaced a table')
        if not absent_upper: require(accessed['parent_pfn'] == old['parent_pfn'], 'later read fault replaced upper tables')
        if after_leaf: require(accessed['table_pfn'] == after['table_pfn'], 'later survivor access replaced the installed leaf')
        walk(cleaned, False, True)
    if not fault:
        require(not any(row[k] for k in ('late_fault_blocked','late_fault_code','late_fault_value','late_fault_stack')),
                'unrecorded concurrent fault obscures missing-table observations')

    origins = {str(o['tid']): (g, o) for g, o in enumerate(row['origins'])}
    done = re.findall(r'KD_MM_UNMAP done ' + IDENT + r' result=0', log)
    errors = re.findall(r'KD_MM_UNMAP error ' + IDENT + r' result=-12', log)
    expected_missing = [r for r in done if not (mode and origins[r[2]][0] == group)]
    suffix = r' pmd_table_pfn=([0-9a-f]+) pmd_none=1 held=0 released=0 target_owned=0 upper_retained=1 tables_unchanged=1'
    actual = re.findall(r'KD_MM_MISSING_TABLE done ' + IDENT + suffix, log)
    failures = re.findall(r'KD_MM_MISSING_TABLE error ' + IDENT + suffix + r' result=-12', log)
    require(sorted(r[:6] for r in actual) == sorted(expected_missing) and
            sorted(r[:6] for r in failures) == sorted(errors), 'missing-table body/error receipt not bound to completion')
    for r in actual + failures:
        g, _ = origins[r[2]]
        require(row['walks_before'][g]['pmd_none'] == 7 and
                int(r[6], 16) == row['walks_before'][g]['parent_pfn'][0] > 0,
                'body used a stale or nonexistent PMD table')
    require(evidence['remote_missing_table_removals'] == len(actual), 'missing-table removal count differs')

    transitions = list(re.finditer(r'KD_MM_TEST table_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+) before_table_none=1 after_zero=(\d+) after_private=(\d+) table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=([0-9a-f]+) anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) result=0', log))
    require(len(transitions) == bool(mode), 'table appearance control missing/duplicated')
    c, more = row['change'], row['change_more']
    if mode:
        require(more['mode'] == mode and not more['before_none'] and not more['table_before'] and
                more['table_after'] == row['walks_after'][group]['table_pfn'][0] > 0 and
                not more['anon_before'] and bool(more['anon_after']) == (mode == 5) and
                more['after_zero'] == (mode == 4), 'fault-created table/metadata state differs')
        require(c['done'] == 1 and c['result'] == c['before_zero'] == 0 and
                c['after_private'] == (mode == 5) and c['index'] == group*3+row['slice'] and
                c['pending'] == (0 if native else 3) and c['readers'] == (1 if native else 2) and
                (native or c['admission'] == -1) and c['actor'] > 0 and
                (c['actor'] == row['origins'][0]['tid'] if native else str(c['actor']) not in origins),
                'table fault was not performed on the existing reader before execution')
        if mode == 5:
            require(len(c['page']) == 1 and not c['zero_pfn'], 'new private page identity absent')
            p = c['page'][0]
            require(p['address'] == row['origins'][group]['start'] and p['pfn'] > 0 and p['hash'] > 0 and
                    p['maps'] == 1 and p['refs'] == 2 and not p['locked'] and p['charged_same'], 'new private reference invalid')
        else: require(not c['page'] and (c['zero_pfn'] > 0 if mode == 4 else c['zero_pfn'] == 0), 'empty/zero target acquired ownership')
        r = transitions[0].groups()
        require(int(r[0], 16) == row['mm'] and tuple(map(int, r[1:9])) ==
                (c['index'], c['actor'], c['pending'], c['readers'], c['admission'], mode, more['after_zero'], c['after_private']) and
                tuple(int(x, 16) for x in r[9:]) == (0, more['table_after'], 0, more['anon_after'], c['zero_pfn'], c['page'][0]['pfn'] if mode == 5 else 0),
                'transition receipt does not describe the observed table and target')
        if not native:
            tag = {3: 'ABSENT_TARGET', 4: 'ZERO_TARGET', 5: 'RESIDENT_PARTIAL'}[mode]
            body = re.search('KD_MM_'+tag+r' done '+IDENT, log)
            require(body and body.group(3) == str(row['origins'][group]['tid']) and transitions[0].end() < body.start(),
                    'table-change body not paired with the actual modified request')
            if mode == 4:
                zero = re.search('KD_MM_ZERO_TARGET done '+IDENT+r' zero_pfn=([0-9a-f]+)',log)
                require(zero and int(zero.group(7),16)==c['zero_pfn'], 'wrong shared-zero target identity')
    else: require(not any(more.values()), 'unexpected table-change metadata')
    mixed = re.findall(r'KD_MM_MIXED_PARTIAL done '+IDENT+r' resident_mask=2 untouched_mask=5 held=1 released=1',log)
    require(len(mixed) == (mode == 5 and not native), 'private-target untouched survivor receipt missing')
    if mixed: require(mixed[0] == next(r for r in done if origins[r[2]][0] == group), 'private-target receipt range/owner differs')
    return dict(evidence,upper_table_identity_checks=True,missing_leaf_distinguished=True,
                controlled_table_appearance=bool(mode),local_table_cleanup_verified=True)
