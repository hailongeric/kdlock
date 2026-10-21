#!/usr/bin/env python3
"""Replay seven frozen points after an explicitly recorded recovery-kernel boot.

The original scheduler retains its strict default boot guard. This separate
driver binds one approved boot transition and compares every other original
environment field unchanged. No provider, collector, oracle or admission
predicate is replaced. Execute an exact external copy in the original VM.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path('/root/host_fs/kdlock')
ORIGINAL_BOOT = 'b65f0205-c8f9-4385-8b13-039cbce243a6'
BUILD_ID = '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
POINTS = frozenset({('c08', 3), ('c08', 4), ('c08', 5),
                    ('pipebytes', 3), ('pipebytes', 5), ('pipecap', 5), ('rcuht', 2)})


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def compare_environment(compare, transition, original_host, host, original_env,
                        environment, original_topology, topology):
    require(transition.get('passed') is True and
            transition.get('original_boot_id') == ORIGINAL_BOOT and
            original_env['boot_id'] == ORIGINAL_BOOT and
            transition.get('new_boot_id') == environment['boot_id'] and
            environment['boot_id'] != ORIGINAL_BOOT and
            transition.get('kernel_release') == '6.1.159-kdclobber2' and
            transition.get('kernel_build_id') == BUILD_ID and
            transition.get('recovery_preserved') is True,
            'verified exact recovery boot transition required')
    old_tasks = sorted(original_host['qemu'][0]['tasks'], key=lambda t: t['tid'])
    new_tasks = sorted(host['qemu'][0]['tasks'], key=lambda t: t['tid'])
    require(len(new_tasks) == 67 and new_tasks == old_tasks,
            'strict original QEMU thread identities or placement differ')
    # Only this comparison copy changes. Both real environment receipts keep
    # their actual boot IDs, and the transition is a separate measured cohort.
    comparison_base = dict(original_env, boot_id=environment['boot_id'])
    result = compare(original_host, host, comparison_base, environment,
                     original_topology, topology)
    result.update(original_boot_id=ORIGINAL_BOOT, new_boot_id=environment['boot_id'],
                  same_boot=False, transition_recorded=True,
                  scope='Same original kernel, QEMU identities, configuration, pins, '
                        'frequency policy, memory bindings, boot arguments, dependencies '
                        'and topology; separate explicitly recorded recovery boot. '
                        'Resident pages are recorded, not fixed.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--host-state', type=Path, required=True)
    p.add_argument('--transition', type=Path, required=True)
    p.add_argument('--transition-sha256', required=True)
    p.add_argument('--source-commit', required=True)
    a = p.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == 'before-mutex-kdonly-20261017T140354Z',
            'confirmed original recovery VM required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/recovery_replay.py'),
            'execute an exact external driver copy')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable, 'original pinned Python required')
    require(re.fullmatch('[0-9a-f]{40}', a.source_commit), 'concrete source commit required')
    require(sha(a.transition) == a.transition_sha256, 'transition receipt hash differs')
    transition = json.loads(a.transition.read_text())
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
            transition['new_boot_id'], 'current boot differs from transition')
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    require(len(modules) == 73 and modules == transition['modules'],
            'original runtime module set differs')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    scheduler_path = ROOT/'bench/mutex_api_compare/run.py'
    spec = importlib.util.spec_from_file_location('recovery_scheduler', scheduler_path)
    scheduler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scheduler)
    prepared, out = a.prepared.resolve(strict=True), a.output.resolve()
    require(not out.is_relative_to(ROOT), 'external output required')
    frozen = scheduler.replay_inputs(prepared, out)
    status = scheduler.load(prepared/'matrix/status.json')
    require(status['state'] == 'COMPLETE' and status['completed'] == 1764,
            'complete original comparison required')
    harness = scheduler.retained_harness(prepared)
    syn, syn_session, bench_session, api = scheduler.runners(prepared/'harness', harness)
    syn.idle()
    out.mkdir()
    shutil.copyfile(__file__, out/'recovery_replay.py')
    shutil.copyfile(a.transition, out/'transition.json')
    shutil.copyfile(scheduler_path, out/'scheduler.py')
    plan = [row for row in scheduler.execution_order() if row[:2] in POINTS]
    require(len(plan) == len(set(plan)) == 84, 'fixed seven-point plan differs')
    original_compare = scheduler.same_environment
    scheduler.same_environment = lambda *args: compare_environment(
        original_compare, transition, *args)
    scheduler.replay_order = lambda: plan
    receipt = dict(passed=False, accepted=False, state='PREPARATION',
                   source_commit=a.source_commit, driver_sha256=sha(Path(__file__)),
                   scheduler_sha256=sha(scheduler_path),
                   transition_sha256=a.transition_sha256,
                   measured_collection='d21a1e3', outer_revision='752fec1',
                   planned=84, order=plan, original_inputs=str(prepared),
                   instrumentation='ORIGINAL_PLAIN', same_boot=False,
                   scope='New recovery boot; original immutable benchmark inputs. '
                         'No candidate optimization or causal acceptance.')
    save(out/'result.json', receipt)
    try:
        for inputs in frozen.values():
            scheduler.verify(inputs['files'])
        receipt['state'] = 'RUNNING'
        save(out/'result.json', receipt)
        result = scheduler.measure(prepared, out/'matrix', syn, syn_session,
            bench_session, api, 2400, False, a.host_state, replay=True)
        records = scheduler.load(out/'matrix/records.json')
        require(result == 0 and len(records) == 84 and all(
            r['drained'] and r['execution_status'] in ('OK', 'NO_JIT') for r in records),
            'selected sessions failed or did not drain')
        syn.idle()
        for inputs in frozen.values():
            scheduler.verify(inputs['files'])
        scheduler.verify(harness)
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
                transition['new_boot_id'], 'boot changed during collection')
        receipt.update(state='COMPLETE', passed=True, sessions=84, final_idle=True)
    except BaseException as error:
        receipt.update(state='FAILED', error=repr(error))
        raise
    finally:
        save(out/'result.json', receipt)


if __name__ == '__main__':
    main()
