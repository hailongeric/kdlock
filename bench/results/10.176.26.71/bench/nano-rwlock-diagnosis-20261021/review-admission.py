#!/usr/bin/env python3
"""Inert archive/source/receipt audit; never execute an archived program."""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ORIGINAL = '/root/kdlock-evidence/10.176.26.71/bench/nano-list-followup-20261020/timing-1/rwlock-w20'
REMOTE_PARENT = '/root/kdlock-evidence/10.176.26.71/bench/nano-rwlock-diagnosis-20261021'
RAW = ROOT/'bench/results/10.176.26.71/raw/bench'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def apply_checked_patch(original, text):
    """Reconstruct exact context, including old/new hunk extents; no fuzz."""
    changes, lines, cursor = {}, text.splitlines(keepends=True), 0
    while cursor < len(lines):
        assert lines[cursor].startswith('--- a/')
        name = lines[cursor][6:].strip()
        assert lines[cursor+1] == '+++ b/'+name+'\n'
        cursor += 2
        before, output, position = original[name].decode().splitlines(keepends=True), [], 0
        while cursor < len(lines) and lines[cursor].startswith('@@'):
            match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', lines[cursor])
            assert match
            old_start, old_count, new_start, new_count = map(int, match.groups())
            assert position <= old_start-1
            output.extend(before[position:old_start-1])
            position, consumed, produced = old_start-1, 0, 0
            assert len(output) == new_start-1
            cursor += 1
            while cursor < len(lines) and not lines[cursor].startswith(('@@', '--- a/')):
                line = lines[cursor]
                assert line[0] in ' +-'
                if line[0] in ' -':
                    assert before[position] == line[1:], (name, position)
                    position += 1
                    consumed += 1
                if line[0] in ' +':
                    output.append(line[1:])
                    produced += 1
                cursor += 1
            assert (consumed, produced) == (old_count, new_count)
        output.extend(before[position:])
        changes[name] = ''.join(output).encode()
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='admission-3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = RAW/'nano-rwlock-diagnosis-20261021'/args.run/'archives'
    out = args.output
    assert not out.exists()
    counts, issues = Counter(), []

    def check(condition, kind, detail=''):
        counts[kind] += 1
        if not condition:
            raise AssertionError((kind, detail))

    manifest, inventory = read(base/'archives.json'), read(base/'input-inventory.json')
    check(manifest['completed'] and manifest['guest_idle'], 'archive_completed')
    blobs, hashes, links, members = {}, {}, {}, set()
    for group in manifest['groups']:
        path = base/group['file']
        check(sha(path.read_bytes()) == group['sha256'] and path.stat().st_size == group['bytes'],
              'archive_hash_size', path.name)
        with tarfile.open(path) as archive:
            for member in archive:
                path = Path(member.name)
                check(path.parts[0] == args.run and '..' not in path.parts, 'safe_member', member.name)
                name = str(path.relative_to(args.run))
                check(name not in members and name in inventory, 'unique_member', name)
                members.add(name)
                stored = inventory[name]
                check(member.mode == stored['mode'] & 0o7777, 'mode', name)
                if member.isfile():
                    data = archive.extractfile(member).read()
                    check(len(data) == stored['bytes'], 'member_size', name)
                    blobs[name], hashes[name] = data, sha(data)
                elif member.issym():
                    check(member.linkname == stored['link'], 'link', name)
                    links[name] = member.linkname
                else:
                    check(member.isdir(), 'directory', name)
    check(members == set(inventory), 'complete_inventory')
    get = lambda name: json.loads(blobs[name])
    reused = get('reused-inputs.json')
    original_raw = RAW/'nano-list-followup-20261020/timing-1/archives'
    old_manifest = read(original_raw/'archives.json')
    compact_manifest = ROOT/'bench/results/10.176.26.71/bench/nano-list-followup-20261020/timing-1/archives.json'
    check((original_raw/'archives.json').read_bytes() == compact_manifest.read_bytes(),
          'original_archive_binding')
    expected_names = {str(Path(p).relative_to(ORIGINAL)) for p in reused}
    expected_names |= {'plan.json', 'build/provider/manifest.json'}
    originals = {}
    matrix = next(g for g in old_manifest['groups'] if g['file'] == 'matrix.tar.gz')
    check(sha((original_raw/'matrix.tar.gz').read_bytes()) == matrix['sha256'], 'original_matrix_hash')
    prefix = 'timing-1/rwlock-w20/'
    with tarfile.open(original_raw/'matrix.tar.gz') as archive:
        for member in archive:
            if member.isfile() and member.name.startswith(prefix) and member.name[len(prefix):] in expected_names:
                originals[member.name[len(prefix):]] = archive.extractfile(member).read()
    check(set(originals) == expected_names, 'original_input_coverage')
    for path, expected in reused.items():
        check(sha(originals[str(Path(path).relative_to(ORIGINAL))]) == expected, 'reused_hash', path)

    for path, expected in get('immutable-inputs.json').items():
        if path in reused:
            check(reused[path] == expected, 'immutable_reused')
        elif path.startswith(REMOTE_PARENT+'/'+args.run+'/'):
            name = path[len(REMOTE_PARENT+'/'+args.run+'/'):]
            check(hashes.get(name) == expected, 'immutable_new', name)
        else:
            name = {'/root/host_fs/kdlock/bench/rwlock_compare/admission.py': 'admission.py',
                    '/root/host_fs/kdlock/bench/archive_run.py': 'archive_run.py'}[path]
            check(hashes['diagnostic-inputs/'+name] == expected, 'immutable_runner', name)
    prepared = json.loads(originals['build/provider/manifest.json'])['prepared']
    original_provider = {p: originals['build/provider/'+p] for p in prepared}
    for name, expected in prepared.items():
        check(sha(original_provider[name]) == expected, 'original_prepared_source', name)
    changed = apply_checked_patch(original_provider, blobs['diagnostic-inputs/observation.patch'].decode())
    additions = {'include/kd_admission.h': 'kd_admission.h', 'kernel_module/kd_admission.c': 'kd_admission.c',
                 'include/kd_admission_fields.def': 'fields.def'}
    recipe = {**original_provider, **changed,
              **{p: blobs['diagnostic-inputs/'+n] for p, n in additions.items()}}
    diagnostic = get('diagnostic-source.json')
    check(set(recipe) == set(diagnostic), 'diagnostic_source_set')
    for name, data in recipe.items():
        check(sha(data) == diagnostic[name] == hashes['provider/'+name], 'diagnostic_reconstruction', name)
    oracle_path = ROOT/'bench/rwlock_compare/oracle.py'
    check(sha(oracle_path.read_bytes()) == sha(originals['source/bench/rwlock_compare/oracle.py']),
          'offline_oracle_binding')
    spec = importlib.util.spec_from_file_location('inert_rwlock_oracle', oracle_path)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    # The offline oracle only reads JSON and recomputes arithmetic.
    check(sha((ROOT/'bench/spin_cacheline/peak.py').read_bytes()) ==
          sha(originals['source/bench/spin_cacheline/peak.py']), 'offline_peak_binding')
    plan, run, rows = get('plan.json'), get('run.json'), []
    check(run['complete'] and run['final_idle'] and len(plan) == len(run['cases']) == 12, 'complete_plan')
    original_plan = {s['name']: s for s in json.loads(originals['plan.json'])}
    for case, outcome in zip(plan, run['cases']):
        name = case['name']
        frozen_case = original_plan[case['original_name']]
        check({k: v for k, v in case.items() if k not in ('name', 'original_name', 'diagnostic_provider')} ==
              {k: v for k, v in frozen_case.items() if k != 'name'}, 'unchanged_case', name)
        session = get(name+'/session.json')
        check(outcome['name'] == name and all(session[k] == v for k, v in case.items()), 'case_identity', name)
        check(session['drained'] and session['retired'] == dict(state=2, modules=0, writers=0, frames=0)
              and not session.get('cleanup_error'), 'exact_retirement', name)
        for phase in ('warmup', 'measure'):
            measured, phase_spec = get(name+'/'+phase+'.json'), get(name+'/'+phase+'.spec.json')
            peak = oracle.validate(measured, phase_spec)
            check(measured['data_ok'], 'phase_oracle', name+'/'+phase)
            # The raw client file precedes the collector's peak annotation.
            annotated = dict(measured)
            if peak:
                annotated['peak'] = peak
            if phase == 'measure':
                check(annotated == session['measurement'], 'measured_receipt', name)
            for position in ('before', 'after'):
                values = get(name+'/'+phase+'-'+position+'.admission.json')
                check(values == session['admission'][phase][position], 'phase_counter_receipt', name)
            before, after = (session['admission'][phase][k] for k in ('before', 'after'))
            delta = session['admission'][phase]['delta']
            for field, values in after.items():
                check(set(values) == {str(i) for i in range(64)}, 'counter_cpu_set', field)
                for cpu, value in values.items():
                    check(type(value) is int and value >= 0, 'counter_value', name)
                    if field not in ('cpu_entries_min', 'cpu_entries_max'):
                        check(delta[field][cpu] == value-before[field][cpu] >= 0, 'counter_delta', name)
            for cpu in (str(i) for i in range(64)) if delta else ():
                for total, parts in [
                    ('lock_record', ('lock_busy', 'lock_cpu_cold', 'lock_missing', 'lock_cold', 'lock_hot')),
                    ('root_entries', ('root_disabled', 'root_heat_refuse', 'root_context_refuse',
                                      'root_occupied_refuse', 'root_fast', 'root_contended')),
                    ('queue_checks', ('queue_unheld', 'queue_missing_tail', 'queue_short',
                                      'queue_missing_link', 'queue_pass'))]:
                    check(delta[total][cpu] == sum(delta[k][cpu] for k in parts),
                          'complete_classification', name+'/'+phase+'/'+cpu+'/'+total)
        measure = session['measurement']
        check(session['jit_bodies'] == session['jit_after']-session['jit_before'] ==
              session['jit_completions'] == session['jit_complete_after']-session['jit_complete_before'],
              'matching_jit', name)
        expected_status = 'OK' if session['jit_completions'] else 'NO_JIT'
        check(session['execution_status'] == outcome['status'] == expected_status and
              session['require_jit'] is True, 'strict_jit_status', name)
        check(session['published_before'] == session['published_after'], 'immutable_publication', name)
        entry = session['publication']['entry']
        check((entry['entry_abi'], entry['lock_kind'], entry['requirements'], entry['status']) == (3, 1, 0, 0),
              'image_contract', name)
        image = session['list_image_audit']
        uploaded = [p for p in blobs if p.startswith(name+'/workspace/') and p.endswith('/jit.bin')]
        check(len(uploaded) == 1 and blobs[uploaded[0]] == blobs[name+'/list-image/loaded.bin'],
              'loaded_bytes', name)
        check(image['loaded_sha256'] == image['uploaded_sha256'] == hashes[uploaded[0]] and
              image['byte_for_byte_match'], 'loaded_hash', name)
        counts_by_phase = {phase: {k: sum(v.values()) for k, v in data['delta'].items()}
                           for phase, data in session['admission'].items()}
        rows.append(dict(name=name, threads=session['threads'], repeat=session['repeat'],
                         arm='diagnostic' if session['diagnostic_provider'] else 'original',
                         status=expected_status, completed=measure['completed'], reads=measure['reads'],
                         writes=measure['writes'], whole_ops_s=measure['completed']*1e9/measure['wall_ns'],
                         peak_ops_s=measure['peak']['throughput_ops_s'], jit_completions=session['jit_completions'],
                         phase_counters=counts_by_phase, session_sha256=hashes[name+'/session.json']))
    check(run['passed'] == all(r['status'] == 'OK' for r in rows), 'overall_strict_result')
    before, after = get('host-before.json'), get('host-after.json')
    bq, aq = before['qemu'][0], after['qemu'][0]
    check(bq['pid'] == aq['pid'] == 257489 and bq['args'] == aq['args'] and
          before['cpufreq'] == after['cpufreq'] and before['numa'] == after['numa'], 'host_configuration')
    check(before['pins_verified'] and after['pins_verified'] and len(bq['tasks']) == 67, 'host_pins')
    if sorted(bq['tasks'], key=lambda t: t['tid']) != sorted(aq['tasks'], key=lambda t: t['tid']):
        issues.append(dict(check='host_after_thread_set', before=len(bq['tasks']), after=len(aq['tasks'])))
    groups = defaultdict(list)
    for row in rows:
        groups[(row['threads'], row['arm'])].append(row)
    summaries = []
    for (threads, arm), group in groups.items():
        rates = [r['whole_ops_s'] for r in group]
        summaries.append(dict(threads=threads, arm=arm, samples=len(rates), min=min(rates), max=max(rates),
                              median=statistics.median(rates),
                              spread_pct=100*(max(rates)-min(rates))/statistics.median(rates),
                              sample_cv_pct=100*statistics.stdev(rates)/statistics.mean(rates)))
    result = dict(evidence_integrity_passed=True, strict_passed=run['passed'], endpoint_issues=issues,
                  checks=sum(counts.values()), check_counts=dict(counts), rows=rows, groups=summaries,
                  files=len(blobs), links=len(links), run=args.run,
                  archive_manifest_sha256=sha((base/'archives.json').read_bytes()),
                  scope='Diagnostic rates include changed layout and counter overhead; no acceptance claim')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'groups', 'check_counts')}, sort_keys=True))


if __name__ == '__main__':
    main()
