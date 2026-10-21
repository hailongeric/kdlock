#!/usr/bin/env python3
"""Inert archive, prerequisite, phase and preserved-control integrity review."""
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
CONTROL = RAW/HERE.name
OLD = RAW/'pipecap-unlock-20261021/archives-1'
NEW = CONTROL/'collection-1/archives-1'
HASH = '71db76f5ab21797c90f0c1a43cf1aad4401e6eb286e71adc304b141b1aac9859'


def main():
    sys.dont_write_bytecode = True
    path = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('worker_inert_reader', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    roots = {}
    for folder, digest in ((RAW/'mutex-public-20261020-r2', '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'),
                           (OLD, 'c665228f06d3c5cd6ba85fb62c4e7609d4f1cc4a4d8ac58d26c439d333317c10'), (NEW, HASH)):
        assert helper.hashfile(folder/'archives.json') == digest
        manifest = json.loads((folder/'archives.json').read_text())
        assert helper.hashfile(folder/'input-inventory.json') == manifest['input_inventory_sha256']
        roots[manifest['guest_base']] = json.loads((folder/'input-inventory.json').read_text())
        if folder == OLD:
            for group in manifest['groups']:
                assert helper.hashfile(folder/group['file']) == group['sha256']

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
                parts = target[len(root):].lstrip('/').split('/')
                if parts == ['']:
                    return True
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

    a = Audit(SimpleNamespace(repo=ROOT, raw=NEW, report=HERE))
    groups, _ = a.load_archives()
    check, read = a.check, a.jread
    result, health = read('phase-2/result.json'), read('final-health.json')
    check(result['passed'] and result['final_idle'] and result['completed'] == result['planned'] == 1 and
          health['idle'] and health['matching_runtime_modules'] and result['phase_single_outer'] and
          not result['accepted'], 'single_completed_drained_diagnostic')
    check(a.files['phase-2/runner.py'] == helper.sha(a.git_bytes(result['source_commit'],
          'bench/mutex_api_compare/unlock_run.py')), 'runner_git_binding')
    for retained, group, original in [('inputs', 'inputs', 'inputs-1/inputs.json'),
                                     ('correctness', 'live', 'correctness-1/result.json'),
                                     ('unit-checks', 'checks', 'checks-1/result.json'),
                                     ('task-check', 'live', 'task-2/result.json'),
                                     ('elf-checks', 'metadata', 'elf-checks-2.json')]:
        with tarfile.open(OLD/(group+'.tar.gz')) as archive:
            data = archive.extractfile('pipecap-unlock-20261021/'+original).read()
        check(a.files['phase-2/'+retained+'.json'] == helper.sha(data), 'exact_prerequisite_binding', retained)
    row, = result['records']
    prefix = 'phase-2/outer/'+row['name']+'/'
    measurement = row['measurement']
    check(read(prefix+'session.json') == row and all(measurement[k] == v for k, v in read(prefix+'measure.json').items()),
          'raw_session_measurement_binding')
    check(row['execution_status'] == 'OK' and row['drained'] and row['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'exact_retirement')
    check(measurement['ok'] and len(measurement['workers']) == 5 and
          sum(w['completed'] for w in measurement['workers']) == measurement['completed'] == row['redirected_calls'] and
          all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] > 0 for w in measurement['workers']), 'business_worker_progress')
    check(row['published_before'] == row['published_after'] and row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32, 'stable_images_placement')
    check(row['duration_ms'] == 2000 and row['warmup'] == 48000 and row['warmup_ms'] == 1000 and
          row['peak_settle_ms'] == row['peak_window_ms'] == 300 and row['sample_ms'] == 10 and
          row['collector_cpu'] == 63 and row['cpus'] == [0, 1, 2, 3, 4] and row['entries'] == 16, 'original_settings')
    check(read(prefix+'load-kd.log.command.json')['argv'][2:] == [
        'bench_quiet=1', 'bench_complete_probe=1', 'jit_timing=0', 'hotlock_stats=1',
        'target_process=sc_worker', 'spin_entry_ratio_limit=2', 'spin_prefetch=2'], 'original_provider_parameters')
    check(measurement['completed'] == health['operations'] == 24489984 and
          row['jit_bodies'] == row['jit_completions'] == health['returns'] == 167972, 'operations_return_counts')
    check(read('phase-2/environment-comparison.json')['configuration_matches'] and
          len(read('phase-2/host-before.json')['qemu'][0]['tasks']) == 67, 'strict_preflight_passed')
    copied = 0
    for name, digest in a.files.items():
        if name.startswith('host-controls/'):
            relative = name.removeprefix('host-controls/')
            local = CONTROL/relative if relative != 'read-sync-manifests.stdout' else CONTROL/'collection-1'/relative
            check(local.is_file() and helper.hashfile(local) == digest, 'copied_control_exact_bytes', relative)
            copied += 1
    for name in ('basic-1', 'sync-2', 'phase-1'):
        state = read('host-controls/'+name+'/supervisor.json')
        check(not state['complete'] and not state['commands'] and state['initial_task_count'] > 67 and 'error' in state,
              'refusal_preserved_no_guest_command', name)
    basic = (CONTROL/'basic-2/basic-build-test.stdout').read_text()
    check('Unit tests: 2 passed, 0 failed' in basic and '"unit_sources_unchanged": true' in basic, 'basic_build_test_passed')
    state = read('host-controls/phase-2/supervisor.json')
    phases = state['phases']
    check([r['guest_event']['remote']['sequence'] for r in phases] == list(range(1, len(phases)+1)), 'phase_sequence_complete')
    stack = []
    for entry in phases:
        event = entry['guest_event']['remote']
        check(entry['guest_event']['received']['mono_ns'] <= entry['host_ack']['sent']['mono_ns'] <=
              entry['host_ack']['ack']['received']['mono_ns'] <= entry['guest_ack_sent']['mono_ns'], 'causal_observer_coordination')
        if event['edge'] == 'begin':
            stack.append(event['label'])
        else:
            check(bool(stack) and stack.pop() == event['label'], 'phase_nested_pair')
    check(not stack and state['complete'], 'phase_stream_completed')
    collection = CONTROL/'collection-1'
    review = dict(integrity_passed=not a.issues, accepted=False, checks=sum(a.counts.values()), issues=a.issues,
        check_counts=dict(a.counts), archive_manifest_sha256=HASH, archives=groups, copied_control_files=copied,
        phase_events=len(phases), operations=measurement['completed'], entries=row['jit_bodies'], returns=row['jit_completions'],
        execution_class='RETURNED_JIT', returned_fraction=row['jit_completions']/measurement['completed'],
        whole_ops_s=row['whole_throughput_ops_s'], peak_ops_s=row['peak_throughput_ops_s'],
        collection_observation_sha256={p.name: helper.hashfile(p) for p in collection.iterdir() if p.is_file()},
        source_sha256=helper.hashfile(Path(__file__)), regressions=health['regressions'],
        scope='Focused intrusive diagnostics. Failed runtime task count; no accepted comparison or isolated unlock cost.')
    (HERE/'review.json').write_text(json.dumps(review, indent=2, sort_keys=True)+'\n')
    assert not a.issues, a.issues[:10]
    print(json.dumps(dict(passed=True, checks=review['checks'], operations=review['operations'], returns=review['returns'], accepted=False)))


if __name__ == '__main__':
    main()
