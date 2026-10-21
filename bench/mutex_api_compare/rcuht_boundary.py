#!/usr/bin/env python3
"""Two-worker RCUHT boundary-counter diagnostic on the retained collector.

Four stable snapshots distinguish original warmup, inter-phase gap and measure.
No provider or workload changes; all classes survive and no rate is accepted.
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
if ROOT.exists(): sys.path.insert(0,str(ROOT/'bench/mutex_api_compare'))
ORIGINAL_BOOT = 'b65f0205-c8f9-4385-8b13-039cbce243a6'
BUILD_ID = '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def bounds(before,after,work,label):
    workers=work['workers']
    require(len(workers)==2 and [w['cpu'] for w in workers]==[0,1] and
            before['finished_ns'] <= work['started_ns'] <= min(w['finished_ns'] for w in workers) and
            max(w['finished_ns'] for w in workers) <= work['finished_ns'] <= after['started_ns'],
            'capture overlaps or reverses joined phase')
    if label=='measure':
        require(all(work['started_ns'] <= w['active_started_ns'] < work['deadline_ns'] <=
                    w['kernel_finished_ns'] <= w['finished_ns'] for w in workers),
                'measured worker bounds differ')
    else:
        require(work['completed']==96000 and all(w['completed']==48000 for w in workers),
                'original fixed warmup differs')


def selected_plan(order, arm=None):
    plan = [row for row in order if row[:3] == ('rcuht', 2, 0) and
            row[3] in ('baseline-kd', 'public-kd')]
    require(plan == [('rcuht', 2, 0, 'baseline-kd'), ('rcuht', 2, 0, 'public-kd')],
            'fixed original diagnostic order differs')
    require(arm in (None, 'baseline-kd', 'public-kd'), 'invalid diagnostic arm')
    return plan if arm is None else [row for row in plan if row[3] == arm]


def endpoint_link(endpoint, controller, host, result_hash, host_hash, result_path):
    require(endpoint['checked'] and endpoint['immediate'] and controller['passed'] and
        controller['guest_returncode']==controller['host_returncode']==controller['result_fetch_returncode']==0 and
        controller['guest_result_path']==result_path and
        endpoint['result_sha256']==controller['guest_result_sha256']==result_hash and
        endpoint['host_sha256']==controller['host_sha256']==host_hash and
        host['pins_verified'] and host['snapshot_listed'], 'endpoint/result/controller binding differs')
    end=controller['guest_exit_observed_monotonic_ns']
    start=controller['host_capture_started_monotonic_ns']
    require(0 <= start-end < 1_000_000_000 and
        start <= controller['host_capture_finished_monotonic_ns'], 'endpoint was not immediate after guest exit')


def predecessor_identity(previous, expected, records):
    require(previous['passed'] and previous['state']=='COMPLETE' and previous['final_idle'] and
        previous['sessions']==1 and previous['order']==[['rcuht',2,0,'baseline-kd']] and
        all(previous[key]==value for key,value in expected.items()), 'OUTER diagnostic identity differs')
    require(len(records)==1 and records[0]['drained'] and
        records[0]['execution_status'] in ('OK','NO_JIT') and
        records[0]['comparison_arm']=='baseline-kd', 'OUTER session did not complete and drain')


def observed_session(base, route, Failure):
    class Observed(base):
        observer=None
        def phase(self,label,iterations,*,spec=None):
            if label not in ('warmup','measure'):
                return super().phase(label,iterations,spec=spec)
            try:
                if self.observer is None:
                    self.observer=route.Snapshot(self.path.parent/'binaries/kdlock_km.ko')
                    self.boundaries={}
                    self.binding=self.observer.receipt()
                    self.observed_kallsyms=self.observer.kallsyms
                require(label not in self.boundaries,'duplicate observed phase')
                before=self.observer.capture()
                self.boundaries[label]=dict(before=before,complete=False)
                work=super().phase(label,iterations,spec=spec)
                after=self.observer.capture()
                self.boundaries[label].update(after=after,completed=work['completed'])
                bounds(before,after,work,label)
                delta=route.difference(before,after)
                delta['scope']='Joined '+label+' only; stable reads outside workers'
                # Private memory prevents repeated receipt I/O before measure.
                self.boundaries[label].update(delta=delta,complete=True)
                return work
            except BaseException as error:
                raise Failure('UNDRAINED','boundary observation failed: '+repr(error),unsafe=True) from error

        def measure(self):
            super().measure()
            try:
                require(set(self.boundaries)=={'warmup','measure'},'four snapshots required')
                measured=self.boundaries['measure']['delta']['counters']
                require(measured['kd_bench_bodies']==self.record['jit_bodies'],
                        'measured entry witness disagrees with frozen collector')
                gap=route.difference(self.boundaries['warmup']['after'],self.boundaries['measure']['before'])
                gap['scope']='Between joined warmup and measurement; not either worker phase'
                self.gap=gap
            except BaseException as error:
                raise Failure('UNDRAINED','boundary accounting failed: '+repr(error),unsafe=True) from error

        def execute(self):
            try:
                return super().execute()
            finally:
                # Preserve partial observations even on unsafe failures. Closing
                # the read-only observer does not release any KD ownership.
                pending=sys.exc_info()[0] is not None
                try:
                    if self.observer is not None:
                        self.observer.close();self.observer=None
                    if hasattr(self,'boundaries'):
                        self.record['boundary_diagnostic']=dict(phases=self.boundaries,
                            gap=getattr(self,'gap',None),binding=self.binding,
                            diagnostic=True,score_eligible=False,
                            witness='ENTRY_ONLY; completion probe disabled',
                            limits='Boundary reads change preparation history; zero combiner is not admission refusal')
                        (self.path/'boundary-kallsyms').write_text(self.observed_kallsyms)
                        self.save()
                except BaseException:
                    if not pending: raise

    return Observed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--host-state', type=Path, required=True)
    p.add_argument('--transition', type=Path, required=True)
    p.add_argument('--transition-sha256', required=True)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--arm', choices=('baseline-kd', 'public-kd'),
                   help='one session per process, with fresh admission and an external immediate endpoint')
    p.add_argument('--predecessor', type=Path,
                   help='completed OUTER directory with its original checked endpoint; required for single DIRECT')
    a = p.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == 'before-mutex-kdonly-20261017T140354Z',
            'confirmed original recovery VM required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/rcuht_boundary.py'),
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
    shutil.copyfile(__file__, out/'rcuht_boundary.py')
    shutil.copyfile(a.transition, out/'transition.json')
    shutil.copyfile(scheduler_path, out/'scheduler.py')
    for name in ('route_snapshot.py','recovery_replay.py'):
        shutil.copyfile(ROOT/'bench/mutex_api_compare'/name,out/name)
    # Import only the retained new copy, outside the mutable checkout. The
    # original collector's module-origin guard remains fully enabled.
    compare_environment=load_module(out/'recovery_replay.py','rcuht_recovery').compare_environment
    plan = selected_plan(scheduler.execution_order(), a.arm)
    predecessor = None
    if a.arm == 'public-kd':
        require(a.predecessor is not None, 'single DIRECT requires completed OUTER and endpoint')
        a.predecessor=a.predecessor.resolve(strict=True)
        require(not out.is_relative_to(a.predecessor) and not a.predecessor.is_relative_to(out),
                'new output must be separate from predecessor')
        previous = scheduler.load(a.predecessor/'result.json')
        records = scheduler.load(a.predecessor/'matrix/records.json')
        expected=dict(driver_sha256=sha(Path(__file__)),scheduler_sha256=sha(scheduler_path),
            route_snapshot_sha256=sha(out/'route_snapshot.py'),
            recovery_driver_sha256=sha(out/'recovery_replay.py'),
            transition_sha256=a.transition_sha256,original_inputs=str(prepared))
        predecessor_identity(previous,expected,records)
        endpoint = scheduler.load(a.predecessor/'endpoint.json')
        controller = scheduler.load(a.predecessor/'controller.json')
        host_endpoint = scheduler.load(a.predecessor/'host-endpoint.json')
        require(endpoint['controller_sha256']==sha(a.predecessor/'controller.json'),
                'endpoint controller receipt changed')
        endpoint_link(endpoint, controller, host_endpoint, sha(a.predecessor/'result.json'),
                      sha(a.predecessor/'host-endpoint.json'), str(a.predecessor/'result.json'))
        require(previous['passed'] and previous['final_idle'] and previous['sessions'] == 1 and
                previous['order'] == [['rcuht', 2, 0, 'baseline-kd']] and
                previous['transition_sha256'] == a.transition_sha256 and
                previous['original_inputs'] == str(prepared) and
                endpoint['checked'] and endpoint['immediate'] and
                endpoint['result_sha256'] == sha(a.predecessor/'result.json') and
                endpoint['host_sha256'] == sha(a.predecessor/'host-endpoint.json'),
                'OUTER predecessor or original endpoint differs')
        # Re-evaluate the preserved endpoint, never trust its pass label alone.
        try:
            compare_environment(scheduler.same_environment, transition,
                scheduler.load(prepared/'matrix/host-state.json'), host_endpoint,
                scheduler.load(prepared/'matrix/environment.json'),
                scheduler.load(a.predecessor/'matrix/environment.json'),
                scheduler.load(prepared/'matrix/topology.json'),
                scheduler.load(a.predecessor/'matrix/topology.json'))
        except ValueError as error:
            require(endpoint['passed'] is False and endpoint.get('error')==repr(error),
                    'original rejected endpoint was relabelled')
        else:
            require(endpoint['passed'] is True, 'original passing endpoint was relabelled')
        # A completed rejected observation remains rejected. The next distinct
        # diagnostic arm may run only through its own fresh full admission;
        # it never replaces or retroactively accepts this predecessor.
        predecessor = {str(a.predecessor/name): sha(a.predecessor/name)
                       for name in ('result.json', 'endpoint.json', 'host-endpoint.json', 'controller.json',
                                    'matrix/environment.json','matrix/topology.json','matrix/records.json','matrix/plan.json')}
        previous_plan=scheduler.load(a.predecessor/'matrix/plan.json')
        require(len(previous_plan)==1,'OUTER plan differs')
        session_path=Path(previous_plan[0]['evidence_path'])/'session.json'
        require(session_path.resolve().is_relative_to(a.predecessor) and
                scheduler.load(session_path)==records[0], 'OUTER session receipt differs')
        predecessor[str(session_path)]=sha(session_path)
    else:
        require(a.predecessor is None, 'predecessor is only valid for single DIRECT')
    original_compare = scheduler.same_environment
    scheduler.same_environment = lambda *args: compare_environment(
        original_compare, transition, *args)
    scheduler.replay_order = lambda: plan
    original_specification=scheduler.specification
    def specification(*args,**kwargs):
        row=original_specification(*args,**kwargs)
        row.update(name=row['name']+'-boundary-diagnostic',diagnostic=True,score_eligible=False)
        return row
    scheduler.specification=specification
    receipt = dict(passed=False, accepted=False, state='PREPARATION',
                   source_commit=a.source_commit, driver_sha256=sha(Path(__file__)),
                   scheduler_sha256=sha(scheduler_path),
                   route_snapshot_sha256=sha(out/'route_snapshot.py'),
                   recovery_driver_sha256=sha(out/'recovery_replay.py'),
                   transition_sha256=a.transition_sha256,
                   measured_collection='d21a1e3', outer_revision='752fec1',
                   planned=len(plan), order=plan, original_inputs=str(prepared),
                   single_arm=a.arm, predecessor=predecessor,
                   predecessor_endpoint_passed=endpoint['passed'] if predecessor else None,
                   instrumentation='JOINED_BOUNDARY_EXISTING_COUNTERS', same_boot=False,
                   p95_status='DEFERRED', seven_mutex_causes='UNRESOLVED',
                   scope='New recovery boot; original immutable benchmark inputs. '
                         'Four boundary reads per session; no throughput or causal acceptance.')
    save(out/'result.json', receipt)
    try:
        for inputs in frozen.values():
            scheduler.verify(inputs['files'])
        route = load_module(out/'route_snapshot.py','rcuht_route')
        syn.BackendSession = observed_session(syn.BackendSession, route, bench_session.Failure)
        receipt['state'] = 'RUNNING'
        save(out/'result.json', receipt)
        result = scheduler.measure(prepared, out/'matrix', syn, syn_session,
            bench_session, api, 600, False, a.host_state, replay=True)
        records = scheduler.load(out/'matrix/records.json')
        require(result == 0 and len(records) == len(plan) and all(
            r['drained'] and r['execution_status'] in ('OK', 'NO_JIT') for r in records),
            'selected sessions failed or did not drain')
        syn.idle()
        for inputs in frozen.values():
            scheduler.verify(inputs['files'])
        scheduler.verify(harness)
        for name,key in (('route_snapshot.py','route_snapshot_sha256'),('recovery_replay.py','recovery_driver_sha256')):
            require(sha(out/name)==sha(ROOT/'bench/mutex_api_compare'/name)==receipt[key],
                    'diagnostic helper changed: '+name)
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
                transition['new_boot_id'], 'boot changed during collection')
        receipt.update(state='COMPLETE', passed=True, sessions=len(plan), final_idle=True,
                       finished_utc=scheduler.utc(), endpoint='PENDING')
    except BaseException as error:
        receipt.update(state='FAILED', error=repr(error))
        raise
    finally:
        save(out/'result.json', receipt)


if __name__ == '__main__':
    main()
