#!/usr/bin/env python3
"""Audit c01 admission trials without pooling candidates or confirmation blocks.

An early screening rung may reject a candidate on one required worker count.
Only a complete primary and regression grid can pass. Two independent complete
confirmation blocks are required before recommending a new default.
"""
import argparse
import json
from pathlib import Path
import statistics

import run
from bench_runtime import digest, require, validate_measurement
from summarize import valid, write_json

PRIMARY = (1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28)
REGRESSION = (32, 36, 48, 60)
GRID = PRIMARY + REGRESSION


def load_run(folder):
    """Verify frozen source/binaries, raw data, full-cohort peak and sample drain."""
    folder = Path(folder)
    environment = json.loads((folder/'environment.json').read_text())
    require(environment['kernel_identity']['ok'] and
            environment['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            environment['topology']['online_cpus'] == list(range(64)) and
            environment['collector_topology']['role_cpus'] == [63] and
            {'nokaslr', 'nopvspin'} <= set(environment['cmdline'].split()) and
            '(voluntary)' in environment['preemption'], 'kernel/boot/topology differs')
    for relative, expected in json.loads((folder/'source-sha256.json').read_text()).items():
        require(digest(folder/'source'/relative) == expected, f'changed frozen source: {relative}')
    for original, expected in json.loads((folder/'binary-sha256.json').read_text()).items():
        path = (folder/'variants'/original.split('/variants/', 1)[1]
                if '/variants/' in original else folder/'binaries'/Path(original).name)
        require(digest(path) == expected, f'changed frozen binary: {path}')
    result = []
    plan = json.loads((folder/'plan.json').read_text())
    require(len({s['name'] for s in plan}) == len(plan), 'duplicate planned samples')
    for spec in plan:
        path = folder/spec['name']/'session.json'
        require(path.exists(), f'missing sample: {path}')
        record = json.loads(path.read_text())
        require(all(record.get(k) == v for k, v in spec.items()), 'sample policy differs from plan')
        require(record['lock_kind'] == 'mutex' and record['cachelines'] == 1 and
                record['workload'] == 'cacheline' and record['cpus'] == list(range(record['threads'])) and
                record['collector_cpu'] == 63 and record['duration_ms'] == 2000 and
                record['warmup_iterations_per_worker'] == 48000 and
                record['peak_window_ms'] == record['peak_settle_ms'] == 300 and
                not record.get('diagnostic', False) and not record.get('pmu', False) and
                not record.get('profile_lock', False) and not record.get('functional', False),
                'sample is outside the uninstrumented c01 study contract')
        require(valid(record), f'invalid/undrained sample: {path}')
        require(record['cpu_nodes'] == [int(cpu >= 32) for cpu in record['cpus']],
                'NUMA placement differs')
        if record['arm'] == 'kdlock':
            require(record['mutex_wait_mode'] == 'blocking' and record['mutex_spin_limit'] == 4096 and
                    record['numa_policy'] == 'on' and record['delegation_batch_limit'] == 1024 and
                    record['kd_provider_ubsan'] == 'off', 'KD build/wait policy differs')
            require(record['published_before'] == record['published_after'] and
                    record['retired'] == dict(state=2, modules=0, frames=0, writers=0),
                    'publication changed or source retirement incomplete')
            publication = record['published_before']
            entry = publication['entry']
            images = path.parent/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
            for name, expected in publication['images'].items():
                require(digest(images/name) == expected, 'changed JIT image/assembly')
            require(record['jit_after'] - record['jit_before'] == record['jit_bodies'] and
                    0 <= record['jit_bodies'] <= record['measurement']['completed'],
                    'invalid returned-body count')
        raw = json.loads((path.parent/'measure.json').read_text())
        peak = validate_measurement(raw, record, record['iterations'])
        require(peak == record['measurement']['peak'], 'saved peak does not match raw progress')
        require(dict(raw, peak=peak) == record['measurement'], 'saved measurement differs from raw data')
        result.append(record)
    # This study freezes 64 post-work rounds; a historical four-round input is
    # not interchangeable even if its rate and session settings look plausible.
    post = (folder/'source/workload_modules/spin_cacheline/post_work.h').read_text()
    require('#define SC_POST_WORK_ROUNDS 64' in post, 'post-work default differs')
    return result


def metrics(rows):
    require(len(rows) == 3 and {r['repeat'] for r in rows} == {0, 1, 2},
            'each arm/cohort requires all three rounds')
    whole = [r['measurement']['completed'] * 1e9 / r['measurement']['wall_ns'] for r in rows]
    peak = [r['measurement']['peak']['throughput_ops_s'] for r in rows]
    shares = [w['completed']/r['measurement']['completed']
              for r in rows for w in r['measurement']['workers']]
    return dict(median_whole=statistics.median(whole), best_peak=max(peak),
                whole_rates=whole, peak_rates=peak,
                whole_spread_pct=100*(max(whole)-min(whole))/statistics.median(whole),
                peak_spread_pct=100*(max(peak)-min(peak))/statistics.median(peak),
                worker_share_min=min(shares), worker_share_max=max(shares),
                worker_cpu_ns_per_op=[r['measurement']['worker_cpu_ns']/r['measurement']['completed']
                                      for r in rows],
                jit_bodies=[r.get('jit_bodies', 0) for r in rows],
                jit_shares=[r.get('jit_share', 0) for r in rows],
                execution_classes=[r.get('execution_class', r.get('jit_status')) for r in rows])


def evaluate(baseline, candidate):
    limits = {r.get('mutex_entry_ratio_limit') for r in candidate if r['arm'] == 'kdlock'}
    require(len(limits) == 1 and next(iter(limits)) in run.MUTEX_ENTRY_RATIO_LIMITS,
            'one threshold per candidate')
    require(all(r.get('mutex_routing') == 'adaptive' and
                r.get('mutex_acceptance') == 'adaptive-performance'
                for r in candidate if r['arm'] == 'kdlock'), 'wrong candidate acceptance policy')
    counts = sorted({r['threads'] for r in candidate})
    require(set(counts) <= set(GRID), 'unexpected worker count')
    checks = []
    for t in counts:
        kd = metrics([r for r in candidate if r['arm'] == 'kdlock' and r['threads'] == t])
        # Primary Native controls are freshly paired with this exact candidate.
        reference = (metrics([r for r in candidate if r['arm'] == 'native' and r['threads'] == t])
                     if t in PRIMARY else
                     metrics([r for r in baseline if r['arm'] == 'kdlock' and r['threads'] == t]))
        ratios = {k: kd[k]/reference[k] for k in ('median_whole', 'best_peak')}
        jit_ok = t in PRIMARY or all(n > 0 for n in kd['jit_bodies'])
        checks.append(dict(threads=t, reference='native' if t in PRIMARY else 'baseline_kd',
                           ratios=ratios, jit_ok=jit_ok, candidate=kd, control=reference,
                           passed=min(ratios.values()) >= .97 and jit_ok))
    missing = sorted(set(GRID)-set(counts))
    verdict = ('REJECTED' if any(not c['passed'] for c in checks) else
               'INCOMPLETE' if missing else 'PASS')
    return dict(threshold=next(iter(limits)), verdict=verdict, missing=missing, checks=checks)


def sample_identities(records):
    return {(r['arm'], r['threads'], r['measurement']['started_ns'],
             r['measurement']['finished_ns']) for r in records}


def require_fresh(records, seen):
    identities = sample_identities(records)
    require(len(identities) == len(records) and not seen.intersection(identities),
            'reused samples in confirmation block')
    seen.update(identities)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidates', type=Path, nargs='+', required=True)
    parser.add_argument('--confirmations', type=Path, nargs=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = load_run(args.baseline)
    require({r['threads'] for r in baseline} == set(GRID), 'incomplete baseline grid')
    for t in GRID:
        for arm in ('native', 'kdlock'):
            metrics([r for r in baseline if r['threads'] == t and r['arm'] == arm])
    candidate_records = {p: load_run(p) for p in args.candidates}
    trials = [dict(path=str(p), **evaluate(baseline, rows))
              for p, rows in candidate_records.items()]
    passing = sorted(t['threshold'] for t in trials if t['verdict'] == 'PASS')
    confirmation = []
    selected = None
    if args.confirmations:
        require(passing, 'cannot confirm without a complete passing screen')
        require(args.confirmations[0].resolve() != args.confirmations[1].resolve(), 'reuse of confirmation block')
        chosen = next(Path(t['path']) for t in trials
                      if t['threshold'] == min(passing) and t['verdict'] == 'PASS')
        frozen = json.loads((chosen/'source-sha256.json').read_text())
        seen = sample_identities(baseline)
        for records in candidate_records.values():
            seen.update(sample_identities(records))
        for p in args.confirmations:
            records = load_run(p)
            require(json.loads((p/'source-sha256.json').read_text()) == frozen,
                    'confirmation source differs from selected screen')
            require_fresh(records, seen)
            confirmation.append(dict(path=str(p), **evaluate(baseline, records)))
        if all(c['verdict'] == 'PASS' and c['threshold'] == min(passing) for c in confirmation):
            selected = min(passing)
    write_json(args.output, dict(selected_default=selected, retained_default=256 if selected is None else None,
        acceptance='97% separately for median whole-run and best valid warmed peak in each block',
        baseline=str(args.baseline), candidates=trials, confirmations=confirmation))
    print(json.dumps(dict(selected_default=selected,
                         verdicts=[(r['threshold'], r['verdict']) for r in trials])))


if __name__ == '__main__':
    main()
