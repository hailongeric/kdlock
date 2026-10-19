#!/usr/bin/env python3
"""Print compact throughput and batch evidence from an existing comparison JSON.

This formatter reads data only. It does not replace finalization or the
independent source/archive and arithmetic audits.
"""
import argparse
import json
from pathlib import Path


def interval(value):
    if not value or not value.get('n'):
        return '—'
    return f"{value['median']:.3f} [{value['min']:.3f}, {value['max']:.3f}]"


def percent(value):
    return '—' if value is None else f'{100 * value:.3f}%'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    args = parser.parse_args()
    data = json.loads(args.comparison.read_text())
    print('Retained-data summary; finalization and independent audits are separate.')
    print('Collection complete:', data.get('complete'), '; issues:', len(data.get('issues', [])))
    print('Batch ratio includes warmup/checks. Synthetic counters establish entry only.\n')
    print('| Arm / revision | Workload | Workers | Whole Mops/s median [min, max] | Bodies/combiner median [min, max] | Entry share | Returned share | Class / status |')
    print('| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |')
    order = {arm: index for index, arm in enumerate(data['arms'])}
    for row in sorted(data['groups'], key=lambda r: (r['workload'], r['threads'], order[r['arm']])):
        print(f"| {row['arm']} / {row['source_commit']} | {row['workload']} | {row['threads']} | "
              f"{interval(row['whole_mops'])} | {interval(row['whole_session_bodies_per_combiner'])} | "
              f"{percent(row['measured_body_entry_share'])} | {percent(row['measured_returned_jit_share'])} | "
              f"{row['jit_class']} / {row['status']} |")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
