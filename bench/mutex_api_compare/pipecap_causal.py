#!/usr/bin/env python3
"""Fixed five-worker pipecap diagnosis using unchanged original measured binaries.

Four separate modes expose counter-capture, perf and inclusive-clock observer
effects. Original oracles, admission, publication and retirement remain in the
retained collector. This is an investigation, not an acceptance benchmark.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
MODES = ('plain', 'counts', 'profile', 'timing')
EXPECTED_BOOT = 'b65f0205-c8f9-4385-8b13-039cbce243a6'
PERF = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf')
PERF_SHA = 'be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def order(original):
    rounds = {}
    for group, count, repeat, arm in original:
        if (group, count) == ('pipecap', 5):
            rounds.setdefault(repeat, []).append(arm)
    require(set(rounds) == {0,1,2} and all(len(v) == len(set(v)) == 4 for v in rounds.values()),
            'three complete original four-arm rotations required')
    # The retained scheduler consumes a numeric repeat key. Its slot encodes
    # mode only for iteration; specification restores the real repeat and names.
    return [('pipecap', 5, r*len(MODES)+MODES.index(mode), arm)
            for r, arms in rounds.items()
            for mode in MODES[r % len(MODES):]+MODES[:r % len(MODES)]
            for arm in arms]


def specification(original_spec, args, kwargs, perf_hash):
    template, group, count, slot, arm, inputs, nodes = args
    repeat, index = divmod(slot, len(MODES))
    mode = MODES[index]
    spec = original_spec(template, group, count, repeat, arm, inputs, nodes, **kwargs)
    return dict(spec, name=spec['name']+'-'+mode, diagnostic=True,
                score_eligible=False, causal_mode=mode,
                perf_record=mode == 'profile', perf_clock_id='mono' if mode == 'profile' else None,
                perf_binary_sha256=perf_hash if mode == 'profile' else None,
                route_snapshot=mode != 'plain' and arm.endswith('-kd'),
                inclusive_jit_timing=mode == 'timing' and arm.endswith('-kd'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == EXPECTED_BOOT and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == 'before-mutex-kdonly-20261017T140354Z',
            'same confirmed recovery VM required')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable, 'original translation environment required')
    require(re.fullmatch('[0-9a-f]{40}', args.source_commit) is not None and
            not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/pipecap_causal.py'),
            'committed, byte-matched external diagnostic driver required')
    prepared, out = args.prepared.resolve(strict=True), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT) and
            not out.is_relative_to(prepared) and not prepared.is_relative_to(out), 'new independent output required')
    scheduler = load(ROOT/'bench/mutex_api_compare/run.py', 'causal_scheduler')
    scheduler.replay_inputs(prepared, out)
    harness = scheduler.retained_harness(prepared)
    syn, syn_session, bench_session, api = scheduler.runners(prepared/'harness', harness)
    archive = load(ROOT/'bench/archive_run.py', 'causal_archive')
    archive.idle(out.parent, syn.idle)
    host = scheduler.load(args.host_state)
    expected = scheduler.load(prepared/'matrix/host-state.json')
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed'] and
            host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG'], 'fresh host/snapshot receipt required')
    require(sorted(host['qemu'][0]['tasks'],key=lambda t:t['tid']) ==
            sorted(expected['qemu'][0]['tasks'],key=lambda t:t['tid']) and len(host['qemu'][0]['tasks']) == 67,
            'strict original QEMU thread set differs')
    out.mkdir(parents=True)
    tool_names = ('pipecap_causal.py','route_snapshot.py','profile_replay.py','run.py')
    tools = out/'tools'; tools.mkdir()
    identities = {}
    for name in tool_names:
        source = ROOT/'bench/mutex_api_compare'/name
        shutil.copyfile(source,tools/name)
        require(sha(source) == sha(tools/name), 'tool changed during retention')
        identities[name] = sha(source)
    scheduler.save(out/'tool-sha256.json',identities)
    require(sha(PERF) == PERF_SHA,'retained perf identity differs')
    shutil.copyfile(PERF,tools/'perf');(tools/'perf').chmod(0o755)
    profile = load(tools/'profile_replay.py','causal_profile')
    snapshot = load(tools/'route_snapshot.py','causal_snapshot')
    original_order, original_spec = scheduler.replay_order, scheduler.specification
    plan = order(scheduler.execution_order())
    require(len(plan) == len(set(plan)) == 48, 'fixed 48-session plan required')
    scheduler.save(out/'diagnostic-plan.json',[dict(workload=g,threads=n,repeat=s//4,
        mode=MODES[s%4],arm=a) for g,n,s,a in plan])
    receipt = dict(state='RUNNING',planned=48,source_commit=args.source_commit,
        provider_collection='d21a1e3',outer='752fec1',source_tools=identities,
        perf_sha256=PERF_SHA,provider_and_workload_binaries_changed=False,
        accepted=False,started_ns=time.time_ns(),
        limits='Separate observer modes. Inclusive timings overlap; no acquisition-only latency or causal fix is presumed.')
    scheduler.save(out/'result.json',receipt)
    old_class = api.SyscallSession

    class ObservedSession(old_class):
        counter_reader = None

        def run(self, argv, log, **kwargs):
            if self.record['inclusive_jit_timing'] and str(argv[0]) == 'insmod' and Path(argv[1]).name == 'kdlock_km.ko':
                require(argv.count('jit_timing=0') == 1, 'unexpected original timing configuration')
                argv = ['jit_timing=1' if arg == 'jit_timing=0' else arg for arg in argv]
            return super().run(argv,log,**kwargs)

        def tell(self, action, *positional, **keywords):
            if action == 'warmup' and self.record['route_snapshot']:
                self.counter_reader = snapshot.Snapshot(self.out/'build/kdlock_km.ko')
                (self.path/'counter-kallsyms.txt').write_text(self.counter_reader.kallsyms)
                scheduler.save(self.path/'counter-layout.json',self.counter_reader.receipt())
            if action != 'measure':
                return super().tell(action,*positional,**keywords)
            recorder = profile.Profile(self,str(tools/'perf'),clock_id='mono') if self.record['causal_mode'] == 'profile' else None
            before = after = None
            try:
                if recorder:
                    try:
                        recorder.start()
                    except Exception as error:
                        raise api.Failure('PERF_START_FAILED',str(error)) from error
                before = self.counter_reader.capture() if self.counter_reader else None
                measured = super().tell(action,*positional,**keywords)
                after = self.counter_reader.capture() if self.counter_reader else None
                if before is not None:
                    delta = snapshot.difference(before,after)
                    require(before['timing_enabled'] == self.record['inclusive_jit_timing'], 'timing mode differs')
                    require(before['finished_ns'] <= min(w['started_ns'] for w in measured['workers']) and
                            after['started_ns'] >= max(w['finished_ns'] for w in measured['workers']),
                            'counter capture overlaps measured workers')
                    self.record['route_delta'] = delta
                    scheduler.save(self.path/'route-snapshots.json',dict(before=before,after=after,delta=delta))
                return measured
            finally:
                if before is not None and after is None:
                    scheduler.save(self.path/'route-snapshot-incomplete.json',dict(before=before,after=None))
                if recorder:
                    try:
                        recorder.finish()
                    except Exception as error:
                        raise api.Failure('PERF_STOP_OR_CAPTURE_FAILED',str(error),unsafe=True) from error

        def measure(self):
            super().measure()
            if self.record['route_snapshot']:
                delta=self.record['route_delta']['counters']
                require(delta['kd_bench_bodies'] == self.record['jit_bodies'] and
                        delta['kd_bench_completions'] == self.record['jit_completions'],
                        'original public counters disagree with raw observation')
                self.save()

        def execute(self):
            try:
                return super().execute()
            finally:
                if self.counter_reader:
                    self.counter_reader.close()

    scheduler.replay_order = lambda: plan
    scheduler.specification = lambda *a,**k: specification(original_spec,a,k,PERF_SHA)
    api.SyscallSession=ObservedSession
    try:
        result=scheduler.measure(prepared,out/'matrix',syn,syn_session,bench_session,api,
                                 2400,False,args.host_state,replay=True)
        require(result == 0,'fixed diagnostic plan did not complete')
        rows=scheduler.load(out/'matrix/records.json')
        require(len(rows)==48 and all(r['drained'] and r['execution_status'] in ('OK','NO_JIT') for r in rows),
                'diagnostic session failure or missing drain')
        for bundle in scheduler.load(prepared/'frozen-inputs.json').values():
            scheduler.verify(bundle['files'])
        scheduler.verify(harness)
        archive.idle(out.parent,syn.idle)
        receipt.update(state='COMPLETE',sessions=len(rows),final_idle=True)
    except BaseException as error:
        receipt.update(state='FAILED',error=repr(error))
        raise
    finally:
        api.SyscallSession=old_class
        scheduler.replay_order,scheduler.specification=original_order,original_spec
        receipt['finished_ns']=time.time_ns()
        scheduler.save(out/'result.json',receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
