#!/usr/bin/env python3
"""Read an archived ELF and flat samples as data; never execute retained code."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--symbol', default='__kd_mutex_lock_slowpath')
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.input.resolve()):
        raise ValueError('require a new output outside the preserved input')
    module = args.input / 'build/kdlock_km.ko'
    argv = ['objdump', '-d', '--no-show-raw-insn', '--disassemble=' + args.symbol, str(module)]
    assembly = subprocess.check_output(argv, text=True, timeout=30)
    starts = re.findall(r'^([0-9a-f]+) <' + re.escape(args.symbol) + r'>:$', assembly, re.M)
    if len(starts) != 1:
        raise ValueError('ELF symbol absent or ambiguous')
    start = int(starts[0], 16)
    instructions = {int(match[1], 16) - start: match[2] for line in assembly.splitlines()
                    if (match := re.fullmatch(r'\s*([0-9a-f]+):\s+(.+)', line))}
    rows = []
    for record in json.loads((args.input / 'records.json').read_bytes()):
        folder = args.input / record['name']
        kallsyms = (folder / 'kallsyms').read_text()
        addresses = [int(row[0], 16) for line in kallsyms.splitlines()
                     if len(row := line.split()) >= 3 and row[2] == args.symbol]
        if len(addresses) != 1:
            raise ValueError('loaded symbol absent or ambiguous')
        total, periods, counts, errors = 0, Counter(), Counter(), []
        for number, line in enumerate((folder / 'perf-samples.txt').read_text().splitlines(), 1):
            if not line.lstrip().startswith('sc_worker '):
                continue
            try:
                head, tail = line.split(' cycles:k:', 1)
                period = int(head.rsplit(':', 1)[1])
                ip, symbol_and_dso = tail.strip().split(None, 1)
                symbol = symbol_and_dso.rsplit(' (', 1)[0]
                if period <= 0:
                    raise ValueError('nonpositive period')
                total += period
                if symbol.split('+0x', 1)[0] == args.symbol:
                    offset = int(ip, 16) - addresses[0]
                    periods[offset] += period
                    counts[offset] += 1
            except (ValueError, IndexError):
                errors.append(dict(line=number, text=line))
        if not total or errors:
            raise ValueError('missing or malformed worker samples: ' + repr(errors[:3]))
        rows.append(dict(name=record['name'], threads=record['threads'], symbol=args.symbol,
            sc_worker_period=total, symbol_period=sum(periods.values()),
            symbol_worker_percent=100 * sum(periods.values()) / total,
            measured_returned_jit_share=record['jit_completions'] / record['measurement']['completed'],
            input_sha256={name: digest(folder / name) for name in ('kallsyms', 'perf-samples.txt', 'perf-report.txt')},
            offsets=[dict(offset=hex(offset), instruction=instructions.get(offset), samples=counts[offset],
                          period=period, worker_percent=100 * period / total)
                     for offset, period in periods.most_common()]))
    result = dict(passed=True, scope='Read-only ELF disassembly and inert text inspection on source host',
                  command=argv, elf_sha256=digest(module), records_sha256=digest(args.input / 'records.json'),
                  disassembly_sha256=hashlib.sha256(assembly.encode()).hexdigest(),
                  helper_sha256=digest(Path(__file__)), profiles=rows,
                  limitations=['The independent full profile audit checks loss, parsing, period totals and source binding.',
                               'Sampled IPs are subject to skid; instruction adjacency is not direct cycle cost or CAS retry count.',
                               'The worker denominator includes polling; reduced wait time need not appear as time spent in an atomic instruction.'])
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=True, profiles=len(rows), output=str(args.output))))


if __name__ == '__main__':
    main()
