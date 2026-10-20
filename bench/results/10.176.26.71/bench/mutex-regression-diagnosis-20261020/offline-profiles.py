#!/usr/bin/env python3
"""Audit diagnostic archives without treating profiles as throughput acceptance."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import posixpath
import re
import socket
from statistics import median
import sys
import tarfile
from types import SimpleNamespace

HELPER = 'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA = '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ORIGINAL_SHA = '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw-parent', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    output = args.report/'offline-review.json'
    assert not output.exists()
    sys.dont_write_bytecode = True
    helper_path = args.repo/HELPER
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location('maintained_inert_reader', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original_raw = args.raw_parent/'mutex-public-20261020-r2'
    assert helper.hashfile(original_raw/'archives.json') == ORIGINAL_SHA
    original_manifest = json.loads((original_raw/'archives.json').read_text())
    original_inventory = json.loads((original_raw/'input-inventory.json').read_text())
    assert helper.hashfile(original_raw/'input-inventory.json') == original_manifest['input_inventory_sha256']

    class JointAudit(helper.Audit):
        def retained_target(self, target):
            # Only the current archive and the pinned original archive may
            # satisfy a link. Resolve path components in memory, including
            # workspace -> replay view -> original bundle chains.
            roots = {self.guest_base.rstrip('/'): self.inventory,
                     original_manifest['guest_base']: original_inventory}
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
                parts = relative.split('/')
                inventory = roots[root]
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = inventory.get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = (link if link.startswith('/') else
                                  posixpath.join(root, posixpath.dirname(name), link))
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return relative in inventory
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    audit = JointAudit(SimpleNamespace(repo=args.repo,
        raw=args.raw_parent/'mutex-public-20261020-profiles-1', report=args.report))
    groups, links = audit.load_archives()
    audit.windows = []
    for group in original_manifest['groups']:
        audit.equal('pinned_original_archive_hash',
                    helper.hashfile(original_raw/group['file']), group['sha256'], group['file'])
    result, health = audit.jread('result.json'), audit.jread('health.json')
    plan, records, state = (audit.jread('matrix/'+name+'.json') for name in ('plan', 'records', 'status'))
    audit.expect('completed_profiles', result['passed'] and result['final_idle'] and
                 result['state'] == state['state'] == 'COMPLETE')
    audit.equal('profile_counts', [state['completed'], state['planned'], len(plan), len(records)], [40]*4)
    audit.equal('profile_source_git', audit.files['profile_replay.py'],
                helper.sha(audit.git_bytes('d3806e4', 'bench/mutex_api_compare/profile_replay.py')))
    audit.equal('scheduler_source_git', audit.files['scheduler.py'],
                helper.sha(audit.git_bytes('bc72912', 'bench/mutex_api_compare/run.py')))
    audit.equal('scheduler_copies', audit.files['scheduler.py'], audit.files['matrix/replay-scheduler.py'])
    audit.equal('profile_source_receipt', audit.files['profile_replay.py'], result['script_sha256'])
    audit.equal('retained_perf', audit.files['tools/perf'], result['perf_sha256'])
    audit.equal('health_verifier', audit.files['verify-profiles.py'], health['verifier_sha256'])
    audit.expect('functional_health', health['idle'] and health['functionally_valid'] ==
        health['sessions'] == health['drained'] == 40 and health['score_eligible'] == 0
        and not health['per_session_kernel_faults'])
    audit.equal('original_reference', audit.files['original-archives.json'], ORIGINAL_SHA)
    audit.equal('original_inputs_manifest', audit.files['matrix/frozen-inputs.json'],
                'df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73')
    frozen = audit.jread('matrix/frozen-inputs.json')
    original_files = {p: h for bundle in frozen.values() for p, h in bundle['files'].items()}
    provenance = audit.jread('matrix/replay-provenance.json')
    audit.equal('verified_exact_inputs', health['verified_original_files'], original_files)
    audit.equal('verified_exact_harness', health['verified_retained_harness'], provenance['retained_collector_files'])
    audit.equal('verified_input_counts', [len(original_files), len(health['verified_retained_harness'])], [4088, 336])
    with tarfile.open(original_raw/'matrix.tar.gz') as original_archive:
        original_host = json.loads(original_archive.extractfile('mutex-public-20261020-r2/matrix/host-state.json').read())
    for name, path in [('before', 'matrix/host-state.json'), ('after', 'host-evidence/host-after.json')]:
        host = audit.jread(path)
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            audit.equal('host_configuration', host[key], original_host[key], [name, key])
        for key in ('pid', 'args'):
            audit.equal('qemu_identity', host['qemu'][0][key], original_host['qemu'][0][key], [name, key])
        pins = lambda h: sorted((t['comm'], t['affinity']) for t in h['qemu'][0]['tasks'])
        audit.equal('qemu_thread_placement', pins(host), pins(original_host), name)
    analysis = audit.jread('analysis/profile-analysis.json')
    audit.equal('analysis_source', analysis['script_sha256'], audit.files['analysis/profile-analysis.py'])
    audit.equal('range_helper_source', analysis['ranges_helper_sha256'], audit.files['analysis/profile_summary.py'])
    audit.equal('range_sizes_source', analysis['symbol_sizes_sha256'], audit.files['analysis/module-symbol-sizes.json'])
    audit.equal('analyzed_record_bytes', analysis['records_sha256'], audit.files['matrix/records.json'])
    analyzed = {r['name']: r for r in analysis['sessions']}
    audit.equal('all_samples_usable', [len(analyzed), analysis['count'], analysis['usable']], [40]*3)
    sample_pattern = re.compile(r'^\s*(.*?)\s+(\d+)\s*/\s*(\d+)\s+\[(\d+)\]\s+'
        r'(\d+\.\d+):\s+(\d+)\s+cycles:k:\s+((?:0x)?[0-9a-fA-F]+)\s+(.*?)\s+\((.*)\)\s*$')
    classes, retirement = Counter(), []
    for index, (row, planned) in enumerate(zip(records, plan)):
        relative = Path(row['evidence_path']).relative_to(audit.guest_base.rstrip('/')).as_posix()
        audit.equal('session_record', row, audit.jread(relative+'/session.json'), row['name'])
        audit.equal('plan_fields', {k: row.get(k) for k in planned}, planned, row['name'])
        audit.equal('original_round_zero_order',
            [row['comparison_workload'], row['threads'], row['repeat'], row['comparison_arm']],
            result['order'][index], row['name'])
        audit.expect('diagnostic_scope', row['diagnostic'] and row['perf_record'] and
                     not row['pmu'] and not row['score_eligible'] and row['repeat'] == 0, row['name'])
        audit.expect('session_finished', row['execution_status'] == 'OK' and row['drained'] and
                     not row.get('cleanup_error'), row['name'])
        m = row['measurement']
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        audit.expect('business_result', (m['complete'] and m['data_ok']) if synthetic else m['ok'], row['name'])
        audit.equal('workers', [w['cpu'] for w in m['workers']], row['cpus'], row['name'])
        audit.expect('worker_progress', all(w['completed'] > 0 and w['error'] == 0 and
            w['observed_cpu'] == w['cpu'] for w in m['workers']), row['name'])
        audit.equal('worker_sum', sum(w['completed'] for w in m['workers']), m['completed'], row['name'])
        audit.peak(dict(row, whole_throughput_ops_s=m['completed']*1e9/m['wall_ns']), relative)
        audit.expect('kernel_log_clean', not helper.FAULT.search(
                    audit.contents[relative+'/kernel.log'].decode(errors='replace')), row['name'])
        if row['arm'] == 'kdlock':
            audit.equal('retirement', row['retired'], dict(state=2, modules=0, frames=0, writers=0), row['name'])
            audit.equal('immutable_publication', row['published_before'], row['published_after'], row['name'])
            audit.expect('jit_bounds', 0 <= row['jit_bodies'] <= m['completed'], row['name'])
            if not synthetic:
                audit.expect('return_bounds', 0 <= row['jit_completions'] <= row['jit_bodies'], row['name'])
            retirement.append(dict(name=row['name'], retired=row['retired']))
        if not synthetic:
            audit.equal('perf_control', [row['perf_exit_code'], row['perf_control_acks']],
                        [0, ['enable', 'disable', 'stop']], row['name'])
        a = analyzed[row['name']]
        for name, digest in a['hashes'].items():
            audit.equal('profile_artifact_binding', audit.files[relative+'/'+name], digest, [row['name'], name])
        all_period, worker_period, samples, cpus, tids = 0, 0, 0, set(), set()
        for line in audit.contents[relative+'/perf-samples.txt'].decode().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            match = sample_pattern.fullmatch(line)
            audit.expect('valid_sample', match is not None, [row['name'], line])
            if match is None:
                continue
            value = int(match[6])
            all_period += value
            if match[1].strip() == 'sc_worker':
                worker_period += value
                samples += 1
                cpus.add(int(match[4]))
                tids.add(int(match[3]))
        audit.equal('sample_arithmetic', [all_period, worker_period, samples],
                    [a['all_sampled_period'], a['worker_sampled_period'], a['worker_samples']], row['name'])
        audit.equal('sample_cohort', [sorted(cpus), len(tids)], [row['cpus'], row['threads']], row['name'])
        report = audit.contents[relative+'/perf-report.txt'].decode()
        audit.equal('no_lost_samples', re.findall(r'Total Lost Samples:\s*([\d,]+)', report), ['0'], row['name'])
    audit.equal('exact_retirement_health', retirement, health['exact_retirements'])
    audit.equal('compact_profile_analysis', helper.hashfile(args.report/'profile-analysis.json'),
                audit.files['analysis/profile-analysis.json'])
    answer = dict(consistent=not audit.issues, checks=sum(audit.counts.values()), issues=audit.issues,
        check_counts=dict(audit.counts), groups=groups, symlinks=len(links),
        sessions=40, reconstructed_windows=len(audit.windows), original_manifest_sha256=ORIGINAL_SHA,
        archives_manifest_sha256=helper.hashfile(audit.raw/'archives.json'),
        reviewer_host=socket.gethostname(), script_sha256=helper.hashfile(Path(__file__)),
        limits='Post-run thread-set mismatch remains a failed check. Flat profiles do not '
               'establish causal attribution, plain-throughput acceptance or latency.')
    output.write_text(json.dumps(answer, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: answer[k] for k in ('consistent', 'checks', 'sessions', 'archives_manifest_sha256')}))
    print('issues', Counter(issue['check'] for issue in audit.issues))
    return int(not answer['consistent'])


if __name__ == '__main__':
    raise SystemExit(main())
