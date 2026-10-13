#!/usr/bin/env python3
"""Audit c01 admission trials without pooling candidates or confirmation blocks.

An early screening rung may reject a candidate on one required worker count.
Only a complete primary and regression grid can pass. Two independent complete
confirmation blocks are required before recommending a new default.
"""
import argparse
import json
from pathlib import Path
import re
import statistics

import run
from bench_runtime import FAULT, digest, require, validate_measurement
from session import check_jit_evidence, check_kd_parameters
from summarize import valid, write_json

PRIMARY = (1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28)
REGRESSION = (32, 36, 48, 60)
GRID = PRIMARY + REGRESSION

OWNED_IDENTITY = dict(registry_lock_kind=3, entry_abi=2, caller_abi='clobber',
    caller_shell='owned_mutex_outer_cookie', cookie_storage='owned_acquisition_local',
    mutex_wait_counter_scope='owned_delegate_waits')


def require_owned_identity(record):
    require(all(record.get(key) == value for key, value in OWNED_IDENTITY.items()),
            'owned mutex family/caller/queue identity differs')
    require(record.get('owned_queue_policy') ==
            ('bounded_fifo_refill' if record.get('owned_mutex_refill', False) else 'finite_fifo'),
            'owned FIFO policy differs from refill control')
    policy = record.get('owned_preflight_policy')
    budget = record.get('owned_mutex_preflight_spins')
    enabled = record.get('owned_mutex_preflight')
    require('owned_mutex_preflight' not in record or (type(enabled) is bool and
            policy == ('c_abi_v1' if enabled else 'capture_first')),
            'owned preflight compile-time identity differs')
    require((policy is None and budget is None) or
            (policy == 'capture_first' and enabled is False and type(budget) is int and budget == 0) or
            (policy == 'c_abi_v1' and type(budget) is int and
             budget in run.OWNED_MUTEX_PREFLIGHT_SPINS),
            'owned preflight policy identity differs')
    queued = record.get('owned_mutex_preflight_queue')
    require((queued is None or type(queued) is bool) and
            (not queued or (policy == 'c_abi_v1' and budget > 0)),
            'owned queued preflight policy identity differs')
    require(record.get('scenario', 'plain') == 'plain' and
            not record.get('owned_mutex_force_full', False),
            'owned performance sample contains a functional control')


def require_owned_evidence(record, folder):
    """Recheck existing live receipts; legacy archives predate owned metadata."""
    if record.get('mutex_implementation', 'legacy') != 'owned-v1':
        return
    require_owned_identity(record)
    layout = record.get('layout', {})
    require(layout.get('lock_bytes') == 32 and layout.get('line_bytes') == 64 and
            layout.get('lock_addr', -1) % 64 == layout.get('data_addr', -1) % 64 == 0,
            'owned mutex layout differs')
    entry = record['published_before']['entry']
    require(entry.get('lock_kind') == 3 and entry.get('entry_abi') == 2 and
            entry.get('pid') == entry.get('status') == 0 and entry.get('code', 0) > 0,
            'owned publication has the wrong family/ABI or is not NORMAL')
    check_kd_parameters(record['parameters'], record, layout['lock_addr'])
    classified = dict(record)
    check_jit_evidence(classified)
    require(all(record.get(key) == classified[key] for key in
                ('execution_class', 'jit_acceptance')),
            'owned execution classification differs from returned bodies')
    log = (folder/'kernel.log').read_text()
    require(not FAULT.search(log), 'owned sample contains a kernel fault')
    matches = re.findall(
        r'kd_owned_mutex: bodies=(\d+) batches=(\d+) refusals=(\d+) early_releases=(\d+)', log)
    require(len(matches) == 1, 'missing or duplicate owned provider drain receipt')
    observed = dict(zip(('bodies', 'batches', 'refusals', 'early_releases'), map(int, matches[0])))
    require(record.get('owned_observations') == observed,
            'owned drain observations differ from the kernel receipt')
    require(observed['bodies'] >= record['jit_bodies'] and observed['early_releases'] == 0,
            'owned plain body observations disagree with measured execution')
    require(json.loads((folder/'drain.counts.json').read_text())['active'] == 0,
            'owned workers did not drain')


def load_run(folder, post_work_rounds=64):
    """Verify frozen source/binaries, raw data, full-cohort peak and sample drain."""
    require(type(post_work_rounds) is int and 1 <= post_work_rounds <= 256,
            'requested post-work rounds must be 1..256')
    folder = Path(folder)
    environment = json.loads((folder/'environment.json').read_text())
    require(environment['kernel_identity']['ok'] and
            environment['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            environment['topology']['online_cpus'] == list(range(64)) and
            environment['collector_topology']['role_cpus'] == [63] and
            {'nokaslr', 'nopvspin'} <= set(environment['cmdline'].split()) and
            '(voluntary)' in environment['preemption'], 'kernel/boot/topology differs')
    frozen = json.loads((folder/'source-sha256.json').read_text())
    require(run.POST_WORK_SOURCE in frozen, 'frozen post-work source is not hashed')
    for relative, expected in frozen.items():
        require(digest(folder/'source'/relative) == expected, f'changed frozen source: {relative}')
    require(run.source_post_work_rounds(folder/'source') == post_work_rounds,
            'frozen post-work rounds differ from requested study')
    for original, expected in json.loads((folder/'binary-sha256.json').read_text()).items():
        path = (folder/'variants'/original.split('/variants/', 1)[1]
                if '/variants/' in original else folder/'binaries'/Path(original).name)
        require(digest(path) == expected, f'changed frozen binary: {path}')
    result = []
    plan = json.loads((folder/'plan.json').read_text())
    require(len({s['name'] for s in plan}) == len(plan), 'duplicate planned samples')
    for spec in plan:
        require_post_work_metadata(spec, post_work_rounds)
        path = folder/spec['name']/'session.json'
        require(path.exists(), f'missing sample: {path}')
        record = json.loads(path.read_text())
        require_post_work_metadata(record, post_work_rounds)
        require(all(record.get(k) == v for k, v in spec.items()), 'sample policy differs from plan')
        # Historical 8/64-round records predate this metadata; the hashed header
        # establishes their identity before downstream comparisons see it.
        record.setdefault('post_work_rounds', post_work_rounds)
        require(record['lock_kind'] == 'mutex' and record['cachelines'] == 1 and
                record['workload'] == 'cacheline' and record['cpus'] == list(range(record['threads'])) and
                record['collector_cpu'] == 63 and record['duration_ms'] == 2000 and
                record['warmup_iterations_per_worker'] == 48000 and
                record['peak_window_ms'] == record['peak_settle_ms'] == 300 and
                not record.get('diagnostic', False) and not record.get('pmu', False) and
                not record.get('profile_lock', False) and not record.get('perf_record', False) and
                not record.get('functional', False),
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
            require_owned_evidence(record, path.parent)
        raw = json.loads((path.parent/'measure.json').read_text())
        peak = validate_measurement(raw, record, record['iterations'])
        require(peak == record['measurement']['peak'], 'saved peak does not match raw progress')
        require(dict(raw, peak=peak) == record['measurement'], 'saved measurement differs from raw data')
        result.append(record)
    return result


def require_post_work_metadata(record, rounds):
    value = record.get('post_work_rounds')
    require(('post_work_rounds' not in record and rounds in (8, 64)) or
            (type(value) is int and value == rounds),
            'post-work metadata differs from frozen source')


def study_post_work_rounds(rows):
    values = [r.get('post_work_rounds', 64) for r in rows]
    require(values and all(type(n) is int and 1 <= n <= 256 for n in values),
            'invalid post-work round metadata')
    rounds = set(values)
    require(len(rounds) == 1,
            'cannot pool different post-work rounds in one study')
    return next(iter(rounds))


def metrics(rows):
    require(len(rows) == 3 and {r['repeat'] for r in rows} == {0, 1, 2},
            'each arm/cohort requires all three rounds')
    whole = [r['measurement']['completed'] * 1e9 / r['measurement']['wall_ns'] for r in rows]
    peak = [r['measurement']['peak']['throughput_ops_s'] for r in rows]
    shares = [w['completed']/r['measurement']['completed']
              for r in rows for w in r['measurement']['workers']]
    return dict(post_work_rounds=study_post_work_rounds(rows),
                median_whole=statistics.median(whole), best_peak=max(peak),
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
    post_work_rounds = study_post_work_rounds([*baseline, *candidate])
    implementations = {r.get('mutex_implementation', 'legacy') for r in candidate if r['arm'] == 'kdlock'}
    require(len(implementations) == 1 and implementations <= {'legacy', 'owned-v1'},
            'one mutex implementation per candidate')
    implementation = next(iter(implementations))
    policies = {r.get('owned_queue_policy', 'not_applicable') for r in candidate if r['arm'] == 'kdlock'}
    require(len(policies) == 1, 'one queue policy per candidate')
    if implementation == 'owned-v1':
        for record in candidate:
            if record['arm'] == 'kdlock':
                require_owned_identity(record)
    preflights = {(r.get('owned_preflight_policy'), r.get('owned_mutex_preflight_spins'),
                   r.get('owned_mutex_preflight_queue'), r.get('owned_mutex_preflight'))
                  for r in candidate if r['arm'] == 'kdlock'}
    require(len(preflights) == 1, 'one preflight policy and budget per candidate')
    preflight_policy, preflight_spins, preflight_queue, preflight_enabled = next(iter(preflights))
    threshold_field = ('owned_mutex_entry_ratio_limit' if implementation == 'owned-v1' else
                       'mutex_entry_ratio_limit')
    limits = {r.get(threshold_field) for r in candidate if r['arm'] == 'kdlock'}
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
    return dict(post_work_rounds=post_work_rounds, implementation=implementation,
                queue_policy=next(iter(policies)),
                owned_preflight_policy=preflight_policy,
                owned_mutex_preflight=preflight_enabled,
                owned_mutex_preflight_spins=preflight_spins,
                owned_mutex_preflight_queue=preflight_queue,
                threshold_field=threshold_field, threshold=next(iter(limits)),
                verdict=verdict, missing=missing, checks=checks)


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
    parser.add_argument('--post-work-rounds', type=int, choices=range(1, 257), default=64,
                        help='expected frozen workload rounds; does not change or rebuild inputs')
    args = parser.parse_args()
    baseline = load_run(args.baseline, args.post_work_rounds)
    require({r['threads'] for r in baseline} == set(GRID), 'incomplete baseline grid')
    for t in GRID:
        for arm in ('native', 'kdlock'):
            metrics([r for r in baseline if r['threads'] == t and r['arm'] == arm])
    candidate_records = {p: load_run(p, args.post_work_rounds) for p in args.candidates}
    trials = [dict(path=str(p), **evaluate(baseline, rows))
              for p, rows in candidate_records.items()]
    require(len({t['implementation'] for t in trials}) == 1,
            'screen each mutex implementation separately before choosing a threshold')
    require(len({t['queue_policy'] for t in trials}) == 1,
            'screen each queue policy separately before choosing a threshold')
    require(len({(t['owned_preflight_policy'], t['owned_mutex_preflight_spins'],
                  t['owned_mutex_preflight_queue'], t['owned_mutex_preflight'])
                 for t in trials}) == 1,
            'screen each preflight policy separately before choosing a threshold')
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
            records = load_run(p, args.post_work_rounds)
            require(json.loads((p/'source-sha256.json').read_text()) == frozen,
                    'confirmation source differs from selected screen')
            require_fresh(records, seen)
            confirmation.append(dict(path=str(p), **evaluate(baseline, records)))
        require(all(c['implementation'] == trials[0]['implementation'] for c in confirmation),
                'confirmation mutex implementation differs from selected screen')
        require(all(c['queue_policy'] == trials[0]['queue_policy'] for c in confirmation),
                'confirmation queue policy differs from selected screen')
        require(all((c['owned_preflight_policy'], c['owned_mutex_preflight_spins'],
                     c['owned_mutex_preflight_queue'], c['owned_mutex_preflight']) ==
                    (trials[0]['owned_preflight_policy'], trials[0]['owned_mutex_preflight_spins'],
                     trials[0]['owned_mutex_preflight_queue'], trials[0]['owned_mutex_preflight'])
                    for c in confirmation),
                'confirmation preflight policy differs from selected screen')
        if all(c['verdict'] == 'PASS' and c['threshold'] == min(passing) for c in confirmation):
            selected = min(passing)
    write_json(args.output, dict(post_work_rounds=args.post_work_rounds,
        candidate_implementation=trials[0]['implementation'],
        selected_implementation=trials[0]['implementation'] if selected is not None else None,
        selected_default=selected, retained_default=256 if selected is None else None,
        acceptance='97% separately for median whole-run and best valid warmed peak in each block',
        baseline=str(args.baseline), candidates=trials, confirmations=confirmation))
    print(json.dumps(dict(selected_default=selected,
                         verdicts=[(r['threshold'], r['verdict']) for r in trials])))


if __name__ == '__main__':
    main()
