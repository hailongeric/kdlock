#!/usr/bin/env python3
"""Fresh c01 controls plus the bounded-NUMA origin candidate.

Use the normal runner's builds, oracles, alternating rounds and drain. The
baseline is a separately archived checkout with its matching daemon/translator;
only its provider/translation inputs differ. No historical scores are imported.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys

import run as runner
from session import BackendSession


def frozen_inputs(root):
    return {str(p.relative_to(root)): runner.digest(p)
            for directory in ('include', 'kernel_module', 'disassem', 'daemon')
            for p in (root / directory).rglob('*')
            if p.is_file() and not any(part.startswith('.') or part == '__pycache__'
                                      for part in p.relative_to(root).parts)
            and (p.suffix in ('.c', '.h', '.inc', '.py', '.S', '.def') or p.name == 'Makefile')
            and not p.name.endswith('.mod.c')}


def gates(out):
    """Keep median whole-run and best warmed peak, plus its paired whole rate."""
    rows = [json.loads(p.read_text()) for p in out.glob('*/session.json')]
    groups = {}
    for row in rows:
        if runner.valid(row) and not row.get('diagnostic'):
            groups.setdefault((row['threads'], row['comparison_arm']), []).append(row)
    scores = {}
    for key, samples in groups.items():
        best = max(samples, key=lambda r: r['measurement']['peak']['throughput_ops_s'])
        m = best['measurement']
        scores[key] = dict(threads=key[0], arm=key[1], samples=len(samples),
            rounds=sorted({r['repeat'] for r in samples}),
            best_session=best['name'], peak=m['peak']['throughput_ops_s'],
            whole=m['completed'] * 1e9 / m['wall_ns'],
            median_whole=statistics.median(r['measurement']['completed'] * 1e9 /
                                           r['measurement']['wall_ns'] for r in samples),
            peak_range=[min(r['measurement']['peak']['throughput_ops_s'] for r in samples),
                        statistics.median(r['measurement']['peak']['throughput_ops_s'] for r in samples),
                        max(r['measurement']['peak']['throughput_ops_s'] for r in samples)])
    comparisons = []
    for (threads, arm), row in scores.items():
        if arm != 'numa':
            continue
        baseline = scores.get((threads, 'current-kd'))
        native = scores.get((threads, 'native'))
        if not baseline or not native:
            continue
        ratios = {metric: row[metric] / baseline[metric] for metric in ('peak', 'whole', 'median_whole')}
        complete = all(s['samples'] == 3 and s['rounds'] == [0, 1, 2]
                       for s in (row, baseline, native))
        native_ratios = {metric: row[metric] / native[metric] for metric in ratios}
        comparisons.append(dict(threads=threads, arm=arm, over_current_kd=ratios,
            regression_pass=min(ratios.values()) >= .97 and complete,
            over_native=native_ratios, native_target_applicable=threads <= 8,
            native_target_pass=complete and min(native_ratios.values()) >= .97 if threads <= 8 else None))
    grid = set(range(1, 9)) | set(range(12, 65, 4))
    arms = {arm for _, arm in scores}
    coverage = arms == {'native', 'tclock', 'current-kd', 'numa'}
    coverage = coverage and set(scores) == {(count, arm) for count in grid for arm in arms}
    coverage = coverage and all(s['samples'] == 3 and s['rounds'] == [0, 1, 2] for s in scores.values())
    runner.write_json(out / 'origin-gates.json', dict(scores=list(scores.values()), comparisons=comparisons,
        full_grid_complete=coverage,
        regression_pass=coverage and all(row['regression_pass'] for row in comparisons)))


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('--baseline-root', type=Path, required=True)
    p.add_argument('--baseline-commit', required=True)
    local, remaining = p.parse_known_args()
    baseline = local.baseline_root.resolve()
    provider = baseline / 'bench/spin_cacheline/.build/provider/kernel_module/kdlock_km.ko'
    daemon = baseline / 'daemon/daemon'
    identity = frozen_inputs(baseline)
    runner.require(identity and len(local.baseline_commit) == 40, 'archived baseline identity required')
    base_plan, base_report = runner.make_plan, runner.report

    def plan(args):
        runner.require(args.mutex_implementation == 'owned-v1' and args.owned_mutex_cabi and
                       args.owned_mutex_reuse_spins == 32 and args.duration_ms == 2000 and
                       args.repeats == 3 and args.backends == ['native', 'tclock', 'kdlock'] and
                       not (args.functional or args.profile_lock or args.pmu or args.perf_record),
                       'origin matrix requires scored ABI4/reuse32 c01, three rounds and all controls')
        result = []
        for spec in base_plan(args):
            if spec['arm'] != 'kdlock':
                result.append(dict(spec, comparison_arm=spec['arm']))
                continue
            variants = ['current-kd', 'numa']
            if spec['repeat'] % 2:
                variants.reverse()
            for variant in variants:
                row = dict(spec, name=spec['name'] + '-' + variant, comparison_arm=variant)
                if variant == 'current-kd':
                    row.pop('owned_mutex_origin_spin'); row.pop('owned_mutex_numa')
                    row['baseline_commit'] = local.baseline_commit
                else:
                    row.update(owned_mutex_origin_spin=True, owned_mutex_numa=True)
                result.append(row)
        return result

    class ComparisonSession(BackendSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            runner.require(frozen_inputs(baseline) == identity, 'baseline source changed')
            runner.require({str(p): runner.digest(p) for p in (provider, daemon)} == binary_hashes,
                           'baseline binaries changed')
            if self.record['comparison_arm'] == 'current-kd':
                self.translation_source = baseline
                self.daemon_binary = daemon
                self.record['baseline_binary_sha256'] = binary_hashes
                self.save()

        def run(self, args, log, **kwargs):
            if self.record['comparison_arm'] == 'current-kd' and args[:2] == ['insmod', runner.PROVIDER]:
                args = ['insmod', provider, *args[2:]]
            return super().run(args, log, **kwargs)

    def report(out):
        base_report(out)
        runner.write_json(out / 'baseline-source-sha256.json', identity)
        gates(out)

    runner.make_plan = plan
    runner.BackendSession = ComparisonSession
    runner.report = report
    sys.argv = [sys.argv[0], *remaining]
    # Baseline preparation belongs to this archived tree, never the source
    # mirror. Reuse only identically hashed artifacts across confirmation blocks.
    if '--dry-run' not in remaining:
        runner.idle()
        runner.require(Path('/sys/devices/system/cpu/online').read_text().strip() == '0-63',
                       'origin comparison requires exactly 64 online vCPUs')
        runner.require(provider.is_file() and daemon.is_file(), 'build archived baseline first')
        binary_hashes = {str(path): runner.digest(path) for path in (provider, daemon)}
    return runner.main('mutex')


if __name__ == '__main__':
    raise SystemExit(main())
