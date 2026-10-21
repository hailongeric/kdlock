#!/usr/bin/env python3
"""Read fixed archives and Git objects as inert data; execute no archived code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import sys
import tarfile
from types import SimpleNamespace

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1]/'raw/bench'
MANIFEST = 'c665228f06d3c5cd6ba85fb62c4e7609d4f1cc4a4d8ac58d26c439d333317c10'
ORIGINAL = '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'


def main():
    sys.dont_write_bytecode = True
    path = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('maintained_inert_reader', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    old, new = RAW/'mutex-public-20261020-r2', RAW/HERE.name/'archives-1'
    roots = {}
    for folder, digest in ((old, ORIGINAL), (new, MANIFEST)):
        assert helper.hashfile(folder/'archives.json') == digest
        manifest = json.loads((folder/'archives.json').read_text())
        assert helper.hashfile(folder/'input-inventory.json') == manifest['input_inventory_sha256']
        roots[manifest['guest_base']] = json.loads((folder/'input-inventory.json').read_text())

    class Audit(helper.Audit):
        def retained(self, target):
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
                parts = relative.split('/')
                for n in range(1, len(parts)+1):
                    name = '/'.join(parts[:n])
                    item = roots[root].get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = link if link.startswith('/') else posixpath.join(root, posixpath.dirname(name), link)
                        if n < len(parts):
                            target = posixpath.join(target, *parts[n:])
                        break
                else:
                    return True
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained(detail['target'])
            return super().check(value, label, detail)

    audit = Audit(SimpleNamespace(repo=ROOT, raw=new, report=HERE))
    groups, links = audit.load_archives()
    check, read = audit.check, audit.jread
    health, result = read('final-health.json'), read('correctness-1/result.json')
    check(health['idle'] and health['matching_runtime_modules'] and not health['accepted'], 'final_idle_unaccepted')
    check(result['passed'] and result['final_idle'] and result['planned'] == result['completed'] == 4, 'correctness_complete')
    check(audit.files['correctness-1/runner.py'] == helper.sha(audit.git_bytes(result['source_commit'],
          'bench/mutex_api_compare/unlock_run.py')), 'runner_git_binding')
    checks = read('checks-1/result.json')
    check(checks['passed'] and checks['unit_basic'] == 2 and len(checks['unit_drivers']) == 6, 'basic_affected_passed')
    committed = read('checks-1/committed-source.json')
    check(checks['committed_manifest_sha256'] == audit.files['checks-1/committed-source.json'], 'committed_manifest_binding')
    for name, digest in read('checks-1/source-sha256.json').items():
        check(audit.files['checks-1/source/'+name] == digest == committed['files'][name] ==
              helper.sha(audit.git_bytes(checks['source_revision'], name)), 'tested_source_git_binding', name)
    inputs = read('inputs-1/inputs.json')
    check(audit.files['inputs-1/inputs.json'] == result['inputs_sha256'] == health['derivative_manifest_sha256'], 'derivative_binding')
    for name, digest in inputs['immutable_files'].items():
        check(audit.files.get('inputs-1/'+name) == digest, 'derivative_immutable_hash', name)
    for name, digest in inputs['bundle']['files'].items():
        check(audit.files.get(name.removeprefix(audit.guest_base)) == digest, 'bundle_hash', name)
    check(audit.files['inputs-1/bundle/build/kdlock_km.ko'] == inputs['provider_sha256'] == health['provider_sha256'], 'original_provider_retained')
    check(audit.files['inputs-1/bundle/build/kdlock-pipecap/real_api.ko'] == inputs['derivative_workload_sha256'], 'actual_derivative_binary')
    elf = read('elf-checks-2.json')
    check(elf['passed'] and not elf['loaded'] and len(elf['rejected']) == 3 and
          elf['candidate_sha256'] == inputs['derivative_workload_sha256'], 'actual_elf_audit')
    task = read('task-2/result.json')
    check(task['passed'] and task['drained'] and task['acks'] == 4 and
          task['registry_stress_iterations'] == 4096, 'live_acks_registry')
    check(audit.files['task-1/kdlock_km.ko'] == audit.files['task-2/kdlock_km.ko'] == health['task_retry_binary_sha256'], 'unchanged_probe_retry')
    check('task-1/result.json' not in audit.files and b'Cannot allocate memory' in audit.contents['task-1/load.log'], 'failed_probe_not_pass')
    for name, digest in read('allocator-refresh-1/failed-attempt-sha256.json').items():
        check(audit.files['task-1/'+name] == digest, 'failed_attempt_retained', name)
    for attempt in ('task-1', 'task-2'):
        for name, digest in read(attempt+'/sources.json').items():
            check(audit.files[attempt+'/source/'+name] == digest ==
                  helper.sha(audit.git_bytes(result['source_commit'], name)), 'task_source_git_binding', name)
    totals = [0, 0, 0]
    records = []
    for row in result['records']:
        arm = 'outer' if row['comparison_arm'] == 'original-outer' else 'general'
        prefix = 'correctness-1/'+arm+'/'+row['name']+'/'
        check(read(prefix+'session.json') == row, 'session_result_binding')
        work = read(prefix+'correctness-work.json')
        check(work == row['correctness_work'] and work['ok'] and row['drained'] and
              row['execution_status'] == 'OK', 'work_complete_drained')
        check(row['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'exact_retirement')
        check(row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32, 'loaded_mutex_placement')
        check(len(work['workers']) == row['threads'] and sum(w['completed'] for w in work['workers']) == work['completed'] and
              all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] >= row['warmup'] for w in work['workers']), 'worker_progress_placement')
        check(0 <= row['jit_completions'] <= row['jit_bodies'] <= work['completed'] and
              (row['jit_completions'] == 0 if row['threads'] == 1 else row['jit_completions'] > 0), 'returned_body_requirement')
        check('measurement' not in row and prefix+'measure.json' not in audit.files, 'correctness_not_timing')
        totals = [a+b for a, b in zip(totals, (work['completed'], row['jit_bodies'], row['jit_completions']))]
        records.append(dict(name=row['name'], operations=work['completed'], entries=row['jit_bodies'], returns=row['jit_completions']))
    check(totals == [20493056, 11496347, 11496347], 'exact_totals')
    check('timing-1/plan.json' not in audit.files and 'timing-1/result.json' not in audit.files and
          not any(n.startswith(('timing-1/outer/', 'timing-1/general/')) for n in audit.members), 'no_timing_sessions')
    check(b'strict original QEMU thread identities or placement differ' in audit.contents['timing-1-command.log'] and
          b'START timing-' not in audit.contents['timing-1-command.log'], 'strict_gate_rejection')
    before, after = (read('host-evidence/'+n+'.log') for n in ('host-before-timing-1', 'host-after-timing-1'))
    check(before['qemu'][0]['tasks'] == after['qemu'][0]['tasks'] and len(before['qemu'][0]['tasks']) == 68, 'unchanged_68_task_endpoints')
    check(health['timing_sessions'] == 0 and set(health['regressions'].values()) == {'UNRESOLVED_CAUSE'} and
          len(health['regressions']) == 7, 'unresolved_limits')
    review = dict(integrity_passed=not audit.issues, accepted=False, checks=sum(audit.counts.values()),
        check_counts=dict(audit.counts), issues=audit.issues, archive_manifest_sha256=MANIFEST,
        original_archive_manifest_sha256=ORIGINAL, archives=groups, sessions=records,
        operations=totals[0], entries=totals[1], returns=totals[2], timing_sessions=0,
        timing_status='BLOCKED_HOST_GATE', regressions=health['regressions'],
        source_sha256=helper.hashfile(Path(__file__)), scope='Inert archive/source integrity and correctness evidence; no timing acceptance.')
    (HERE/'review.json').write_text(json.dumps(review, indent=2, sort_keys=True)+'\n')
    assert not audit.issues, audit.issues[:10]
    print(json.dumps(dict(passed=True, checks=review['checks'], sessions=4, timing_sessions=0, accepted=False)))


if __name__ == '__main__':
    main()
