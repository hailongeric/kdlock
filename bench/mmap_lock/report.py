#!/usr/bin/env python3
"""Summarize exactly 24 qualified cases; keep observations and trials separate."""
import argparse
import json
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
    if len(rows) != 24:
        raise ValueError('exactly 24 qualified cases required; do not fill missing cases with rejected timings')
    keyed = {}
    boots, ready_bindings = {}, {}
    identity = rows[0]['prepared']
    for r in rows:
        key = (r['repeat'], r['mode'], r['case'])
        if (not r['passed'] or not r['drained'] or not r['accepted'] or not r['endpoint_checked'] or
                r['prepared'] != identity or key not in paired.ORDER or key in keyed):
            raise ValueError('rejected, duplicate, mixed-input or unexpected timing case')
        if r['spec'] != paired.specification(r['case'], r['repeat'], r['mode']):
            raise ValueError('workload/instrumentation differs')
        block = paired.expected_block(r['repeat'], r['mode'])
        if r['block'] != block or not r['boot_id']:
            raise ValueError('boot block differs')
        if boots.setdefault(block, r['boot_id']) != r['boot_id'] or \
                ready_bindings.setdefault(block, r['ready']) != r['ready']:
            raise ValueError('shared block changed boot or readiness')
        keyed[key] = r
    if set(keyed) != set(paired.ORDER):
        raise ValueError('incomplete paired plan')
    if len(boots) != 4 or len(set(boots.values())) != 4:
        raise ValueError('four distinct measured boot blocks required')
    for index, key in enumerate(paired.ORDER):
        expected = None if index == 0 else receipt_bindings[paired.ORDER[index-1]]
        if keyed[key].get('previous') != expected:
            raise ValueError('exact chronological predecessor chain differs')
    points = []
    for case, (n, observation) in enumerate(paired.CASES):
        arms = {}
        for mode in ('native', 'kd'):
            selected = [keyed[(repeat, mode, case)] for repeat in range(3)]
            arms[mode] = dict(throughput_ops_s=spread([r['measurement']['whole_ops_s'] for r in selected]),
                boot_ids=[r['boot_id'] for r in selected],
                latency_sample_counts=[r['measurement']['latency_samples'] for r in selected],
                latency_percentiles_ns={p: spread([r['measurement']['latency_percentiles_ns'][p]
                    for r in selected]) for p in ('50', '95', '99')} if observation == 'sampled' else {})
        ratios = [keyed[(r, 'kd', case)]['measurement']['whole_ops_s'] /
                  keyed[(r, 'native', case)]['measurement']['whole_ops_s'] for r in range(3)]
        points.append(dict(threads=n, observation=observation, arms=arms,
                           paired_kd_over_native_throughput=spread(ratios)))
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
    if any(r.get(key) != value for key, value in client.items()
           if key not in ('passed', 'accepted', 'drained')):
        raise ValueError('final receipt changed client identity/specification')
    ready = paired.load_bound(r['ready'])
    if (not ready['passed'] or any(ready[k] != r[k] for k in ('mode', 'boot_id', 'block', 'prepared'))):
        raise ValueError('readiness mode/boot/block/preparation differs')
    paired.load_bound(r['prepared'])
    for mode, binding in zip(('native', 'kd'), r['validated'], strict=True):
        paired.validation_receipt(paired.file_bound(binding), mode, r['prepared'])
    evidence = r['qualification']
    for key in ('controller', 'endpoint', 'admission'):
        paired.file_bound(evidence[key])
    directory = Path(evidence['controller']['path']).parent
    repeated = paired.qualify(path.parent, client, directory)
    if repeated != evidence or r['endpoint_captured_utc'] != repeated['captured_utc']:
        raise ValueError('saved qualification bindings differ')
    raw = [json.loads(line) for line in (path.parent / 'client.jsonl').read_text().splitlines()]
    if paired.measurement(raw, r['spec'], r['mode']) != r['measurement']:
        raise ValueError('recorded measurement differs from raw client output: ' + str(path))
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipts', type=Path, nargs='+')
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
    print(json.dumps(summarize(rows, bindings), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
