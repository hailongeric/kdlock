#!/usr/bin/env python3
"""Inert audit of the completed provider experiment and its retained controls."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import socket
import sys
import tarfile
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw-parent', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    output = args.report/'offline-review.json'
    assert not output.exists()
    sys.dont_write_bytecode = True

    def load_module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result

    helper_path = args.repo/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    helper = load_module('archive_reader', helper_path)
    externals, roots = {}, {}
    for name, digest in (
        ('mutex-public-20261020-r2', '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'),
        ('mutex-public-20261020-inline-inputs-1', 'e84308527775fac8a26c2eaf0e524868431b0a6eb5179a9419f5e81e8e6b7035'),
    ):
        raw = args.raw_parent/name
        assert helper.hashfile(raw/'archives.json') == digest
        manifest = json.loads((raw/'archives.json').read_text())
        assert helper.hashfile(raw/'input-inventory.json') == manifest['input_inventory_sha256']
        roots[manifest['guest_base']] = json.loads((raw/'input-inventory.json').read_text())
        externals[name] = manifest

    class JointAudit(helper.Audit):
        def retained_target(self, target):
            inventories = dict(roots, **{self.guest_base.rstrip('/'): self.inventory})
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in inventories if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                relative = target[len(root):].lstrip('/')
                if not relative:
                    return True
                if not helper.safe_relative(relative):
                    return False
                parts = relative.split('/')
                inventory = inventories[root]
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
                    return relative in inventory
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    audit = JointAudit(SimpleNamespace(repo=args.repo,
        raw=args.raw_parent/'mutex-public-20261020-inline-1', report=args.report))
    groups, links = audit.load_archives()
    audit.windows = []
    for name, manifest in externals.items():
        for group in manifest['groups']:
            audit.equal('pinned_external_archive', helper.hashfile(args.raw_parent/name/group['file']),
                        group['sha256'], [name, group['file']])
    health = audit.jread('health.json')
    records, plan, state = (audit.jread('matrix/'+name+'.json') for name in ('records', 'plan', 'status'))
    audit.expect('completed_matrix', state['state'] == 'COMPLETE' and health['idle'])
    audit.equal('session_counts', [len(records), len(plan), state['planned'], state['completed'],
                health['functionally_valid'], health['score_eligible']], [120]*6)
    audit.equal('scheduler_git_binding', audit.files['matrix/replay-scheduler.py'],
                helper.sha(audit.git_bytes('d1a976a', 'bench/mutex_api_compare/run.py')))
    audit.equal('verifier_binding', audit.files['verify-inline-run.py'], health['script_sha256'])
    audit.equal('candidate_binding', audit.files['matrix/candidate.json'],
                'd8b5b56daa3110cf3e276ca8c2198c2b05eda1bd79630210142163f57bc8f9ac')
    candidate = audit.jread('matrix/candidate.json')
    frozen = audit.jread('matrix/frozen-inputs.json')
    audit.equal('original_input_manifest', audit.files['matrix/frozen-inputs.json'],
                'df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73')
    old_raw = args.raw_parent/'mutex-public-20261020-r2'
    with tarfile.open(old_raw/'matrix.tar.gz') as stream:
        original_host = json.loads(stream.extractfile('mutex-public-20261020-r2/matrix/host-state.json').read())
    for endpoint in ('before', 'after'):
        host = audit.jread('host-'+endpoint+'.json')
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            audit.equal('host_configuration', host[key], original_host[key], [endpoint, key])
        for key in ('pid', 'args'):
            audit.equal('qemu_identity', host['qemu'][0][key], original_host['qemu'][0][key], [endpoint, key])
        pins = lambda h: sorted((t['comm'], t['affinity']) for t in h['qemu'][0]['tasks'])
        audit.equal('qemu_thread_placement', pins(host), pins(original_host), endpoint)
    retirement = []
    order = audit.jread('matrix/execution-order.json')
    for index, (row, planned) in enumerate(zip(records, plan)):
        name = row['name']
        relative = Path(row['evidence_path']).relative_to(audit.guest_base.rstrip('/')).as_posix()
        audit.equal('session_record', row, audit.jread(relative+'/session.json'), name)
        audit.equal('plan_fields', {k: row.get(k) for k in planned}, planned, name)
        audit.equal('recorded_order', [row['comparison_workload'], row['threads'], row['repeat'],
                                      row['comparison_arm']], order[index], name)
        version = ('candidate-public' if row['comparison_arm'] == 'public-kd' else
                   'baseline' if row['comparison_arm'] == 'baseline-kd' else 'current')
        key = version+'/'+row['comparison_workload']
        inputs = candidate['bundles'][key] if version == 'candidate-public' else frozen[key]
        audit.equal('arm_source_identity', row['source_identity'], inputs['source_identity'], name)
        audit.equal('arm_evidence_path', relative, 'matrix/measurements/'+key+'/'+name, name)
        audit.expect('plain_scope', not any(row.get(k) for k in ('diagnostic', 'perf_record', 'pmu')), name)
        audit.expect('complete_drained', row['execution_status'] == 'OK' and row['drained']
                     and not row.get('cleanup_error'), name)
        m = row['measurement']
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        audit.expect('business_result', m['complete'] and m['data_ok'] if synthetic else m['ok'], name)
        audit.equal('worker_cpus', [w['cpu'] for w in m['workers']], row['cpus'], name)
        audit.expect('worker_progress', all(w['completed'] > 0 and w['error'] == 0
                     and w['observed_cpu'] == w['cpu'] for w in m['workers']), name)
        audit.equal('worker_sum', sum(w['completed'] for w in m['workers']), m['completed'], name)
        audit.peak(dict(row, whole_throughput_ops_s=m['completed']*1e9/m['wall_ns']), relative)
        audit.expect('kernel_log_clean', not helper.FAULT.search(audit.contents[relative+'/kernel.log'].decode()), name)
        if row['arm'] == 'kdlock':
            audit.equal('exact_retirement', row['retired'], dict(state=2, modules=0, writers=0, frames=0), name)
            audit.equal('immutable_publication', row['published_before'], row['published_after'], name)
            retirement.append(dict(name=name, retired=row['retired']))
    audit.equal('retirement_health', retirement, health['exact_retirements'])
    report_path = args.repo/'bench/mutex_api_compare/report.py'
    audit.equal('report_source', helper.hashfile(report_path), audit.files['analysis/report.py'])
    report = load_module('report', report_path)
    summary, comparisons = report.summarize(records), report.comparisons(report.summarize(records))
    analysis = audit.jread('analysis/comparisons.json')
    audit.equal('analysis_producer', analysis['script_sha256'], audit.files['analysis/compare-inline.py'])
    audit.equal('analysis_records_binding', analysis['inputs']['mutex-public-20261020-inline-1']['sha256'],
                audit.files['matrix/records.json'])
    for point in analysis['points']:
        selected = lambda r: (r['workload'], r['threads']) == (point['workload'], point['workers'])
        current = point['runs']['mutex-public-20261020-inline-1']
        audit.equal('summary_arithmetic', current['groups'], [r for r in summary if selected(r)])
        audit.equal('comparison_arithmetic', current['outer_comparisons'],
                    [r for r in comparisons if selected(r) and r['comparator'] == 'baseline-kd'])
    answer = dict(consistent=not audit.issues, checks=sum(audit.counts.values()), issues=audit.issues,
        check_counts=dict(audit.counts), groups=groups, symlinks=len(links), sessions=120,
        reconstructed_windows=len(audit.windows), archives_manifest_sha256=helper.hashfile(audit.raw/'archives.json'),
        reviewer_host=socket.gethostname(), script_sha256=helper.hashfile(Path(__file__)),
        limits='Post-run thread mismatch remains failed. Three repetitions and observed ranges '
               'do not establish confidence intervals, causal improvement or latency acceptance.')
    output.write_text(json.dumps(answer, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: answer[k] for k in ('consistent', 'checks', 'sessions', 'archives_manifest_sha256')}))
    print('issues', Counter(issue['check'] for issue in audit.issues))


if __name__ == '__main__':
    main()
