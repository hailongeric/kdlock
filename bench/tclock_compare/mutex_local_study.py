#!/usr/bin/env python3
"""Audit owned c01/post64 at 1–8 workers; no live execution.

Each count must reach 97% of its paired Native median whole-run throughput and
best valid warmed peak. A screen and two fresh source/policy-identical blocks
must pass independently. JIT is classified, with no minimum in this local scope.
Historical through-28/higher-thread acceptance remains in mutex_study.py.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import mutex_study as study
import run
from bench_runtime import FAULT, digest, require
from summarize import write_json

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
GENERIC_HELPER = ROOT/'bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/evidence.py'
PRIMARY = tuple(range(1, 9))
VARYING_FIELDS = {'name', 'threads', 'repeat', 'cpus', 'cpu_nodes'}
OLD_NATIVE_FIRST = {'owned_mutex_native_first', 'owned_mutex_native_first_spins',
                    'owned_mutex_early_release'}


def generic_helpers():
    """Reuse pure archive IO/hash/export helpers, never historical policy checks.

Current study.load_run and session validators own local-first identity. This
module does not call the earlier helper's audit_group/audit_backend functions.
Report-specific users of that archive traversal must explicitly inject current
protocol validators; the helper defaults retain its frozen historical policy.
"""
    sys.path.insert(0, str(GENERIC_HELPER.parent))
    spec = importlib.util.spec_from_file_location('local_study_generic_evidence', GENERIC_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy_identity(plan):
    policies = {json.dumps({key: value for key, value in item.items()
                           if key not in VARYING_FIELDS}, sort_keys=True)
                for item in plan if item['arm'] == 'kdlock'}
    require(len(policies) == 1, 'mixed owned policies in one block')
    return json.loads(next(iter(policies)))


def require_scope(rows, candidate):
    expected = {(arm, count, repeat) for arm in ('native', 'kdlock')
                for count in PRIMARY for repeat in range(3)}
    require(len(rows) == len(expected) and
            {(r['arm'], r['threads'], r['repeat']) for r in rows} == expected,
            'each block must contain exactly 48 Native/owned 1–8 samples')
    geometries = set()
    for record in rows:
        layout = record['layout']
        require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0,
                'Native/owned object geometry differs')
        geometries.add((layout['lock_addr']-layout['data_addr'], layout['slots'],
                        tuple(address-layout['data_addr'] for address in layout['slot_addr'])))
        require(record.get('scenario') == 'plain' and record['sample_ms'] == 10 and
                not record.get('diagnostic', False),
                'sample is not an uninstrumented plain c01 score')
        if record['arm'] == 'kdlock':
            require(record.get('mutex_implementation') == 'owned-v1' and
                    record.get('mutex_routing') == 'adaptive' and
                    record.get('mutex_acceptance') == 'adaptive-performance',
                    'owned adaptive-performance identity required')
            study.require_owned_identity(record)
            require(not OLD_NATIVE_FIRST.intersection(record),
                    'archived bounded-native-first controls are outside this study')
            if candidate:
                require(record.get('owned_mutex_cabi') is True and
                        record.get('owned_acquire_policy') == 'linux_local_first' and
                        record.get('owned_release_policy') == 'guarded_owner_release' and
                        record['parameters'].get('owned_mutex_protocol') == 'linux_local_first_v1',
                        'candidate must use ABI4 Linux local-first and guarded release')
    require(len(geometries) == 1, 'Native/owned lock-to-payload placement differs')
    for threads in PRIMARY:
        cohort = [r for r in rows if r['threads'] == threads]
        orders = [[r['arm'] for r in cohort if r['repeat'] == repeat] for repeat in range(3)]
        require(set(orders[0]) == {'native', 'kdlock'} and
                orders[1] == orders[0][::-1] and orders[2] == orders[0] and
                [r['repeat'] for r in cohort] == [0, 0, 1, 1, 2, 2],
                'three rounds must alternate backend order')
    require(all(left['measurement']['finished_ns'] < right['measurement']['started_ns']
                for left, right in zip(rows, rows[1:])),
            'actual sample order differs from the sequential frozen plan')


def audit_block(folder, candidate, helpers):
    # Maintained source/raw/JIT checks call current session policy validators.
    # Old ABI2 baseline records with absent caller metadata remain distinct.
    rows = study.load_run(folder, 64)
    require_scope(rows, candidate)
    plan = helpers.read(folder/'plan.json')
    policy = policy_identity(plan)
    aggregate = helpers.read(folder/'records.json')
    require(len(aggregate) == len(rows) and
            {r['name'] for r in aggregate} == {r['name'] for r in rows},
            'aggregate samples differ from plan')
    aggregate = {r['name']: r for r in aggregate}
    hashes = {}
    for record in rows:
        path = folder/record['name']
        require(all(aggregate[record['name']].get(key) == value for key, value in record.items()) and
                aggregate[record['name']].get('score_eligible') is True,
                'aggregate differs from the audited session or is unscored')
        require(helpers.read(path/'drain.counts.json')['active'] == 0,
                'workers remain active after drain')
        log = (path/'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault in scored sample')
        if record['arm'] == 'native':
            require(record['jit_bodies'] == record['delegated_bodies'] == 0 and
                    record['execution_class'] == 'NATIVE', 'Native execution identity differs')
        else:
            completed = record['measurement']['completed']
            require(record['jit_share'] == record['jit_bodies']/completed and
                    record['delegated_bodies'] == record['jit_bodies'],
                    'returned-body classification differs')
            for key in ('result_schedule_calls', 'result_wakes'):
                require(record['mutex_wait_after'][key] - record['mutex_wait_before'][key] ==
                        record['mutex_wait_delta'][key] >= 0, 'wait delta differs')
            # load_run checks owned retirement, task references and owner ACKs.
        hashes[record['name']] = {name: digest(path/name) for name in
                                ('session.json', 'measure.json', 'kernel.log', 'drain.counts.json')}
    # load_run verified each source/binary byte; only collect manifests here.
    receipt = helpers.frozen(folder, verify=False)
    receipt.update(sessions=len(rows), raw_artifact_sha256=hashes, passed=True)
    return rows, policy, receipt


def evaluate(rows):
    checks = []
    for threads in PRIMARY:
        pair = {arm: study.metrics([r for r in rows if r['threads'] == threads and r['arm'] == arm])
                for arm in ('native', 'kdlock')}
        ratios = {key: pair['kdlock'][key]/pair['native'][key]
                  for key in ('median_whole', 'best_peak')}
        checks.append(dict(threads=threads, candidate=pair['kdlock'], paired_native=pair['native'],
                           ratios=ratios, passed=all(value >= .97 for value in ratios.values())))
    return dict(checks=checks, passed=all(item['passed'] for item in checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--baseline', required=True, help='relative fresh baseline directory')
    parser.add_argument('--screen', help='relative local-first screening directory')
    parser.add_argument('--confirmations', nargs=2, default=[], metavar=('BLOCK1', 'BLOCK2'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    helpers = generic_helpers()
    require(not args.confirmations or args.screen, 'confirmation blocks require a screen')
    roles = [('baseline', args.baseline)]
    if args.screen:
        roles.append(('screen', args.screen))
    roles += [('confirmation' + str(i + 1), value) for i, value in enumerate(args.confirmations)]
    groups = helpers.declared(args.raw.resolve(), [label + '=' + value for label, value in roles])
    seen, comparisons, receipts, policies = set(), {}, {}, {}
    for label, folder in groups.items():
        rows, policies[label], receipts[label] = audit_block(folder, label != 'baseline', helpers)
        study.require_fresh(rows, seen)
        comparisons[label] = evaluate(rows)
    for label, _ in roles:
        if not label.startswith('confirmation'):
            continue
        require(helpers.read(groups[label]/'source-sha256.json') ==
                helpers.read(groups['screen']/'source-sha256.json'), 'confirmation source differs')
        require(policies[label] == policies['screen'], 'confirmation policy differs')
    accepted = bool(args.screen and len(args.confirmations) == 2 and
                    all(comparisons[label]['passed'] for label in
                        ('screen', 'confirmation1', 'confirmation2')))
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out/'acceptance.json', dict(
        schema=1, scope='owned c01 post64 workers 1–8 only', primary=list(PRIMARY),
        higher_thread_requirement=False, minimum_jit_requirement=False,
        required_fresh_confirmation_blocks=2, performance_target_reached=accepted,
        comparisons=comparisons, receipts=receipts, policies=policies, command=sys.argv,
        auditor_sha256=digest(Path(__file__)), generic_helper_sha256=digest(GENERIC_HELPER),
        maintained_validator_sha256={name: digest(Path(__file__).parent/name)
                                    for name in ('mutex_study.py', 'session.py', 'run.py')},
        limitations=['No extrapolation above 8 workers or other workloads.',
                     'JIT/SELF classification retained; no minimum JIT required in this scope.',
                     'Both metrics and each fresh block must pass independently.',
                     'Every declared sample and raw correctness/progress/drain check is required.',
                     'Protocol unit/live correctness coverage is a separate receipt.']))
    print(json.dumps(dict(audited_samples=sum(r['sessions'] for r in receipts.values()),
                          performance_target_reached=accepted, output=str(args.out))))


if __name__ == '__main__':
    main()
