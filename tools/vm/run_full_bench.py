#!/usr/bin/env python3
"""Run all maintained comparison payloads at 22 worker counts in the guest.

The collector needs its own guest CPU. On a 64-core host the 64-worker case
must record any physical-core sharing with collection and QEMU services.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
THREADS = [*range(1, 9), *range(12, 65, 4)]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def commands(output, cpus, collector, include_multicacheline=False):
    """Compare one-cacheline and hash payloads; larger sizes are opt-in."""
    cases = [('spin', 'cacheline', 1), ('mutex', 'cacheline', 1),
             ('rwlock', 'rcuht', 0), ('spin', 'rcuht', 0),
             ('mutex', 'rcuht', 0), ('rwlock', 'cacheline', 1)]
    if include_multicacheline:
        cases += [('spin', 'cacheline', 8), ('mutex', 'cacheline', 8),
                  ('spin', 'cacheline', 16), ('mutex', 'cacheline', 16),
                  *[('rwlock', 'cacheline', n) for n in (2, 4, 8, 16)]]
    result = []
    for kind, workload, lines in cases:
        name = f'{kind}-{workload}' + (f'-c{lines:02d}' if lines else '')
        runner = ('bench/rwlock_compare/run.py' if kind == 'rwlock' else
                  'bench/tclock_compare/run_mutex.py' if kind == 'mutex' else
                  'bench/tclock_compare/run.py')
        args = [sys.executable, runner, '--backends', 'native', 'tclock', 'kdlock',
                '--threads', *map(str, THREADS), '--collector-cpu', str(collector),
                '--repeats', '3', '--duration-ms', '2000', '--peak-window-ms', '300',
                '--peak-settle-ms', '300', '--kernel-source', '/root/linux-6.1.159-kdclobber2',
                '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919',
                '--output', str(output / name)]
        if kind == 'rwlock':
            args += ['--workloads', workload, '--write-percent', '1', '20',
                     '--cpus', *map(str, cpus)]
        else:
            args += ['--workload', workload, '--cpus', ','.join(map(str, cpus)),
                     '--keep-going-no-jit']
        if lines:
            args += ['--cachelines', str(lines)]
        result.append(dict(name=name, lock_kind=kind, workload=workload,
                           cachelines=lines, expected_sessions=len(THREADS) * 9 *
                           (2 if kind == 'rwlock' else 1), argv=args))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpus', type=int, nargs='+', required=True)
    parser.add_argument('--collector-cpu', type=int, required=True)
    parser.add_argument('--include-multicacheline', action='store_true',
                        help='also run the historical multi-cacheline payloads')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if len(args.cpus) != 64 or len(set(args.cpus)) != 64 or args.collector_cpu in args.cpus:
        raise ValueError('provide 64 distinct worker CPUs and a separate collector CPU')
    output = args.output.resolve()
    plan = commands(output, args.cpus, args.collector_cpu, args.include_multicacheline)
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if (ROOT != Path('/root/host_fs/kdlock') or os.geteuid() != 0 or
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or
            not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise ValueError('run inside the guest after confirming a recovery snapshot')
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError('use a fresh output directory outside the checkout')
    sys.path.insert(0, str(ROOT / 'bench/rwlock_compare'))
    import run as rwlock_runner
    rwlock_runner.idle()
    output.mkdir(parents=True)
    write_json(output / 'matrix-plan.json', plan)
    status = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                  threads=THREADS, worker_cpus=args.cpus, collector_cpu=args.collector_cpu,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                  expected_sessions=sum(p['expected_sessions'] for p in plan),
                  state='RUNNING', groups=[])
    write_json(output / 'matrix-status.json', status)
    for group in plan:
        if (output / 'STOP').exists():
            status['state'] = 'STOPPED'
            break
        rwlock_runner.idle()
        print(f"START {group['name']}: {group['expected_sessions']} sessions", flush=True)
        entry = dict(name=group['name'], started_utc=datetime.now(timezone.utc).isoformat())
        status['groups'].append(entry)
        write_json(output / 'matrix-status.json', status)
        try:
            with (output / (group['name'] + '.log')).open('w') as stream:
                process = subprocess.run(group['argv'], cwd=ROOT, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=7200)
            entry['exit_code'] = process.returncode
            rwlock_runner.idle()
            records = json.loads((output / group['name'] / 'records.json').read_text())
            entry['recorded_sessions'] = len(records)
            entry['executed_sessions'] = sum(r.get('execution_status') != 'NOT_RUN' for r in records)
            entry['drained_sessions'] = sum(r.get('drained') is True for r in records)
            entry['status_counts'] = {s: sum(r.get('execution_status') == s for r in records)
                                      for s in sorted({r.get('execution_status', 'UNKNOWN') for r in records})}
            entry['finished_utc'] = datetime.now(timezone.utc).isoformat()
            if (len(records) != group['expected_sessions'] or
                    entry['executed_sessions'] != group['expected_sessions'] or
                    entry['drained_sessions'] != group['expected_sessions']):
                raise RuntimeError('incomplete or undrained group; inspect retained evidence')
            # A completed, drained NO_JIT rejection is retained and does not
            # prevent executing the remaining payloads. Unsafe failures stop.
            if process.returncode:
                failure = json.loads((output / group['name'] / 'failure.json').read_text())
                if failure.get('status') != 'NO_JIT':
                    raise RuntimeError('runner failed outside the drained NO_JIT case')
            print(f"END {group['name']}: {entry['status_counts']}", flush=True)
            write_json(output / 'matrix-status.json', status)
        except Exception as error:
            entry['error'] = str(error)
            status['state'] = 'FAILED'
            write_json(output / 'matrix-status.json', status)
            raise
    else:
        rwlock_runner.idle()
        status['state'] = 'COMPLETE'
    status['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(output / 'matrix-status.json', status)
    return 0 if status['state'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
