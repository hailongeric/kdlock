#!/usr/bin/env python3
"""Replay frozen rwlock cases with strict checks and an isolated diagnostic.

The diagnostic changes only the provider. The remaining-case mode reuses every
original binary. A drained NO_JIT remains a failed case; it does not prevent
collecting other predeclared cases. Any other error stops the sequence. Neither
mode changes admission thresholds, ownership, ACK, retirement or JIT checks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/'
                'nano-list-followup-20261020/timing-1/rwlock-w20')
BOOT = 'b65f0205-c8f9-4385-8b13-039cbce243a6'
FIELD_DIR = ROOT/'tests/kernel/rwlock_admission'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_inputs():
    """Bind all reused code and binaries to their original retained manifests."""
    committed = read(ORIGINAL.parent/'committed-source.json')
    assert committed['commit'] == 'f48b90e42e1538a5204d215b573a238ebd95f391'
    files = read(ORIGINAL/'source-sha256.json')
    assert files and all(committed['files'].get(p) == h for p, h in files.items())
    hashes = {ORIGINAL/'source'/p: h for p, h in files.items()}
    prepared = read(ORIGINAL/'build/provider/manifest.json')
    assert prepared['complete'] is True
    hashes.update({ORIGINAL/'build/provider'/p: h for p, h in prepared['prepared'].items()})
    hashes.update({Path(p): h for p, h in read(ORIGINAL/'binary-sha256.json').items()})
    for path, expected in hashes.items():
        assert digest(path) == expected, path
    return hashes


def selection(mode):
    original = read(ORIGINAL/'plan.json')
    assert len(original) == 72
    expected = ['list-n16-native-w020-t08-r00', 'list-n16-tclock-w020-t08-r00',
                'list-n16-kdlock-w020-t08-r00']
    assert [s['name'] for s in original[:3]] == expected
    assert [read(ORIGINAL/n/'session.json')['execution_status'] for n in expected] == [
        'OK', 'OK', 'NO_JIT']
    if mode == 'remaining':
        assert all(not (ORIGINAL/s['name']).exists() for s in original[3:])
        return [dict(s, diagnostic_provider=False, original_name=s['name']) for s in original[3:]]
    selected = []
    # Six fixed matched pairs. Rotate provider order, never retry for JIT.
    for threads in (8, 60):
        for repeat in range(3):
            case = next(s for s in original if s['variant'] == 'list-n16-kdlock' and
                        s['threads'] == threads and s['repeat'] == repeat)
            for diagnostic in ((False, True) if repeat % 2 == 0 else (True, False)):
                label = 'diagnostic' if diagnostic else 'original'
                selected.append(dict(case, name=label+'-'+case['name'],
                                     original_name=case['name'], diagnostic_provider=diagnostic))
    assert len(selected) == 12
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run'))
    parser.add_argument('--mode', choices=('diagnostic', 'remaining'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path)
    args = parser.parse_args()
    assert ROOT == Path('/root/host_fs/kdlock') and Path.cwd() == ROOT
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert sys.executable == shutil.which('python3') == \
        '/root/kdlock-translation-venv-20261019/bin/python3'
    packages = {n: importlib.metadata.version(n) for n in ('miasm', 'future', 'pyparsing', 'pyelftools')}
    assert packages == dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27')
    out = args.output.resolve()
    assert not out.is_relative_to(ROOT) and not ROOT.is_relative_to(out)
    assert not out.is_relative_to(ORIGINAL.parent) and not ORIGINAL.is_relative_to(out)
    hashes = frozen_inputs()
    source = ORIGINAL/'source'
    # Import only the verified retained collector and its helper modules.
    sys.path[:0] = [str(source/'bench/rwlock_compare'), str(source/'bench/tclock_compare'),
                    str(source/'bench/spin_cacheline'), str(source/'tests/protocols')]
    collector = load('frozen_rwlock_runner', source/'bench/rwlock_compare/run.py')
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](out, rt.idle)
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and '/kdlock-evidence/' in path:
            assert Path(path).resolve().is_relative_to(source), (name, path)
    plan = selection(args.mode)
    write = archive['save']
    binaries = dict(kdlock=ORIGINAL/'build/provider/kernel_module/kdlock_km.ko',
                    guard=ORIGINAL/'build/guard/tc_allocator_guard.ko',
                    daemon=source/'daemon/daemon',
                    tclock=ORIGINAL/'build/tclock/tclock_rwlock_backend_km.ko',
                    workloads={s['variant']: ORIGINAL/'build'/s['variant']/'rwlock_bench.ko' for s in plan})

    if args.action == 'prepare':
        assert not out.exists()
        out.mkdir(parents=True)
        (out/'source').symlink_to(source, target_is_directory=True)
        write(out/'plan.json', plan)
        write(out/'reused-inputs.json', {str(p): h for p, h in hashes.items()})
        write(out/'environment-prepare.json', dict(boot_id=BOOT, packages=packages,
              original=str(ORIGINAL), mode=args.mode, scope='Preparation; no measurements'))
        inputs = out/'diagnostic-inputs'
        inputs.mkdir()
        shutil.copyfile(Path(__file__), inputs/'admission.py')
        shutil.copyfile(ROOT/'bench/archive_run.py', inputs/'archive_run.py')
        if args.mode == 'diagnostic':
            for path in FIELD_DIR.iterdir():
                if path.is_file():
                    shutil.copyfile(path, inputs/path.name)
            provider = out/'provider'
            manifest = read(ORIGINAL/'build/provider/manifest.json')
            for relative in manifest['prepared']:
                target = provider/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ORIGINAL/'build/provider'/relative, target)
            for name, relative in [('kd_admission.c', 'kernel_module/kd_admission.c'),
                                   ('kd_admission.h', 'include/kd_admission.h'),
                                   ('fields.def', 'include/kd_admission_fields.def')]:
                shutil.copyfile(inputs/name, provider/relative)
            rt.command(['patch', '--batch', '--forward', '--fuzz=0', '--no-backup-if-mismatch',
                        '-p1', '-i', inputs/'observation.patch'], out/'apply-overlay.log',
                       timeout=30, cwd=provider)
            prepared = {str(p.relative_to(provider)): digest(p) for p in provider.rglob('*') if p.is_file()}
            write(out/'diagnostic-source.json', prepared)
            rt.command(['make', '-C', provider/'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2',
                        'W=1', 'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024',
                        'UBSAN_SANITIZE=n'], out/'build-provider.log', timeout=180)
            module = provider/'kernel_module/kdlock_km.ko'
            for field, expected in [('spin_numa', '1'), ('spin_batch', '1024'), ('mutex_batch', '1024')]:
                assert rt.command(['modinfo', '-F', field, module], out/(field+'.txt')).strip() == expected
            imports = rt.command(['nm', '-u', module], out/'provider-imports.txt')
            assert '__ubsan_' not in imports
            rt.command(['readelf', '-SW', module], out/'provider-sections.txt')
            assert all(digest(provider/p) == h for p, h in prepared.items())
            hashes.update({provider/p: h for p, h in prepared.items()})
            hashes[module] = digest(module)
        hashes.update({p: digest(p) for p in inputs.iterdir()})
        hashes[Path(__file__)] = digest(Path(__file__))
        hashes[ROOT/'bench/archive_run.py'] = digest(ROOT/'bench/archive_run.py')
        write(out/'immutable-inputs.json', {str(p): h for p, h in hashes.items()})
        assert all(digest(p) == h for p, h in hashes.items())
        archive['idle'](out, rt.idle)
        write(out/'prepared.json', dict(complete=True, mode=args.mode, cases=len(plan), boot_id=BOOT))
        print('PREPARED '+str(out), flush=True)
        return 0

    assert read(out/'prepared.json') == dict(complete=True, mode=args.mode, cases=len(plan), boot_id=BOOT)
    assert read(out/'plan.json') == plan and not (out/'run.json').exists()
    immutable = read(out/'immutable-inputs.json')
    assert all(digest(Path(p)) == h for p, h in immutable.items())
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1' and args.host_state
    host = read(args.host_state)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    assert 0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed']
    assert host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG']
    # Keep the existing strict host gate. The diagnostic never authorizes a
    # performance pass for a differing endpoint.
    old_host = read(ORIGINAL.parent/'host-before.json')
    old_qemu, new_qemu = old_host['qemu'][0], host['qemu'][0]
    assert old_qemu['pid'] == new_qemu['pid'] == 257489
    assert old_qemu['args'] == new_qemu['args']
    assert sorted(old_qemu['tasks'], key=lambda t: t['tid']) == \
        sorted(new_qemu['tasks'], key=lambda t: t['tid'])
    assert len(new_qemu['tasks']) == 67
    assert old_host['cpufreq'] == host['cpufreq'] and old_host['numa'] == host['numa']
    shutil.copyfile(args.host_state, out/'host-before.json')
    kernel_args = argparse.Namespace(kernel_source=Path('/root/linux-6.1.159-kdclobber2'),
                                    kernel_baseline=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))
    collector.kernel_identity.capture(kernel_args, out, rt.command)
    collector.boot_policy.capture(kernel_args.kernel_source, out, rt.command)
    assert 'nokaslr' in Path('/proc/cmdline').read_text().split()
    assert '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text()
    topology = rt.capture_topology(list(range(60))+[63])
    assert topology['role_nodes'] == [0]*32+[1]*29
    write(out/'topology.json', topology)
    fields = [line.split('(')[1].split(')')[0] for line in
              (out/'diagnostic-inputs/fields.def').read_text().splitlines()
              if line.startswith('KD_ADMISSION_FIELD(')] if args.mode == 'diagnostic' else []

    class ObservedSession(collector.RWSession):
        def admission(self, label):
            values = {}
            if self.record['diagnostic_provider']:
                for field in fields:
                    text = (Path('/sys/module/kdlock_km/parameters')/('admission_'+field)).read_text()
                    values[field] = {cpu: int(value) for cpu, value in
                                     (item.split(':') for item in text.split())}
                    rt.require(set(values[field]) == {str(i) for i in range(64)},
                               'diagnostic CPU identities differ')
            write(self.path/(label+'.admission.json'), values)
            return values

        def phase(self, label, spec):
            before = self.admission(label+'-before')
            result = super().phase(label, spec)
            after = self.admission(label+'-after')
            # Both reads occur outside worker execution; min/max are lifetime
            # extrema, while all other fields are monotonic event counts.
            delta = {k: {cpu: v-before[k][cpu] for cpu, v in row.items()}
                     for k, row in after.items() if k not in ('cpu_entries_min', 'cpu_entries_max')}
            rt.require(all(v >= 0 for row in delta.values() for v in row.values()),
                       'diagnostic event counter moved backward')
            for cpu in (str(i) for i in range(64)) if delta else ():
                def count(name):
                    return delta[name][cpu]
                rt.require(count('lock_record') == sum(count(k) for k in
                           ('lock_busy', 'lock_cpu_cold', 'lock_missing', 'lock_cold', 'lock_hot')),
                           'incomplete per-lock admission classification')
                rt.require(count('root_entries') == sum(count(k) for k in
                           ('root_disabled', 'root_heat_refuse', 'root_context_refuse',
                            'root_occupied_refuse', 'root_fast', 'root_contended')),
                           'incomplete clobber-entry admission classification')
                rt.require(count('queue_checks') == sum(count(k) for k in
                           ('queue_unheld', 'queue_missing_tail', 'queue_short',
                            'queue_missing_link', 'queue_pass')),
                           'incomplete native queue-prefix classification')
                if 'combiner_calls' in delta:
                    rt.require(count('combiner_calls') == sum(count(k) for k in
                               ('combiner_missing_next', 'combiner_native_current',
                                'combiner_native_next', 'combiner_source_refused',
                                'combiner_admitted')),
                               'incomplete initial combiner classification')
            self.record.setdefault('admission', {})[label] = dict(before=before, after=after, delta=delta)
            self.save()
            return result

    result = dict(mode=args.mode, boot_id=BOOT, passed=False, complete=False, cases=[],
                  scope='Diagnostic observations, including measured overhead' if args.mode == 'diagnostic'
                  else 'Previously unstarted original cases; strict failures retained')
    write(out/'run.json', result)
    for index, spec in enumerate(plan):
        assert all(digest(Path(p)) == h for p, h in immutable.items())
        archive['idle'](out, rt.idle)
        print(f'START {index+1}/{len(plan)} {spec["name"]}', flush=True)
        selected = dict(binaries)
        if spec['diagnostic_provider']:
            selected['kdlock'] = out/'provider/kernel_module/kdlock_km.ko'
        session = ObservedSession(out, spec, selected)
        error = None
        try:
            session.execute()
        except rt.Failure as failure:
            error = str(failure)
            if (failure.status != 'NO_JIT' or failure.unsafe or not session.record['drained'] or
                    session.record.get('cleanup_error') or
                    session.record.get('retired') != dict(state=2, modules=0, writers=0, frames=0)):
                result['fatal_error'] = repr(failure)
                write(out/'run.json', result)
                raise
        archive['idle'](out, rt.idle)
        row = dict(name=spec['name'], status=session.record['execution_status'],
                   drained=session.record['drained'], error=error)
        result['cases'].append(row)
        write(out/'run.json', result)
        print('FINISH '+json.dumps(row, sort_keys=True), flush=True)
    assert all(digest(Path(p)) == h for p, h in immutable.items())
    archive['idle'](out, rt.idle)
    result.update(complete=True, final_idle=True, passed=all(c['status'] == 'OK' for c in result['cases']))
    write(out/'run.json', result)
    write(out/'health.json', dict(idle=True, boot_id=BOOT, cases=result['cases'],
                                 immutable_hashes_checked=len(immutable)))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
