#!/usr/bin/env python3
"""Inert archive/source validation and descriptive paired arithmetic only."""
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
from statistics import mean, median, stdev, variance
import sys
import tarfile
from types import SimpleNamespace

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1]/'raw/bench'
OLD = RAW/'pipecap-unlock-20261021/archives-1'
NEW = RAW/HERE.name/'archives-1'
HASH = '08fc223e20341d1bae01aff178bb36aca5a415fe7d262a876f8f216126d0a788'


def main():
    sys.dont_write_bytecode = True
    path = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('maintained_inert_reader', path)
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

    def old_bytes(group, name):
        with tarfile.open(OLD/(group+'.tar.gz')) as t:
            return t.extractfile('pipecap-unlock-20261021/'+name).read()

    result, health = read('timing-1/result.json'), read('final-health.json')
    check(result['passed'] and result['final_idle'] and result['completed'] == result['planned'] == 6 and
          health['idle'] and health['matching_runtime_modules'], 'completed_drained')
    check(a.files['timing-1/runner.py'] == helper.sha(a.git_bytes(result['source_commit'], 'bench/mutex_api_compare/unlock_run.py')), 'runner_git_binding')
    for retained, group, original in [('inputs', 'inputs', 'inputs-1/inputs.json'),
                                     ('correctness', 'live', 'correctness-1/result.json'),
                                     ('unit-checks', 'checks', 'checks-1/result.json'),
                                     ('task-check', 'live', 'task-2/result.json'),
                                     ('elf-checks', 'metadata', 'elf-checks-2.json')]:
        check(a.files['timing-1/'+retained+'.json'] == helper.sha(old_bytes(group, original)), 'exact_prerequisite_binding', retained)
    check(result['inputs_sha256'] == 'daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae', 'unchanged_derivative')
    rows, rates = [], {'outer': [], 'general': []}
    order = [(0, 'outer'), (0, 'general'), (1, 'general'), (1, 'outer'), (2, 'outer'), (2, 'general')]
    for record, (repeat, arm) in zip(result['records'], order):
        name = f'timing-pipecap-t05-r{repeat}-{arm}'
        prefix = 'timing-1/'+arm+'/'+name+'/'
        check(record['name'] == name and read(prefix+'session.json') == record, 'serial_order_session_binding')
        m = record['measurement']
        check(all(m[k] == v for k, v in read(prefix+'measure.json').items()), 'raw_measurement_binding')
        check(m['ok'] and record['drained'] and record['execution_status'] == 'OK' and
              record['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'business_exact_retirement')
        check(record['actual_lock_cacheline_offset'] == record['lock_addr'] % 64 == 32, 'actual_placement')
        check(len(m['workers']) == 5 and sum(w['completed'] for w in m['workers']) == m['completed'] and
              all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] > 0 for w in m['workers']), 'worker_progress')
        check(record['redirected_calls'] == m['completed'] and record['published_before'] == record['published_after'], 'protected_calls_stable_images')
        check(record['duration_ms'] == 2000 and record['warmup'] == 48000 and record['warmup_ms'] == 1000 and
              record['peak_settle_ms'] == record['peak_window_ms'] == 300 and record['sample_ms'] == 10 and
              record['collector_cpu'] == 63 and record['cpus'] == [0, 1, 2, 3, 4] and record['entries'] == 16, 'original_settings')
        check(read(prefix+'load-kd.log.command.json')['argv'][2:] == [
            'bench_quiet=1', 'bench_complete_probe=1', 'jit_timing=0', 'hotlock_stats=1',
            'target_process=sc_worker', 'spin_entry_ratio_limit=2', 'spin_prefetch=2'], 'original_provider_parameters')
        rate = m['completed']*1e9/m['wall_ns']
        check(rate == record['whole_throughput_ops_s'], 'whole_rate_arithmetic')
        entries, returned = record['jit_bodies'], record['jit_completions']
        check(0 <= returned <= entries <= m['completed'], 'jit_count_order')
        execution = 'RETURNED_JIT' if returned else 'PARTIAL_JIT' if entries else 'NO_JIT'
        rows.append(dict(name=name, repeat=repeat, arm=arm, operations=m['completed'], wall_ns=m['wall_ns'],
            whole_ops_s=rate, peak_ops_s=record['peak_throughput_ops_s'], entries=entries, returns=returned,
            entry_fraction=entries/m['completed'], returned_fraction=returned/m['completed'], execution_class=execution))
        rates[arm].append(rate)
    pairs = []
    for repeat in range(3):
        pair = {r['arm']: r for r in rows if r['repeat'] == repeat}
        ratio = pair['general']['whole_ops_s']/pair['outer']['whole_ops_s']
        pairs.append(dict(repeat=repeat, ratio=ratio, percent_change=(ratio-1)*100,
            matching_class=pair['general']['execution_class'] == pair['outer']['execution_class'], score_eligible=False))
    stats = {arm: dict(n=len(v), minimum_ops_s=min(v), median_ops_s=median(v), maximum_ops_s=max(v),
             sample_variance=variance(v), sample_sd_ops_s=stdev(v), sample_cv_percent=100*stdev(v)/mean(v),
             spread_percent=100*(max(v)-min(v))/median(v)) for arm, v in rates.items()}
    before, after = read('timing-1/host-before.json'), read('host-evidence/host-after-timing-1.json')
    old_tasks, new_tasks = ({r['tid']: r for r in h['qemu'][0]['tasks']} for h in (before, after))
    check(len(old_tasks) == 67 and len(new_tasks) == 120 and all(new_tasks.get(i) == t for i, t in old_tasks.items()), 'endpoint_67_to_120')
    check(read('timing-1/environment-comparison.json')['configuration_matches'] and
          health['host_preflight_passed'] and not health['host_endpoint_passed'], 'strict_environment_outcome')
    snapshots = [read('host-evidence/endpoint-lifetime-'+str(i)+'.json') for i in range(2)]
    workers = []
    for snapshot in snapshots:
        observed = []
        for task in snapshot['after']['tasks']:
            if task.get('comm') != 'worker':
                continue
            fields = task['stat_after'].rsplit(')', 1)[1].split()
            io = dict(line.split(': ', 1) for line in task['files']['io']['text'].splitlines())
            observed.append(dict(tid=task['tid'], start_ticks=int(fields[19]), affinity=task['affinity'],
                runtime_ns=int(task['files']['schedstat']['text'].split()[0]), read_bytes=int(io['read_bytes']),
                write_bytes=int(io['write_bytes']), in_immediate_endpoint=task['tid'] in new_tasks))
        workers.append(dict(captured_utc=snapshot['captured_utc'], thread_count=len(snapshot['after']['tasks']), workers=observed))
    prior_ids = {(w['tid'], w['start_ticks']) for w in workers[0]['workers']}
    later_ids = {(w['tid'], w['start_ticks']) for w in workers[1]['workers']}
    check(len(prior_ids) == 9 and len(later_ids) == 1 and not prior_ids & later_ids, 'departed_workers_and_new_identity')
    check(sum(r['operations'] for r in rows) == health['completed_operations'] == 117108224 and
          sum(r['returns'] for r in rows) == health['returns'] == 2608148, 'total_operations_returns')
    review = dict(integrity_passed=not a.issues, accepted=False, checks=sum(a.counts.values()), issues=a.issues,
        check_counts=dict(a.counts), archive_manifest_sha256=HASH, archives=groups, sessions=rows, pairs=pairs,
        arm_statistics=stats, ratio_of_arm_medians=median(rates['general'])/median(rates['outer']),
        median_paired_ratio=median(p['ratio'] for p in pairs), host_worker_observations=workers,
        nominal_endpoint_delay_seconds=datetime.fromisoformat(after['captured_utc']).timestamp()-result['finished_ns']/1e9,
        delay_limit='Cross-host clock offset was not calibrated; this is not a proven elapsed-time bound.',
        source_sha256=helper.hashfile(Path(__file__)), regressions=health['regressions'],
        scope='All rates descriptive only: failed endpoint, changing fractions, one class-mismatched pair; no acceptance or isolated provider-overhead conclusion.')
    (HERE/'review.json').write_text(json.dumps(review, indent=2, sort_keys=True)+'\n')
    assert not a.issues, a.issues[:10]
    print(json.dumps(dict(passed=True, checks=review['checks'], sessions=6, accepted=False,
                         median_paired_ratio=review['median_paired_ratio'], arm_statistics=stats)))


if __name__ == '__main__':
    main()
