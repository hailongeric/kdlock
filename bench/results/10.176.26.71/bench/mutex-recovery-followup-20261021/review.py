#!/usr/bin/env python3
"""Read original/follow-up archives as inert data; never execute their code."""
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
from statistics import mean, median, stdev
import sys
from types import SimpleNamespace

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
REPORT = ROOT/'bench/results/10.176.26.71/bench/mutex-recovery-followup-20261021'
RAW = ROOT/'bench/results/10.176.26.71/raw/bench'
POINTS = {('c08', 3), ('c08', 4), ('c08', 5), ('pipebytes', 3),
          ('pipebytes', 5), ('pipecap', 5), ('rcuht', 2)}
ORIGINAL_MANIFEST = '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def execution_class(row):
    if row['arm'] != 'kdlock':
        return 'NOT_APPLICABLE'
    if row['comparison_workload'] in ('c08', 'rcuht'):
        return 'WITNESSED_JIT' if row['jit_bodies'] else 'NO_JIT'
    return ('RETURNED_JIT' if row['jit_completions'] else
            'PARTIAL_JIT' if row['jit_bodies'] else 'NO_JIT')


def main():
    sys.dont_write_bytecode = True
    helper_path = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == \
        '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('maintained_inert_reader', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    out = REPORT/'review-1'
    out.mkdir()
    original_raw = RAW/'mutex-public-20261020-r2'
    new_raw = RAW/'mutex-recovery-followup-20261021/archives-1'
    assert helper.hashfile(original_raw/'archives.json') == ORIGINAL_MANIFEST
    roots = {}
    for folder in (original_raw, new_raw):
        archive = json.loads((folder/'archives.json').read_text())
        roots[archive['guest_base'].rstrip('/')] = json.loads((folder/'input-inventory.json').read_text())

    class JointAudit(helper.Audit):
        def retained_target(self, target):
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in roots if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                relative = target[len(root):].lstrip('/')
                if not relative:
                    return True
                if not helper.safe_relative(relative):
                    return False
                parts, inventory = relative.split('/'), roots[root]
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = inventory.get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = link if link.startswith('/') else posixpath.join(root, posixpath.dirname(name), link)
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return True
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    audits = []
    for folder in (original_raw, new_raw):
        audit = JointAudit(SimpleNamespace(repo=ROOT, raw=folder, report=out))
        audit.load_archives()
        audits.append(audit)
    old, new = audits
    new.windows = []
    health = new.jread('final-health.json')
    transition = new.jread('transition-1/result.json')
    result = new.jread('run-1/result.json')
    new.equal('original_archive_binding', new.files['original-archives.json'], ORIGINAL_MANIFEST)
    new.equal('transition_binding', new.files['transition-1/result.json'], result['transition_sha256'])
    new.equal('retained_transition_binding', new.files['run-1/transition.json'], result['transition_sha256'])
    new.equal('old_boot', old.archive['boot_id'], transition['original_boot_id'])
    new.equal('new_boot', new.archive['boot_id'], transition['new_boot_id'])
    new.expect('separate_boot', old.archive['boot_id'] != new.archive['boot_id'])
    new.expect('verified_recovery', transition['passed'] and transition['recovery_preserved'] and
               transition['kernel_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960')
    new.equal('driver_git_binding', new.files['run-1/recovery_replay.py'],
              helper.sha(new.git_bytes(result['source_commit'], 'bench/mutex_api_compare/recovery_replay.py')))
    new.equal('scheduler_git_binding', new.files['run-1/scheduler.py'],
              helper.sha(new.git_bytes(result['source_commit'], 'bench/mutex_api_compare/run.py')))
    frozen = old.jread('frozen-inputs.json')
    checked = {p: h for bundle in frozen.values() for p, h in bundle['files'].items()}
    harness = {old.guest_base+'harness/'+p.removeprefix('/root/host_fs/kdlock/'): h
               for p, h in old.jread('harness-inputs.json').items()}
    new.equal('health_input_sets', [health['verified_original_files'], health['verified_retained_harness']],
              [checked, harness])
    new.equal('original_input_counts', [len(checked), len(harness)], [4088, 336])
    for path, digest in {**checked, **harness}.items():
        new.equal('original_file_hash', old.files[path.removeprefix(old.guest_base)], digest, path)
    for path, digest in new.jread('checks-1/source-sha256.json').items():
        new.equal('frozen_test_source_hash', new.files['checks-1/source/'+path], digest, path)
    new.expect('basic_affected_tests', new.jread('checks-1/result.json')['passed'])

    prefix = 'run-1/matrix/'
    records, plan, state = (new.jread(prefix+n+'.json') for n in ('records', 'plan', 'status'))
    new.equal('completed_run', [state['state'], state['completed'], state['planned'], len(records), len(plan)],
              ['COMPLETE', 84, 84, 84, 84])
    selected = [r for r in old.jread('matrix/records.json')
                if (r['comparison_workload'], r['threads']) in POINTS]
    old_by_name = {r['name']: r for r in selected}
    order = [r for r in old.jread('matrix/execution-order.json') if tuple(r[:2]) in POINTS]
    new.equal('original_rotated_order', new.jread(prefix+'execution-order.json'), order)
    new.equal('same_selected_names', sorted(old_by_name), sorted(r['name'] for r in records))
    settings = ('comparison_workload', 'threads', 'repeat', 'comparison_arm', 'arm',
        'source_identity', 'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes',
        'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
        'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker', 'warmup',
        'warmup_ms', 'warmup_policy', 'warmup_pause_seconds', 'entries', 'value_size',
        'file_descriptions', 'syscalls_per_op', 'post_work_rounds', 'numa_policy',
        'spin_entry_ratio_limit', 'spin_prefetch', 'delegation_batch_limit',
        'kd_provider_ubsan', 'diagnostic', 'pmu', 'perf_record')
    for index, row in enumerate(records):
        name = row['evidence_path'].removeprefix(new.guest_base)
        new.equal('session_plan_binding', {k: row.get(k) for k in plan[index]}, plan[index], name)
        new.equal('session_record_binding', row, new.jread(name+'/session.json'), name)
        new.equal('original_settings', {k: row.get(k) for k in settings},
                  {k: old_by_name[row['name']].get(k) for k in settings}, name)
        new.expect('session_valid_drained', row['execution_status'] == 'OK' and row['drained'] and
                   not row.get('cleanup_error'), name)
        new.expect('kernel_log_no_fault_match', not helper.FAULT.search(new.contents[name+'/kernel.log'].decode()), name)
        m = row['measurement']
        new.expect('measurement_binding', all(m.get(k) == v for k, v in new.jread(name+'/measure.json').items()), name)
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        new.expect('business_oracle', m['complete'] and m['data_ok'] if synthetic else m['ok'], name)
        if synthetic:
            delta = [b-a for a, b in zip(m['before'], m['after'])]
            if row['comparison_workload'] == 'c08':
                new.equal('cacheline_oracle', delta, [m['completed']]*8+[0]*8, name)
            else:
                new.expect('hash_oracle', m['hash_integrity_ok'] and delta[0] == m['completed'] and
                    m['before'][0] == sum(m['before'][1:4]) and m['after'][0] == sum(m['after'][1:4]) and
                    not any(m['before'][4:]+m['after'][4:]), name)
        new.peak(dict(row, whole_throughput_ops_s=m['completed']*1e9/m['wall_ns']), name)
        if row['arm'] == 'kdlock':
            new.equal('exact_retirement', row['retired'], dict(state=2, modules=0, writers=0, frames=0), name)
            new.equal('stable_publication', row['published_before'], row['published_after'], name)
            new.expect('jit_entry_bounds', 0 <= row['jit_bodies'] <= m['completed'], name)
            if not synthetic:
                new.expect('jit_return_bounds', 0 <= row['jit_completions'] <= row['jit_bodies'], name)
            for filename, digest in row['published_before']['images'].items():
                new.expect('published_image_retained', any(p.startswith(name+'/workspace/') and
                    Path(p).name == filename and h == digest for p, h in new.files.items()), [name, filename])
    new.equal('health_operation_sum', health['completed_operations'], sum(r['measurement']['completed'] for r in records))
    new.equal('health_classes', health['execution_classes'], dict(Counter(execution_class(r) for r in records)))
    new.equal('health_retirements', health['exact_retirements'],
              [dict(name=r['name'], retired=r['retired']) for r in records if r['arm'] == 'kdlock'])

    original_host = old.jread('matrix/host-state.json')
    host_issues = []
    for phase, host in [('before', new.jread(prefix+'host-state.json')), ('after', new.jread('host-after-1.json'))]:
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            new.equal('host_configuration', host[key], original_host[key], [phase, key])
        for key in ('pid', 'args'):
            new.equal('same_qemu', host['qemu'][0][key], original_host['qemu'][0][key], [phase, key])
        tasks = lambda h: sorted(h['qemu'][0]['tasks'], key=lambda t: t['tid'])
        if tasks(host) != tasks(original_host):
            host_issues.append(dict(phase=phase, expected_threads=len(tasks(original_host)),
                                    actual_threads=len(tasks(host)), reason='Strict original thread set differs'))
        def memory(h):
            return [(f[0], f[1], next(v for v in f if v.startswith('kernelpagesize_kB=')))
                    for line in h['qemu'][0]['numa_maps'].splitlines()
                    if len(f := line.split()) > 1 and f[1].startswith('bind:')]
        new.equal('same_host_memory_binding', memory(host), memory(original_host), phase)
    old_env, new_env = old.jread('matrix/environment.json'), new.jread(prefix+'environment.json')
    for key in ('cmdline', 'preemption', 'packages', 'python', 'snapshot_tag', 'collector_topology'):
        new.equal('same_guest_configuration', new_env[key], old_env[key], key)
    new.equal('bound_new_boot', new_env['boot_id'], transition['new_boot_id'])
    new.equal('same_guest_topology', new.jread(prefix+'topology.json'), old.jread('matrix/topology.json'))

    per_repeat, summaries = [], []
    for collection, rows in [('original', selected), ('followup', records)]:
        groups = defaultdict(list)
        for row in rows:
            m = row['measurement']
            item = dict(collection=collection, name=row['name'], workload=row['comparison_workload'],
                threads=row['threads'], arm=row['comparison_arm'], repeat=row['repeat'],
                execution_class=execution_class(row), whole_ops_s=m['completed']*1e9/m['wall_ns'],
                jit_entries=row.get('jit_bodies'), jit_returns=row.get('jit_completions'),
                evidence_path=row['evidence_path'])
            per_repeat.append(item)
            groups[(item['workload'], item['threads'], item['arm'], item['execution_class'])].append(item)
        for key, group in sorted(groups.items()):
            rates = [r['whole_ops_s'] for r in group]
            summaries.append(dict(collection=collection, workload=key[0], threads=key[1], arm=key[2],
                execution_class=key[3], repeats=sorted(r['repeat'] for r in group),
                complete_three_repeats=sorted(r['repeat'] for r in group) == [0, 1, 2],
                minimum=min(rates), median=median(rates), maximum=max(rates),
                spread_pct=100*(max(rates)-min(rates))/median(rates),
                sample_cv_pct=100*stdev(rates)/mean(rates) if len(rates)>1 else None))
    comparisons = []
    for collection in ('original', 'followup'):
        for workload, threads in sorted(POINTS):
            groups = [g for g in summaries if (g['collection'], g['workload'], g['threads']) ==
                      (collection, workload, threads)]
            public = [g for g in groups if g['arm'] == 'public-kd']
            outer = [g for g in groups if g['arm'] == 'baseline-kd']
            complete = len(public) == len(outer) == 1 and public[0]['complete_three_repeats'] and \
                outer[0]['complete_three_repeats'] and public[0]['execution_class'] == outer[0]['execution_class']
            comparisons.append(dict(collection=collection, workload=workload, threads=threads,
                complete_same_class=complete, direct_outer_ratio=public[0]['median']/outer[0]['median'] if complete else None,
                public_groups=public, outer_groups=outer, disposition='UNRESOLVED_CAUSE'))
    save(out/'groups.json', summaries)
    save(out/'comparisons.json', comparisons)
    with (out/'per-repeat.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_repeat[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(per_repeat)
    issues = [dict(archive=a.raw.name, **issue) for a in audits for issue in a.issues]
    review = dict(integrity_passed=not issues, checks=sum(sum(a.counts.values()) for a in audits),
        integrity_issues=issues, environment_issues=host_issues, accepted=False,
        original_manifest_sha256=ORIGINAL_MANIFEST, followup_manifest_sha256=helper.hashfile(new_raw/'archives.json'),
        members={a.raw.name: len(a.members) for a in audits}, reconstructed_peak_windows=len(new.windows),
        sessions=len(records), exact_retirements=len(health['exact_retirements']),
        original_input_files=len(checked), retained_harness_files=len(harness),
        completed_operations=health['completed_operations'], source_sha256=helper.hashfile(Path(__file__)),
        scope='Inert archive hashes/inventories/links, exact frozen inputs, source bindings, selected settings, '
              'business/worker checks, reconstructed peaks, JIT evidence, retirements and environment comparisons. '
              'No archived code executed; descriptive statistics only, no causal acceptance.')
    save(out/'review.json', review)
    for name, member in [('checks-1.json', 'checks-1/result.json'), ('transition-1.json', 'transition-1/result.json'),
                         ('run-1.json', 'run-1/result.json'), ('archives.json', None)]:
        (REPORT/name).write_bytes((new_raw/'archives.json').read_bytes() if member is None else new.contents[member])
    save(REPORT/'health-summary.json', {k: v for k, v in health.items() if k not in
        ('verified_original_files', 'verified_retained_harness', 'checks', 'exact_retirements')})
    print(json.dumps(review, indent=2))
    print(json.dumps([c for c in comparisons if c['collection'] == 'followup'], indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
