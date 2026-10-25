#!/usr/bin/env python3
"""Summarize one bound historical or prospective campaign without mixing plans."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired


def spread(values):
    return dict(n=len(values), values=values, median=statistics.median(values),
                minimum=min(values), maximum=max(values),
                sample_cv=statistics.stdev(values)/statistics.mean(values))


def summarize(rows, receipt_bindings):
    if not rows:
        raise ValueError('complete campaign receipts required')
    plan = paired.row_plan(rows[0])
    policy = paired.window.policy(rows[0])
    cases, order = paired.cases_for(plan), paired.order_for(plan)
    if len(rows) != len(order) or set(receipt_bindings) != set(order):
        raise ValueError(f'exactly {len(order)} qualified cases and bindings required for {plan}')
    keyed = {}
    boots, ready_bindings = {}, {}
    identity = rows[0]['prepared']
    for r in rows:
        key = (r['repeat'], r['mode'], r['case'])
        if (not r['passed'] or not r['drained'] or not r['accepted'] or not r['endpoint_checked'] or
                r.get('screen') or paired.window.policy(r) != policy or
                r['prepared'] != identity or paired.row_plan(r) != plan or key not in order or key in keyed):
            raise ValueError('rejected, duplicate, mixed-input or unexpected timing case')
        if r['spec'] != paired.specification(r['case'], r['repeat'], r['mode'], plan):
            raise ValueError('workload/instrumentation differs')
        rate = r['measurement']['whole_ops_s']
        if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise ValueError('finite positive completed-cycle throughput required')
        if plan in paired.PLAIN_PLANS and (r['measurement']['latency_samples'] != 0 or
                                               r['measurement']['latency_percentiles_ns'] != {}):
            raise ValueError('plain campaign contains workload latency sampling')
        block = paired.expected_block(r['repeat'], r['mode'])
        if r['block'] != block or not r['boot_id']:
            raise ValueError('boot block differs')
        if boots.setdefault(block, r['boot_id']) != r['boot_id'] or \
                ready_bindings.setdefault(block, r['ready']) != r['ready']:
            raise ValueError('shared block changed boot or readiness')
        keyed[key] = r
    if set(keyed) != set(order):
        raise ValueError('incomplete paired plan')
    if len(boots) != 4 or len(set(boots.values())) != 4:
        raise ValueError('four distinct measured boot blocks required')
    for index, key in enumerate(order):
        expected = None if index == 0 else receipt_bindings[order[index-1]]
        if keyed[key].get('previous') != expected:
            raise ValueError('exact chronological predecessor chain differs')
    points = []
    for case, (n, observation) in enumerate(cases):
        arms = {}
        for mode in ('native', 'kd'):
            selected = [keyed[(repeat, mode, case)] for repeat in range(3)]
            arms[mode] = dict(throughput_ops_s=spread([r['measurement']['whole_ops_s'] for r in selected]),
                boot_ids=[r['boot_id'] for r in selected])
            if plan == paired.LEGACY_PLAN:
                arms[mode].update(latency_sample_counts=[r['measurement']['latency_samples'] for r in selected],
                    latency_percentiles_ns={p: spread([r['measurement']['latency_percentiles_ns'][p]
                        for r in selected]) for p in ('50', '95', '99')} if observation == 'sampled' else {})
        ratios = [keyed[(r, 'kd', case)]['measurement']['whole_ops_s'] /
                  keyed[(r, 'native', case)]['measurement']['whole_ops_s'] for r in range(3)]
        points.append(dict(threads=n, observation=observation, arms=arms,
                           paired_kd_over_native_throughput=spread(ratios)))
    if plan in paired.PLAIN_PLANS:
        limitations = ('Three paired observations; adjacent repetitions can share a boot. '
                       'No independent-boot, NUMA scaling, reader scaling, delegation or TCLock claim. '
                       'No workload latency sampling; progress and correctness accounting retained.')
        if plan == paired.SCALING_PLAN:
            limitations = ('Three paired observations; adjacent repetitions share boots. '
                           'Workers use CPUs 0..N-1, collector 63; counts above 32 span both guest NUMA nodes. '
                           'The count sweep does not isolate NUMA effects or establish independent-boot, '
                           'reader-scaling, delegation or TCLock results. No workload latency sampling; '
                           'progress and correctness accounting retained.')
        return dict(plan=plan, measurement_policy=policy, qualified_cases=len(order), paired_repetitions=3, prepared=identity,
            points=points, throughput_definition='Completed whole mmap/munmap cycles / actual elapsed time',
            limits=paired.bounds(plan), limitations=limitations)
    instrumentation = {str(n): {mode: spread([
        keyed[(repeat, mode, paired.CASES.index((n, 'sampled')))]['measurement']['whole_ops_s'] /
        keyed[(repeat, mode, paired.CASES.index((n, 'plain')))]['measurement']['whole_ops_s']
        for repeat in range(3)]) for mode in ('native', 'kd')} for n in (1, 16)}
    return dict(qualified_cases=24, paired_repetitions=3, prepared=identity, points=points,
        sampled_over_plain_throughput=instrumentation,
        latency_definition='Sampled complete mmap/munmap cycles, not lock-acquisition latency',
        limitations='Three paired observations; adjacent repetitions can share a boot. No independent-boot '
                    'claim, pooled latency samples, NUMA scaling, delegation or TCLock comparison. '
                    'Observation order is fixed; sampled/plain ratios do not isolate causation.')


def replay(path):
    """Use only saved evidence; missing/changed captures cannot be replaced."""
    r = paired.common.load(path)
    client = paired.common.load(path.parent / 'client-result.json')
    plan = paired.row_plan(r)
    policy = paired.window.policy(r)
    if paired.row_plan(client) != plan or paired.window.policy(client) != policy:
        raise ValueError('final/client campaign plan differs')
    if any(r.get(key) != value for key, value in client.items()
           if key not in ('passed', 'accepted', 'drained')):
        raise ValueError('final receipt changed client identity/specification')
    ready = paired.load_bound(r['ready'])
    if (not ready['passed'] or paired.row_plan(ready) != plan or paired.window.policy(ready) != policy or
            any(ready[k] != r[k] for k in ('mode', 'boot_id', 'block', 'prepared'))):
        raise ValueError('readiness mode/boot/block/preparation differs')
    paired.load_bound(r['prepared'])
    if r.get('screen'):
        if policy != paired.window.POLICY or plan != paired.SCALING_PLAN or r['case'] != 9 or r['repeat'] != 0:
            raise ValueError('unexpected controlled screen scope')
        paired.mapping.SITES = paired.common.load(paired.SITES)
        raw = [json.loads(line) for line in paired.file_bound(r['fixed_raw']).read_text().splitlines()]
        proof = paired.mapping.validate(raw, 'cycle', paired.FIXED_THREADS, paired.FIXED_ITERATIONS, r['mode'])
        if (any(r['fixed'][k] != v for k, v in proof.items()) or
                r['fixed']['rejected_mutations'] != paired.PROOF_MUTATIONS or
                r['fixed']['health'] != 'files=0 mm_refs=0 destroyed=1 release_errors=0'):
            raise ValueError('screen fixed proof differs')
    else:
        for mode, binding in zip(('native', 'kd'), r['validated'], strict=True):
            v = paired.validation_receipt(paired.file_bound(binding), mode, r['prepared'], plan)
            if paired.window.policy(v) != policy:
                raise ValueError('validation measurement policy differs')
    evidence = r['qualification']
    for key in ('controller', 'endpoint', 'admission'):
        paired.file_bound(evidence[key])
    directory = Path(evidence['controller']['path']).parent
    repeated = paired.qualify(path.parent, client, directory)
    if repeated != evidence or r['endpoint_captured_utc'] != repeated['captured_utc']:
        raise ValueError('saved qualification bindings differ')
    raw = [json.loads(line) for line in (path.parent / 'client.jsonl').read_text().splitlines()]
    if paired.measurement(raw, r['spec'], r['mode'], plan) != r['measurement']:
        raise ValueError('recorded measurement differs from raw client output: ' + str(path))
    return r


def screen_summary(rows):
    """One pair validates the prospective harness; it is not the 126-case result."""
    if len(rows) != 2 or {r['mode'] for r in rows} != {'native', 'kd'}:
        raise ValueError('one Native/KD screen pair required')
    rows = sorted(rows, key=lambda r: r['mode'])
    for r in rows:
        if (not all(r.get(k) for k in ('screen', 'passed', 'accepted', 'drained', 'endpoint_checked')) or
                paired.window.policy(r) != paired.window.POLICY or paired.row_plan(r) != paired.SCALING_PLAN or
                r['spec'] != paired.specification(9, 0, r['mode'], paired.SCALING_PLAN) or
                r['block'] != (0 if r['mode'] == 'native' else 1) or
                r['measurement']['latency_samples'] != 0):
            raise ValueError('screen scope, correctness or policy differs')
    if (rows[0]['prepared'] != rows[1]['prepared'] or rows[0]['boot_id'] == rows[1]['boot_id'] or
            rows[0]['qualification']['window']['roles']['sha256'] !=
            rows[1]['qualification']['window']['roles']['sha256']):
        raise ValueError('screen builds, boots or role policy differ')
    rates = {r['mode']: r['measurement']['whole_ops_s'] for r in rows}
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in rates.values()):
        raise ValueError('finite positive screen rates required')
    return dict(measurement_policy=paired.window.POLICY, screen=True, qualified_cases=2,
        rates=rates, kd_over_native=rates['kd']/rates['native'],
        limitations='One unscored harness-validation pair; no variability estimate, optimization gain '
                    'or completed throughput matrix. The 21-count, three-pair plan remains unchanged.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipts', type=Path, nargs='+')
    p.add_argument('--screen', action='store_true')
    a = p.parse_args()
    rows = []
    bindings = {}
    for path in a.receipts:
        path = path.resolve()
        r = replay(path)
        key = (r['repeat'], r['mode'], r['case'])
        if key in bindings:
            raise ValueError('duplicate case receipt')
        bindings[key] = paired.bind(path)
        rows.append(r)
    print(json.dumps(screen_summary(rows) if a.screen else summarize(rows, bindings), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
