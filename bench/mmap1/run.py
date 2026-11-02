#!/usr/bin/env python3
"""Run unchanged pinned mmap1 binaries; builds and execution belong in the VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'bench/mmap_fault'))
import timing as common
rt, identity, platform = common.rt, common.kernel_identity, common.mm_platform
mm = common.module('mmap1_existing_mm_checks', ROOT/'bench/mmap_writer/linux70.py')
execution = common.module('mmap1_execution_session', ROOT/'bench/mmap1/execution_session.py')
REVISION = '75f66e45697e6f5f49c33dd950c4e6b289198f8f'
PINNED = {
    'main.c': '48d4640f151801fdfb5f3915c822cf280c713df3c1998068e16ce0c961cbf746',
    'Makefile': '9089726b38440a6466ebd0ea7561b3fd99ee263fea2485f974fbd91f4866d5a8',
    'tests/mmap1.c': 'a7e09c6a7a12524a2cd949e5d37cf8ec0ba2479868cbd04ebd8c83c4eaed9d06',
}
WORKERS = tuple(range(1, 9))+tuple(range(12, 61, 4))
MODELS = ('threads', 'processes')
DESCRIPTION = 'Anonymous memory mmap/munmap of 128MB'
SAMPLES, UPSTREAM_S, WARMUP_SAMPLES = 2, 2, 6


def load(path):
    return json.loads(Path(path).read_text())


def plan(model='both'):
    rt.require(model in (*MODELS, 'both'), 'unknown process model')
    return [dict(model=m, workers=n, round=0, nominal_seconds=2)
            for m in MODELS if model in (m, 'both') for n in WORKERS]


def argv(binary, workers):
    rt.require(type(workers) is int and workers in WORKERS, 'unplanned worker count')
    return [str(binary), '-t', str(workers), '-s', str(UPSTREAM_S), '-m']


def parse_output(text, workers):
    """Validate the pinned harness boundary and original integer average."""
    lines = text.splitlines()
    rt.require(len(lines) == 12 and lines[:2] == ['testcase:'+DESCRIPTION, 'warmup'] and
               lines[8] == 'measurement', 'truncated or unexpected upstream output')
    rows = []
    for line in lines[2:8]+lines[9:11]:
        match = re.fullmatch(r'min:(\d+) max:(\d+) total:(\d+)', line)
        rt.require(match is not None, 'invalid upstream sample')
        low, high, total = map(int, match.groups())
        rt.require(0 <= low <= high and total > 0 and workers*low <= total <= workers*high and
                   (workers != 1 or low == high == total), 'invalid per-worker progress')
        rows.append(dict(min=low, max=high, total=total))
    match = re.fullmatch(r'average:(\d+)', lines[-1])
    rt.require(match is not None, 'missing upstream average')
    rt.require(all(row['min'] > 0 for row in rows[WARMUP_SAMPLES:]),
               'a worker made no progress in a measured interval')
    total = sum(row['total'] for row in rows[WARMUP_SAMPLES:])
    raw = int(match[1])
    rt.require(raw == total//UPSTREAM_S, 'upstream average/interval conservation failed')
    return dict(warmup=rows[:WARMUP_SAMPLES], measurement=rows[WARMUP_SAMPLES:],
                completed_pairs=total, nominal_seconds=SAMPLES, pairs_per_nominal_second=total/SAMPLES,
                upstream_average=raw, upstream_average_divisor=UPSTREAM_S,
                upstream_counter_boundary='-s2: six pre-marker samples, two post-marker samples, integer average divides by2',
                elapsed_interval_seconds_observed=False)


def verified_files(files):
    rt.require(isinstance(files, dict) and bool(files), 'empty frozen file map')
    for name, expected in files.items():
        rt.require(isinstance(name, str) and Path(name).is_absolute() and
                   isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected),
                   'invalid frozen file entry')
        rt.require(rt.digest(Path(name)) == expected, 'frozen input changed: '+name)


def freeze_support(out):
    files = mm.platform.freeze_support(out)
    for directory in ('bench/mmap1', 'tests/kernel/mmap1_identity'):
        for source in sorted((ROOT/directory).rglob('*')):
            if not source.is_file() or source.suffix not in ('.py', '.md', '.c', '.h') and source.name != 'Makefile':
                continue
            target = out/'runtime-source'/source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files[str(source)] = files[str(target)] = rt.digest(target)
    rt.write_json(out/'runtime-source-sha256.json', files)
    return files


def guest(args):
    if args.kernel_variant != 'kdlock1':
        mm.platform.guest(args)
        return
    rt.require(args.mode == 'native', 'explicit backend and kernel variant differ')
    if args.kernel_source is None:
        args.kernel_source = Path('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build')
    if args.kernel_baseline is None:
        args.kernel_baseline = Path('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027')
    platform.guest(args.boot_id)


def admit(args, out):
    guest(args)
    host = common.host_check(args.host_state, out, True, args.boot_id,
                             reference=args.host_reference,
                             reference_sha256=args.host_reference_sha256)
    captured = identity.capture(args, out, rt.command)
    rt.require(captured.get('schema') == 2, 'Linux 7 schema-2 identity required')
    if args.kernel_variant == 'kdlock1':
        binding = platform.kernel_binding(captured, args.kernel_source, args.kernel_baseline,
                                          private_backing_locks=False)
    else:
        binding = mm.platform.binding(captured, args.kernel_source, args.kernel_baseline, args.mode,
                                      variant=args.kernel_variant)
    args.captured_runtime_policy = captured['runtime_policy']
    return dict(kernel_identity=captured, kernel_binding=binding, host_qualification=host)


def verify_boot(args):
    guest(args)
    rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
               'boot changed')
    policy = args.captured_runtime_policy
    rt.require(Path('/proc/cmdline').read_text().strip() == policy['cmdline'] and
               Path('/sys/kernel/debug/sched/preempt').read_text().strip() == policy['preempt_control'],
               'running command line/preemption policy changed')


def idle(*, allow_identity_probe=False):
    rt.idle()
    allowed = {'kd_mmap1_identity'} if allow_identity_probe else set()
    for entry in Path('/sys/module').iterdir():
        rt.require(entry.name in allowed or not entry.name.startswith(('kd_', 'jit_', 'tclock_', 'tc_')),
                   'experimental module remains loaded: '+entry.name)
        rt.require(entry.name not in ('real_api', 'rwlock_bench', 'rwlock_test', 'rwsem_probe'),
                   'workload remains loaded: '+entry.name)
    for entry in Path('/proc').glob('[0-9]*/comm'):
        try:
            name = entry.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        rt.require(name not in ('mmap1_threads', 'mmap1_processes'), 'existing mmap1 task')


def prepare(args, out):
    source = args.upstream.resolve()
    revision = rt.command(['git', '-C', source, 'rev-parse', 'HEAD'], out/'upstream-revision.log').strip()
    clean = rt.command(['git', '-C', source, 'status', '--porcelain=v1', '--untracked-files=all'],
                       out/'upstream-status.log')
    rt.require(revision == REVISION and not clean.strip(), 'clean pinned upstream checkout required')
    listing = rt.command(['git', '-C', source, 'ls-tree', '-r', '--full-tree', 'HEAD'], out/'upstream-tree.log')
    copied = out/'upstream'
    copied.mkdir()
    files, source_hashes = {}, {}
    for line in listing.splitlines():
        match = re.fullmatch(r'(100644|100755) blob ([0-9a-f]{40})\t([A-Za-z0-9_.+/-]+)', line)
        rt.require(match is not None, 'unsupported upstream tree entry')
        mode, blob, name = match.groups()
        rt.require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe upstream path')
        original = source/name
        rt.require(original.is_file() and not original.is_symlink(), 'nonregular upstream source')
        data = original.read_bytes()
        actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        rt.require(actual == blob, 'upstream worktree differs from pinned Git blob: '+name)
        target = copied/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(int(mode, 8) & 0o777)
        source_hashes[name] = files[str(target)] = hashlib.sha256(data).hexdigest()
    rt.require(all(source_hashes.get(name) == value for name, value in PINNED.items()),
               'pinned harness/testcase bytes differ')
    env = {key:os.environ[key] for key in ('HOME', 'TMPDIR') if key in os.environ}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    compiler = Path('/usr/bin/gcc').resolve()
    rt.command([compiler, '--version'], out/'compiler.log', env=env)
    rt.command(['/usr/bin/make', '--version'], out/'make.log', env=env)
    rt.command(['/usr/bin/ld', '--version'], out/'linker.log', env=env)
    rt.command(['/usr/bin/make', '-j2', 'CC='+str(compiler), 'mmap1_threads', 'mmap1_processes'],
               out/'build.log', cwd=copied, env=env, timeout=120)
    binaries, dependencies = {}, {str(compiler):rt.digest(compiler)}
    for tool in ('/usr/bin/make', '/usr/bin/ld'):
        dependencies[tool] = rt.digest(Path(tool))
    for model in MODELS:
        binary = copied/('mmap1_'+model)
        binaries[model] = str(binary)
        files[str(binary)] = rt.digest(binary)
        data = rt.command(['/usr/bin/ldd', binary], out/(model+'-ldd.log'), env=env)
        rt.require('not found' not in data, 'missing dynamic library')
        libraries = re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', data, re.M)
        rt.require(any('libhwloc' in name for name in libraries), 'libhwloc identity missing')
        for name in libraries:
            path = Path(name).resolve()
            dependencies[name] = dependencies[str(path)] = rt.digest(path)
    files.update(dependencies)
    for name, expected in source_hashes.items():
        rt.require(rt.digest(copied/name) == expected, 'build changed upstream source')
    result = dict(schema=1, upstream_revision=REVISION, source_sha256=source_hashes,
                  binaries=binaries, binary_sha256={m:rt.digest(Path(p)) for m,p in binaries.items()},
                  dependencies=dependencies, files=files, executable_modified=False)
    verified_files(files)
    rt.write_json(out/'inputs.json', result)
    return result


def inputs_from(path):
    data = load(path)
    rt.require(data.get('schema') == 1 and data.get('upstream_revision') == REVISION and
               data.get('executable_modified') is False and set(data.get('binaries', {})) == set(MODELS),
               'unsupported prepared mmap1 inputs')
    rt.require(all(data['source_sha256'].get(name) == value for name,value in PINNED.items()),
               'prepared upstream source differs')
    verified_files(data['files'])
    source_roots = {str(Path(name).parent) for name in data['binaries'].values()}
    rt.require(len(source_roots) == 1, 'prepared binaries have different source roots')
    source_root = Path(next(iter(source_roots)))
    rt.require(all(data['files'].get(str(source_root/name)) == digest
                   for name,digest in data['source_sha256'].items()), 'prepared source manifest is unbound')
    for model, name in data['binaries'].items():
        rt.require(Path(name).name == 'mmap1_'+model and data['files'].get(name) == data['binary_sha256'][model],
                   'binary model/digest binding differs')
    preparation = load(Path(path).parent/'result.json')
    rt.require(preparation.get('passed') is True and preparation.get('action') == 'prepare' and
               preparation.get('inputs_sha256') == rt.digest(Path(path)), 'successful exact preparation required')
    return data


def task_record(pid):
    base = Path('/proc')/str(pid)
    stat = (base/'stat').read_text()
    # The comm field can contain spaces and parentheses; fields after its final
    # close parenthesis start at field3. starttime is field22.
    fields = stat[stat.rfind(')')+2:].split()
    tgid = next(line.split()[1] for line in (base/'status').read_text().splitlines() if line.startswith('Tgid:'))
    return dict(tid=pid, tgid=int(tgid), start_ticks=int(fields[19]), ppid=int(fields[1]),
                cpus=sorted(os.sched_getaffinity(pid)), executable=str((base/'exe').resolve(strict=True)))


def validate_placement(rows, parent, model, workers, binary):
    rt.require(len(rows) == workers and len({r['tid'] for r in rows}) == workers,
               'wrong or duplicate worker count')
    rt.require(all(r['tid'] != parent and type(r['start_ticks']) is int and r['start_ticks'] > 0 and
                   r['executable'] == str(Path(binary).resolve()) for r in rows), 'worker lifetime/binary differs')
    rt.require(all(len(r['cpus']) == 1 for r in rows) and
               sorted(r['cpus'][0] for r in rows) == list(range(workers)),
               'upstream hwloc worker placement differs from CPU0..N-1')
    rt.require(all(r['tgid'] == (parent if model == 'threads' else r['tid']) for r in rows),
               'worker process/thread model differs')
    if model == 'processes':
        rt.require(all(r['ppid'] == parent for r in rows), 'worker parent differs')
    rt.require(os.sched_getaffinity(parent) == {63}, 'upstream collector affinity differs')


def capture_workers(parent, model, workers, binary):
    if model == 'threads':
        ids = sorted(int(p.name) for p in (Path('/proc')/str(parent)/'task').iterdir()
                     if int(p.name) != parent)
    else:
        ids = sorted(map(int, (Path('/proc')/str(parent)/'task'/str(parent)/'children').read_text().split()))
    rows = [task_record(pid) for pid in ids]
    validate_placement(rows, parent, model, workers, binary)
    rt.require(rows == [task_record(pid) for pid in ids], 'worker identity changed during warmup snapshot')
    return rows


def task_gone(row):
    try:
        stat = (Path('/proc')/str(row['tid'])/'stat').read_text()
        return int(stat[stat.rfind(')')+2:].split()[19]) != row['start_ticks']
    except (FileNotFoundError, ProcessLookupError):
        return True


def run_point(out, spec, inputs, verify, *, diagnostic=False, execution_session=None):
    """One normal upstream lifetime; observations end during its own warmup."""
    if execution_session is None:
        idle(allow_identity_probe=diagnostic)
    else:
        rt.require(isinstance(execution_session, execution.ExecutionSession),
                   'explicit verified execution-session contract required')
        execution_session.verify(allow_identity_probe=diagnostic)
    verify()
    out.mkdir()
    binary = inputs['binaries'][spec['model']]
    command = argv(binary, spec['workers'])
    result = dict(schema=1, **spec, passed=False, drained=False, scored=not diagnostic,
                  state='RUNNING', argv=command, executable_sha256=inputs['binary_sha256'][spec['model']],
                  application_lock_identity='not-observed-in-this-process', instrumentation='identity-kprobe' if diagnostic else 'none')
    if execution_session is not None:
        result['execution_session'] = execution_session.identity()
    rt.write_json(out/'result.json', result)
    fd = os.open('/dev/kmsg', os.O_RDONLY|os.O_NONBLOCK)
    os.lseek(fd, 0, os.SEEK_END)
    messages = ''
    child = None
    started = time.monotonic_ns()
    before_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        with (out/'upstream.log').open('w') as log:
            previous = os.sched_getaffinity(0)
            try:
                os.sched_setaffinity(0, {63})
                child = subprocess.Popen(command, cwd=Path(binary).parent, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True, env={'PATH':'/usr/bin:/bin', 'LC_ALL':'C',
                                                                     'HOME':os.environ.get('HOME', '/root')})
            finally:
                os.sched_setaffinity(0, previous)
            result.update(pid=child.pid, started_ns=started)
            rt.write_json(out/'command.json', dict(argv=command, pid=child.pid, started_ns=started,
                          timeout_seconds=30, cwd=str(Path(binary).parent)))
            # Six upstream one-second warmup samples precede measurement. Read
            # proc only within four seconds of launch, never in the timed tail.
            rows = None
            while time.monotonic_ns()-started < 4_000_000_000:
                if child.poll() is not None:
                    raise rt.Failure('WORKLOAD_FAILED', 'upstream exited before warmup observation')
                try:
                    rows = capture_workers(child.pid, spec['model'], spec['workers'], binary)
                    break
                except (rt.Failure, FileNotFoundError, ProcessLookupError):
                    time.sleep(0.05)
            rt.require(rows is not None, 'could not verify all upstream workers before measurement')
            result['workers_observed'] = rows
            result['observation_finished_ns'] = time.monotonic_ns()
            rt.require(result['observation_finished_ns']-started < 5_000_000_000,
                       'warmup placement observation exceeded its deadline')
            rt.write_json(out/'result.json', result)
            try:
                code = child.wait(timeout=max(1, 30-(time.monotonic_ns()-started)/1e9))
            except subprocess.TimeoutExpired as error:
                raise rt.Failure('TIMEOUT', 'mmap1 lifetime unknown; no cleanup attempted', unsafe=True) from error
        after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
        result.update(returncode=code, process_elapsed_ns=time.monotonic_ns()-started,
                      cpu_time_scope='whole upstream lifetime including warmup and reaped workers',
                      user_cpu_seconds=after_cpu.ru_utime-before_cpu.ru_utime,
                      system_cpu_seconds=after_cpu.ru_stime-before_cpu.ru_stime)
        rt.require(code == 0, 'upstream application failed')
        rt.require(all(task_gone(row) for row in rows), 'upstream worker survived normal shutdown')
        result['drained'] = True
        parsed = parse_output((out/'upstream.log').read_text(), spec['workers'])
        # A diagnostic receipt proves progress/shape, never contributes a score.
        result['output'] = parsed if not diagnostic else dict(output_valid=True, measured_samples=len(parsed['measurement']))
        verify()
        if execution_session is None:
            idle(allow_identity_probe=diagnostic)
        else:
            result['execution_session_after'] = execution_session.verify(allow_identity_probe=diagnostic)
        result.update(state='COMPLETE', passed=True)
    except BaseException as error:
        result.update(state='FAILED', passed=False, error=repr(error))
        raise
    finally:
        try:
            while True:
                try:
                    messages += os.read(fd, 1<<20).decode(errors='replace')+'\n'
                except BlockingIOError:
                    break
            (out/'kernel.log').write_text(messages)
            rt.require(not rt.FAULT.search(messages), 'kernel warning/fault')
        except BaseException as error:
            result.update(state='FAILED', passed=False, log_error=repr(error))
            raise
        finally:
            os.close(fd)
            rt.write_json(out/'result.json', result)
    return result


def diagnostic_receipt(path, inputs_path, binding, boot_id):
    receipt = load(path)
    rt.require(receipt.get('schema') == 1 and receipt.get('passed') is True and
               receipt.get('drained') is True and receipt.get('scope') == 'diagnostic-class-proof' and
               receipt.get('boot_id') == boot_id and receipt.get('kernel_binding') == binding and
               receipt.get('inputs_sha256') == rt.digest(inputs_path), 'mmap1 object observation differs')
    rt.require(set(receipt.get('models', {})) == set(MODELS), 'both application model observations required')
    verified_files(receipt['files'])
    validator = common.module('mmap1_identity_receipt_validator', ROOT/'tests/kernel/mmap1_identity/run.py')
    rt.require(receipt.get('clock_ticks') == 100, 'unexpected x86 Linux task start-time clock')
    for model, row in receipt['models'].items():
        session_path, snapshot_path = Path(row['session_result']), Path(row['snapshot'])
        rt.require(receipt['files'].get(str(session_path)) == row['session_result_sha256'] and
                   receipt['files'].get(str(snapshot_path)) == row['snapshot_sha256'],
                   'identity observation files are unbound')
        session = load(session_path)
        rt.require(session.get('model') == model and session.get('executable_sha256') ==
                   load(inputs_path)['binary_sha256'][model], 'identity executable/model differs')
        observed = validator.validate(load(snapshot_path), session, binding['kernel_mmap_backend'], receipt['clock_ticks'])
        rt.require(all(row.get(key) == value for key,value in observed.items()),
                   'identity summary differs from its actual stopped records')
    return receipt


def arguments(parser):
    parser.add_argument('--mode', choices=('native', 'kd'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    platform.arguments(parser)
    identity.arguments(parser)
    parser.set_defaults(kernel_source=None, kernel_baseline=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'measure'))
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--identity-result', type=Path)
    parser.add_argument('--model', choices=(*MODELS, 'both'), default='both')
    for name in mm.PREREQUISITES:
        parser.add_argument('--'+name+'-result', type=Path)
    arguments(parser)
    args = parser.parse_args()
    for name in ('inputs', 'identity_result', *(kind+'_result' for kind in mm.PREREQUISITES)):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve())
    guest(args)
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external evidence directory required')
    idle()
    out.mkdir(parents=True)
    result = dict(schema=1, action=args.action, mode=args.mode, boot_id=args.boot_id,
                  state='PREPARATION', passed=False, drained=False, accepted=False,
                  single_round=True, upstream_revision=REVISION, sessions=[], host_endpoint='PENDING')
    rt.write_json(out/'result.json', result)
    try:
        result.update(admit(args, out))
        support = freeze_support(out)
        if args.action == 'prepare':
            rt.require(args.upstream is not None and args.inputs is None, 'prepare needs original upstream checkout')
            prepared = prepare(args, out)
            result.update(inputs_sha256=rt.digest(out/'inputs.json'), binary_sha256=prepared['binary_sha256'])
        else:
            rt.require(args.inputs and args.identity_result, 'prepared binaries and unscored object proof required')
            rt.require(args.kernel_variant != 'kdlock1', 'scored replacement comparison requires enabled-MM mode prerequisites')
            inputs = inputs_from(args.inputs)
            rt.require(all(getattr(args, name+'_result') for name in mm.PREREQUISITES),
                       'all four same-boot MM correctness paths required')
            files = mm.prerequisite_files({name:getattr(args, name+'_result') for name in mm.PREREQUISITES},
                                         result['kernel_binding'], args.boot_id)
            diagnostic_receipt(args.identity_result, args.inputs, result['kernel_binding'], args.boot_id)
            files[str(args.inputs)] = rt.digest(args.inputs)
            files[str(args.inputs.parent/'result.json')] = rt.digest(args.inputs.parent/'result.json')
            files[str(args.identity_result)] = rt.digest(args.identity_result)
            files.update(load(args.identity_result)['files'])
            shutil.copyfile(args.inputs, out/'inputs.json')
            result.update(inputs_sha256=rt.digest(args.inputs), binary_sha256=inputs['binary_sha256'],
                          application_lock_identity='separate-diagnostic-class-proof; timed mm addresses unobserved',
                          identity_result=dict(path=str(args.identity_result), sha256=rt.digest(args.identity_result)))
            def verify():
                verify_boot(args)
                verified_files(support)
                verified_files(files)
                verified_files(inputs['files'])
            work = plan(args.model)
            rt.write_json(out/'plan.json', work)
            result.update(state='RUNNING', planned=len(work))
            for spec in work:
                name = f'{spec["model"]}-n{spec["workers"]:02d}-r00'
                print('START', name, flush=True)
                result['sessions'].append(run_point(out/name, spec, inputs, verify))
                rt.write_json(out/'result.json', result)
                print('FINISH', name, flush=True)
            verify()
        verified_files(support)
        verify_boot(args)
        idle()
        result.update(state='COMPLETE', passed=True, drained=True, final_idle=True)
    except BaseException as error:
        result.update(state='FAILED', passed=False, error=repr(error))
        raise
    finally:
        rt.write_json(out/'result.json', result)


if __name__ == '__main__':
    main()
