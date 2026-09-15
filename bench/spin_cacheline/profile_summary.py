#!/usr/bin/env python3
"""Offline flat-IP attribution using saved symbols and exact generated ranges.

Weights are sampled event periods, not isolated function timings. Preserve
unresolved addresses instead of attributing arbitrary executable allocations
to the nearest kernel symbol. Never execute a workload or open a JIT device.
"""
import argparse
import bisect
import collections
import csv
import json
import re
import subprocess
from pathlib import Path


def symbol_ranges(kallsyms, sizes, module):
    addresses = collections.defaultdict(list)
    for line in kallsyms.splitlines():
        fields = line.split()
        if len(fields) not in (3, 4) or fields[1] not in 'tTwW':
            continue
        owner = fields[3].strip('[]') if len(fields) == 4 else 'kernel'
        if owner == module:
            addresses[fields[2]].append(int(fields[0], 16))
    result = []
    definitions = collections.defaultdict(list)
    for line in sizes.splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[2] not in 'tTwW' or fields[3] not in addresses:
            continue
        definitions[fields[3]].append((int(fields[0], 16), int(fields[1], 16)))
    for name, entries in definitions.items():
        locations = sorted(addresses[name])
        entries.sort()
        if len(locations) != len(entries):
            continue
        # Different compilation units may contain static functions with the
        # same name (spin/mutex both have execute_cs). Match distinct addresses
        # only when their relative layout proves a common relocation bias.
        if len(entries) > 1 and len({address - entry[0] for address, entry
                                    in zip(locations, entries)}) != 1:
            continue
        for begin, (_, length) in zip(locations, entries):
            if begin and length:
                result.append((begin, begin + length, module + ':' + name))
    return result


def aggregate(samples, ranges):
    ordered = sorted(ranges)
    starts = [r[0] for r in ordered]
    ends = []
    for _, end, _ in ordered:
        ends.append(max(ends[-1] if ends else 0, end))
    weights = collections.Counter()
    counts = collections.Counter()
    offsets = collections.defaultdict(collections.Counter)
    sample_count = 0
    for line in samples.splitlines():
        fields = line.split()
        if not fields or fields[0] != 'sc_worker':
            continue
        if len(fields) != 3:
            raise ValueError('unexpected perf script fields')
        period, ip = int(fields[1]), int(fields[2], 16)
        if period <= 0:
            raise ValueError('nonpositive sample period')
        index = bisect.bisect_right(starts, ip) - 1
        label, offset = 'unresolved', ip
        if index >= 0:
            # Assembly labels can lie inside a larger C function. If a
            # shorter inner symbol has ended, retain the containing function;
            # the prefix maximum also stops lookup across real unmapped gaps.
            while index >= 0 and ends[index] > ip:
                begin, end, candidate = ordered[index]
                if begin <= ip < end:
                    label, offset = candidate, ip - begin
                    break
                index -= 1
        weights[label] += period
        counts[label] += 1
        offsets[label][offset] += period
        sample_count += 1
    if not sample_count:
        raise ValueError('no worker samples')
    total = sum(weights.values())
    rows = [dict(symbol=name, samples=counts[name], sampled_period=weight,
                 sample_weight_percent=100 * weight / total,
                 hot_offsets=[dict(offset=hex(offset), sampled_period=value)
                              for offset, value in offsets[name].most_common(12)])
            for name, weight in weights.most_common()]
    return dict(worker_samples=sample_count, total_sampled_period=total, symbols=rows)


def summarize(out, kernel_symbols=None):
    session = out / 'profile'
    record = json.loads((session / 'session.json').read_text())
    if not (record['execution_status'] == 'OK' and record['drained'] and
            record['measurement']['data_ok'] and record.get('performance_result') is False):
        raise ValueError('profile session is not a correct, drained diagnostic')
    report = (session / 'perf-report.txt').read_text()
    lost = re.search(r'Total Lost Samples: ([0-9]+)', report)
    if not lost or int(lost[1]):
        raise ValueError('missing or nonzero lost-sample count')
    header = (session / 'perf-header.txt').read_text()
    sample_type = re.search(r'sample_type = ([A-Z_|]+)', header)
    if not sample_type or set(sample_type[1].split('|')) != {'IP', 'TID', 'TIME', 'PERIOD'}:
        raise ValueError('unexpected sampling fields; flat IP samples required')
    kallsyms = (session / 'kallsyms.txt').read_text()
    sizes = (kernel_symbols or session / 'kernel-symbol-sizes.txt').read_text()
    ranges = symbol_ranges(kallsyms, sizes, 'kernel')
    for module, relative in (
        ('kdlock_km', 'bench/spin_cacheline/.build/provider/kernel_module/kdlock_km.ko'),
        ('spin_cacheline', 'workload_modules/spin_cacheline/spin_cacheline.ko')):
        symbols = subprocess.check_output(['nm', '-S', '--defined-only', str(out/'binaries'/relative)],
                                          text=True, timeout=30)
        ranges.extend(symbol_ranges(kallsyms, symbols, module))
    if record['arm'] == 'kdlock':
        entry = record['published_before']['entry']
        image = session/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm/jit.bin'
        ranges.append((entry['code'], entry['code'] + image.stat().st_size, 'generated:jit_image'))
    result = aggregate((session/'perf-samples.txt').read_text(), ranges)
    result.update(event=record['sample_event'], frequency_hz=record['sample_frequency_hz'],
                  lost_samples=0, callchain=False, jit_bodies=record['jit_bodies'],
                  jit_share=record['jit_share'], arm=record['arm'], threads=record['threads'],
                  scope='flat sampled event-period weights; not isolated function times')
    (session/'hotspots.json').write_text(json.dumps(result, indent=2) + '\n')
    with (session/'hotspots.csv').open('w', newline='') as output:
        fields = ['symbol', 'samples', 'sampled_period', 'sample_weight_percent']
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: row[k] for k in fields} for row in result['symbols'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--kernel-symbols', type=Path)
    args = parser.parse_args()
    result = summarize(args.output.resolve(), args.kernel_symbols)
    print(json.dumps({k: v for k, v in result.items() if k != 'symbols'}, indent=2))
    for row in result['symbols'][:12]:
        print(f"{row['sample_weight_percent']:7.2f}% {row['samples']:7d} {row['symbol']}")
