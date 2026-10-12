#!/usr/bin/env python3
"""Compare KD spin/blocking mutex policies across the maintained benchmark set.

Run only in the verified recovery VM. Existing runners retain all acceptance,
publication and drain checks. A STOP file stops between independently drained
groups. No automatic retry, force cleanup, snapshot restore or partial pooling.
"""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FULL_THREADS = [*range(1, 9), *range(12, 65, 4)]


def commands(out, threads, spin_limit, collector, cpus=None, paired=False):
    cpus = list(range(max(threads))) if cpus is None else cpus
    groups = []
    common = ['--threads', *map(str, threads), '--collector-cpu', str(collector),
              '--repeats', '3', '--duration-ms', '2000']
    # Match every payload exposed by the maintained complete-matrix driver.
    micro = [('mutex', 'cacheline', [1, 8, 16]), ('mutex', 'rcuht', []),
             ('spin', 'cacheline', [1, 8, 16]), ('spin', 'rcuht', []),
             ('rwlock', 'cacheline', [1, 2, 4, 8, 16]), ('rwlock', 'rcuht', [])]
    api = [('pipebytes', ['query'], [16, 128]), ('pipecap', ['query'], [16]),
           ('seek', ['set', 'end'], [16]), ('ofd', ['tail'], [16, 128]),
           ('setfd', ['toggle'], [16, 512]), ('utsname', ['host', 'domain'], [20])]
    for family, workload, sizes in micro:
        for mode in (('both',) if paired and family != 'rwlock' else ('spin', 'blocking')):
            name = f'{family}-{workload}-{mode}'
            runner = ('bench/rwlock_compare/run.py' if family == 'rwlock' else
                      'bench/tclock_compare/run_mutex.py' if family == 'mutex' else
                      'bench/tclock_compare/run.py')
            backends = ['native', 'tclock', 'kdlock'] if mode != 'blocking' else ['kdlock']
            argv = [sys.executable, runner, *common, '--backends', *backends,
                    '--mutex-wait-mode', mode, '--mutex-spin-limit', str(spin_limit),
                    '--output', str(out/name)]
            if family == 'rwlock':
                argv += ['--workloads', workload, '--write-percent', '1', '20',
                         '--cpus', *map(str, cpus)]
            else:
                argv += ['--workload', workload, '--keep-going-no-jit',
                         '--cpus', ','.join(map(str, cpus))]
            if sizes:
                argv += ['--cachelines', *map(str, sizes)]
            groups.append(dict(name=name, suite='micro', family=family, mode=mode,
                expected=len(threads)*3*(len(backends)+(mode == 'both'))*max(1, len(sizes))*(2 if family == 'rwlock' else 1), argv=argv))
    for kind, queries, entries in api:
        for mode in (('both',) if paired else ('spin', 'blocking')):
            name = f'api-{kind}-{mode}'
            backends = ['stock', 'native', 'tclock', 'kdlock'] if mode != 'blocking' else ['kdlock']
            argv = [sys.executable, 'bench/real_api/run.py', *common, '--backends', *backends,
                    '--kinds', kind, '--queries', *queries, '--entries', *map(str, entries),
                    '--mutex-wait-mode', mode, '--mutex-spin-limit', str(spin_limit),
                    '--cpus', ','.join(map(str, cpus)),
                    '--output', str(out/name)]
            groups.append(dict(name=name, suite='api', family=kind, mode=mode,
                expected=len(threads)*3*(len(backends)+(mode == 'both'))*len(queries)*len(entries), argv=argv))
    return groups


def write(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--threads', nargs='+', type=int, default=[1, 8, 16, 32, 48, 60])
    p.add_argument('--full-grid', action='store_true', help='1..8 and 12..64 in steps of four')
    p.add_argument('--cpus', nargs='+', type=int, help='ordered worker CPUs; each cohort takes a prefix')
    p.add_argument('--collector-cpu', type=int, default=63)
    p.add_argument('--paired-policies', action='store_true',
                   help='adjacent alternating KD policies for spin/mutex and real APIs; rwlock controls remain separate')
    p.add_argument('--mutex-spin-limit', type=int, default=4096)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    out = args.output.resolve()
    if args.full_grid:
        args.threads = FULL_THREADS
    cpus = args.cpus if args.cpus is not None else list(range(max(args.threads)))
    if not (args.threads and len(set(args.threads)) == len(args.threads) and
            1 <= min(args.threads) <= max(args.threads) <= 64 and
            len(cpus) >= max(args.threads) and len(set(cpus)) == len(cpus) and min(cpus) >= 0 and
            args.collector_cpu >= 0 and args.collector_cpu not in cpus[:max(args.threads)] and
            0 <= args.mutex_spin_limit <= 1048576):
        p.error('need distinct 1..64 worker counts, enough unique CPUs, separate collector, and bounded spin limit')
    plan = commands(out, args.threads, args.mutex_spin_limit, args.collector_cpu, cpus, args.paired_policies)
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if (ROOT != Path('/root/host_fs/kdlock') or os.geteuid() or
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise ValueError('confirmed recovery VM required')
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('use a new output directory outside the checkout')
    sys.path.insert(0, str(ROOT/'bench/rwlock_compare'))
    import run as rwlock_runner
    rwlock_runner.idle()
    out.mkdir(parents=True)
    write(out/'matrix-plan.json', plan)
    (out/'run.py').write_bytes(Path(__file__).read_bytes())
    approved = {}
    state = dict(state='RUNNING', started_utc=datetime.now(timezone.utc).isoformat(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], threads=args.threads,
        worker_cpus=cpus, paired_policies=args.paired_policies,
        collector_cpu=args.collector_cpu, mutex_spin_limit=args.mutex_spin_limit,
        expected_sessions=sum(g['expected'] for g in plan), groups=[])
    write(out/'matrix-status.json', state)
    for group in plan:
        if (out/'STOP').exists():
            state['state'] = 'STOPPED'
            break
        rwlock_runner.idle()
        for relative, expected in approved.items():
            if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != expected:
                raise ValueError('frozen source changed between groups: '+relative)
        print(f"GROUP {group['name']} ({group['expected']} sessions)", flush=True)
        record = dict(name=group['name'], started_utc=datetime.now(timezone.utc).isoformat())
        state['groups'].append(record)
        write(out/'matrix-status.json', state)
        try:
            with (out/(group['name']+'.log')).open('w') as log:
                result = subprocess.run(group['argv'], cwd=ROOT, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=10800)
        except subprocess.TimeoutExpired:
            # A killed runner does not establish that its workers drained.
            record['error'] = 'group exceeded three-hour timeout; drain unconfirmed'
            state['state'] = 'FAILED'
            break
        record.update(returncode=result.returncode, finished_utc=datetime.now(timezone.utc).isoformat())
        records_file = out/group['name']/'records.json'
        manifest_file = out/group['name']/'source-sha256.json'
        if manifest_file.exists():
            for relative, expected in json.loads(manifest_file.read_text()).items():
                if relative in approved and approved[relative] != expected:
                    raise ValueError('group source mismatch: '+relative)
                approved[relative] = expected
            write(out/'source-sha256-approved.json', approved)
        records = json.loads(records_file.read_text()) if records_file.exists() else []
        # A timed NO_JIT exclusion may finish safely, but is not an accepted
        # JIT measurement. Every other failure stops the matrix for diagnosis.
        complete = len(records) == group['expected'] and all(r.get('drained') and
            r.get('execution_status') in ('OK', 'NO_JIT') for r in records)
        record['complete'] = complete
        record['jit_exclusions'] = sum(r.get('execution_status') == 'NO_JIT' for r in records)
        write(out/'matrix-status.json', state)
        if not complete or (result.returncode and not record['jit_exclusions']):
            state['state'] = 'FAILED'
            break
        rwlock_runner.idle()
    else:
        state['state'] = 'COMPLETE'
    state['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write(out/'matrix-status.json', state)
    print(state['state'], flush=True)
    if state['state'] == 'FAILED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
