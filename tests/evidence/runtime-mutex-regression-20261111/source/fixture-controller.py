#!/usr/bin/env python3
"""VM-only external fixture builds and one explicitly selected live run."""

import argparse
import ast
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

RELEASE = '7.0.0-38-kdrebuild4'
NORMAL = '7.0.0-38-kdlock1'
KERNEL_PINS = {'vmlinux', '.config', 'System.map', 'Module.symvers',
               'include/config/kernel.release', 'include/generated/utsrelease.h'}
FIXTURES = {
    'spin': ('kd_spin_runtime_fixture', 'tests/kernel/spin/payload',
             'tests/kernel/spin/run_spin_runtime_fixture.py',
             'protected_spin_jit_recursive_mechanism_pass'),
    'mutex': ('kd_runtime_fixture', 'tests/kernel/payload',
              'tests/kernel/run_runtime_fixture.py',
              'protected_jit_recursive_mechanism_pass'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pinned_json(path, expected):
    require(path.is_file() and not path.is_symlink() and digest(path) == expected,
            'receipt identity differs: ' + str(path))
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity():
    return dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                release=os.uname().release,
                taint=int(Path('/proc/sys/kernel/tainted').read_text()))


def command(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=15,
                          env={**os.environ, 'LC_ALL': 'C'}).stdout


def idle():
    modules = Path('/proc/modules').read_text()
    names = {entry[0] for entry in FIXTURES.values()}
    devices = sorted(str(path) for name in names for path in Path('/dev').glob(name + '*'))
    processes = command(['ps', '-eo', 'pid,comm,args'])
    require(not any(line.split()[0] in names for line in modules.splitlines() if line),
            'a fixture module remains loaded')
    require(not devices, 'fixture devices remain: ' + repr(devices))
    for line in processes.splitlines()[1:]:
        fields = line.split(None, 2)
        if len(fields) < 2:
            continue
        comm = fields[1].strip('[]')
        args = fields[2] if len(fields) == 3 else ''
        require(comm not in {'make', 'gcc', 'gcc-15', 'cc1', 'as', 'ld', 'ld.bfd',
                             'objtool', 'insmod', 'rmmod', 'modprobe', 'depmod', 'mkinitramfs'}
                and not comm.startswith('kd-fixture/')
                and not any(name in args for name in ('unittest discover',
                            'run_runtime_fixture.py', 'run_spin_runtime_fixture.py')),
                'build, fixture or boot-image work remains: ' + line)
    return dict(modules=modules, devices=devices, processes=processes)


def free_bytes(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def space(args, path):
    available = {'root': free_bytes('/'), 'output': free_bytes(path)}
    require(available['root'] >= args.root_floor and available['output'] >= args.space_floor,
            'explicit free-space floor is unavailable: ' + repr(available))
    return available


def verify_inputs(args):
    manifest = pinned_json(args.manifest, args.manifest_sha256)
    state = pinned_json(args.state, args.state_sha256)
    package = pinned_json(args.build_inputs, args.build_inputs_sha256)
    pins = pinned_json(args.kernel_pins, args.kernel_pins_sha256)
    require(state['commit'] == args.source_commit and
            package['source_git_head'] == args.package_source_commit and
            package['core_git_head'] == args.core_commit,
            'source or kernel package revision differs')
    required = {'tests/kernel/payload/runtime_fixture.c',
                'tests/kernel/payload/runtime_fixture_observe.inc',
                'tests/kernel/run_runtime_fixture.py',
                'tests/kernel/spin/payload/spin_runtime_fixture.c',
                'tests/kernel/spin/run_spin_runtime_fixture.py'}
    required |= {layout[1] + '/Kbuild' for layout in FIXTURES.values()}
    require(required <= manifest.keys(), 'frozen snapshot is missing fixture sources or private includes')
    actual = {}
    for path in args.input.rglob('*'):
        require(not path.is_symlink(), 'frozen source contains a symlink: ' + str(path))
        if path.is_file():
            actual[path.relative_to(args.input).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': digest(path)}
    require(actual == manifest, 'frozen source differs from the manifest')
    require(package['files'] and all(
        digest(args.kernel_source / 'kernel/kdlock' / name) == sha
        and actual[name]['sha256'] == sha for name, sha in package['files'].items()),
        'actual built kernel package differs from the frozen source')
    require(pins.keys() == KERNEL_PINS and
            {name: digest(args.kernel_build / name) for name in KERNEL_PINS} == pins,
            'actual completed kernel output pins differ')
    require((args.kernel_build / 'include/config/kernel.release').read_text().strip() == RELEASE and
            RELEASE in (args.kernel_build / 'include/generated/utsrelease.h').read_text(),
            'kernel output is outside the explicit release')
    config = (args.kernel_build / '.config').read_text().splitlines()
    require({'CONFIG_KDLOCK_REBUILD=y', 'CONFIG_PREEMPT_COUNT=y'} <= set(config)
            and 'CONFIG_PREEMPT_RT=y' not in config,
            'kernel config is outside the fixture context')
    return dict(source_commit=args.source_commit, core_commit=args.core_commit,
                package_source_commit=args.package_source_commit,
                source_manifest_sha256=args.manifest_sha256, source_file_count=len(actual),
                package_manifest_sha256=args.build_inputs_sha256,
                package_file_count=len(package['files']), kernel_pins_sha256=args.kernel_pins_sha256,
                kernel_pins=pins)


def observe(args, argv, receipts, env, output_filesystem):
    started = time.monotonic()
    save(receipts / 'command.json', dict(argv=argv, environment=env, utc=utc(),
                                        observer_seconds=args.seconds))
    with (receipts / 'stdout.log').open('xb') as log:
        child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env={**os.environ, **env})
        save(receipts / 'child.json', dict(pid=child.pid, utc=utc()))
        stop = None
        while child.poll() is None:
            if time.monotonic() - started >= args.seconds:
                stop = 'observer deadline'
                break
            try:
                space(args, output_filesystem)
            except ValueError:
                stop = 'space floor'
                break
            time.sleep(0.25)
        result = dict(pid=child.pid, returncode=child.poll(), utc=utc(),
                      elapsed_seconds=time.monotonic() - started, observer_stop=stop)
    save(receipts / 'child-result.json', result)
    return result


def build(args, record):
    require(args.jobs > 0, 'positive build jobs required')
    overrides = sorted(name for name in os.environ if name in {
        'KCFLAGS', 'KAFLAGS', 'KCPPFLAGS', 'CC', 'LD', 'KBUILD_CFLAGS', 'KBUILD_AFLAGS',
        'MAKEFLAGS', 'MFLAGS', 'LLVM', 'LLVM_IAS'} or name.startswith(('CFLAGS', 'AFLAGS')))
    require(not overrides, 'unreviewed build environment overrides: ' + ', '.join(overrides))
    record['compiler_environment_overrides'] = overrides
    record['module_builds'] = {}
    for variant, (name, payload, runner, _) in FIXTURES.items():
        ast.parse((args.input / runner).read_text(), filename=runner)
        output = args.output / variant
        receipt = args.receipts / variant
        output.mkdir()
        receipt.mkdir()
        argv = ['make', '-C', str(args.kernel_source), 'O=' + str(args.kernel_build),
                'M=' + str(args.input / payload), 'MO=' + str(output),
                'KERNELRELEASE=' + RELEASE, '-j' + str(args.jobs), 'V=1', 'modules']
        result = observe(args, argv, receipt, {'LC_ALL': 'C', 'LANG': 'C'}, output)
        record['module_builds'][variant] = result
        if result['observer_stop'] or result['returncode'] != 0:
            return 124 if result['observer_stop'] else result['returncode']
        module = output / (name + '.ko')
        info = command(['modinfo', str(module)])
        (receipt / 'modinfo.txt').write_text(info)
        (receipt / 'symbols.txt').write_text(command(['nm', '-S', '--defined-only', str(module)]))
        require(command(['modinfo', '-F', 'name', str(module)]).strip() == name and
                command(['modinfo', '-F', 'vermagic', str(module)]).split()[0] == RELEASE,
                'compiled fixture module name or vermagic differs')
        result.update(module=str(module), module_sha256=digest(module), module_bytes=module.stat().st_size,
                      runner_ast='PASS', stdout_sha256=digest(receipt / 'stdout.log'))
        record['after_each_build'] = verify_inputs(args)
        require(identity() == record['before_identity'], 'guest identity changed during build')
        idle()
    return 0


def parse_cpus(text):
    cpus = set()
    for piece in text.strip().split(','):
        bounds = piece.split('-')
        first, last = int(bounds[0]), int(bounds[-1])
        require(len(bounds) <= 2 and 0 <= first <= last, 'invalid online CPU list')
        cpus.update(range(first, last + 1))
    return cpus


def finish_live(args, record, module_sha, success):
    result_path = args.output / 'result.json'
    result = json.loads(result_path.read_text())
    require(result['status'] == success and result['kernel_release'] == RELEASE and
            result['module_sha256'] == module_sha and
            result['returned_full_jit_body'] == 'protected_episode_completed' and
            result['managed_fork_exit']['shutdown_native_holds_drained'] is True,
            'runner did not record protected completion and managed shutdown')
    attempts = sorted((args.output / 'wire').glob('attempt-*'))
    require(len(attempts) == result['wire_log']['reservations'] and len(attempts) >= 4,
            'wire receipt count differs')
    tail = [json.loads((attempt / 'result.json').read_text()) for attempt in attempts[-4:]]
    require([row['operation'] for row in tail] == [9, 10, 11, 6] and all(
        row['completed_response'] is True and row['status'] == 0 and
        row['returned_sequence'] == row['sequence'] for row in tail),
        'actual shutdown, archive claim, settlement and end are required')
    archive_sha = digest(args.output / 'shutdown-archive.json')
    require(archive_sha == result['archive_sha256'], 'actual archive hash differs')
    record.update(runner_status=success, runner_result_sha256=digest(result_path),
                  archive_sha256=archive_sha, wire_tail=tail, wire_attempts=len(attempts),
                  unloaded=True)


def live(args, record):
    variant = args.variant
    name, _, runner, success = FIXTURES[variant]
    before = record['before_identity']
    require(before['release'] == RELEASE, 'exact rebuilt kernel must be running')
    proof = pinned_json(args.postboot, args.postboot_sha256)
    gs = pinned_json(args.gs_proof, args.gs_proof_sha256)
    pins = record['verified_inputs']['kernel_pins']
    require(proof['phase'] == 'POSTBOOT_IDENTITY_VERIFIED' and
            proof['source_commit'] == args.core_commit and proof['boot_id'] == before['boot_id'] and
            proof['running_build_id'] == args.build_id and int(proof['tainted']) == 0 and
            gs['verified_for_running_kernel'] is True and gs['boot_id'] == before['boot_id'] and
            gs['kernel_release'] == RELEASE and gs['build_id'] == args.build_id and
            gs['kernel_elf_sha256'] == pins['vmlinux'] and gs['kernel_config_sha256'] == pins['.config'] and
            gs['gs_symbol'] == 'current_task' and gs['kaslr_disabled'] is True and
            int(str(gs['const_current_task']), 0) == int(str(gs['current_task_gs_offset']), 0),
            'actual postboot identity/full-VMA current_task proof differs')
    built = pinned_json(args.module_result, args.module_result_sha256)
    require(built['status'] == 'COMPLETE' and built['returncode'] == 0 and
            built['verified_inputs'] == record['verified_inputs'], 'module build inputs differ')
    compiled = built['module_builds'][variant]
    require(compiled['returncode'] == 0 and compiled['observer_stop'] is None and
            compiled['runner_ast'] == 'PASS', 'target fixture build did not complete')
    module = Path(compiled['module'])
    require(module.name == name + '.ko' and not module.is_symlink() and
            module.stat().st_size == compiled['module_bytes'] and
            digest(module) == compiled['module_sha256'], 'actual fixture module differs from the build')
    if variant == 'spin':
        require(before['taint'] == 0 and args.prior_result is None and args.prior_result_sha256 is None,
                'spin requires the fresh proven boot')
    else:
        require(before['taint'] == 12288 and args.prior_result and args.prior_result_sha256,
                'same-boot mutex requires the exact completed spin receipt and expected module taint')
        prior = pinned_json(args.prior_result, args.prior_result_sha256)
        require(prior['status'] == 'COMPLETE' and prior['returncode'] == 0 and
                prior['variant'] == 'spin' and prior['unloaded'] is True and
                prior['after_identity'] == before and
                prior['verified_inputs'] == record['verified_inputs'] and
                prior['module_result_sha256'] == args.module_result_sha256 and
                prior['postboot_sha256'] == args.postboot_sha256,
                'prior spin run did not establish same-boot drain/unload')
        record['prior_result_sha256'] = args.prior_result_sha256
    tracer = Path('/sys/kernel/tracing/current_tracer')
    require(not tracer.exists() or tracer.read_text().strip() == 'nop', 'active tracer changes context')
    require(args.python.is_file() and os.access(args.python, os.X_OK) and args.recovery_tag,
            'explicit interpreter and confirmed recovery snapshot tag required')
    require(math.isfinite(args.deadline) and args.deadline > 0 and args.deadline < args.seconds,
            'finite runner deadline below the outer observer limit required')
    record.update(variant=variant, module_sha256=compiled['module_sha256'],
                  module_result_sha256=args.module_result_sha256, postboot_sha256=args.postboot_sha256,
                  gs_proof_sha256=args.gs_proof_sha256, kernel_build_id=args.build_id,
                  recovery_snapshot_tag=args.recovery_tag)
    argv = [str(args.python), str(args.input / runner), '--repo', str(args.input),
            '--module', str(module), '--output', str(args.output), '--expected-release', RELEASE,
            '--kernel-elf', str(args.kernel_build / 'vmlinux'),
            '--kernel-config', str(args.kernel_build / '.config'), '--gs-proof-json', str(args.gs_proof),
            '--gs-offset', str(gs['current_task_gs_offset']), '--immutable-text-contract',
            '--auxiliary-stack-contract']
    for key in ('dependency_page_limit', 'total_source_byte_limit', 'wire_log_byte_limit',
                'event_capacity', 'workers', 'iterations', 'deadline'):
        argv += ['--' + key.replace('_', '-'), str(getattr(args, key))]
    if args.builtin_source_start or args.builtin_source_size:
        argv += ['--builtin-source-start', str(args.builtin_source_start),
                 '--builtin-source-size', str(args.builtin_source_size)]
        record['builtin_source'] = dict(start=args.builtin_source_start,
                                         length=args.builtin_source_size)
    if variant == 'spin':
        require(args.holder_timeout_ms is not None and 0 < args.holder_timeout_ms < 1 << 32,
                'explicit bounded holder wait required')
        online = parse_cpus(Path('/sys/devices/system/cpu/online').read_text())
        available = os.sched_getaffinity(0) & online
        cpus = args.cpus if args.cpus is not None else sorted(available)[:6]
        require(len(cpus) == len(set(cpus)) == 6 and set(cpus) <= available,
                'five distinct role CPUs and a separate controller CPU required')
        record['cpu_selection'] = dict(online=sorted(online), available=sorted(available),
                                       roles=cpus[:5], controller=cpus[5])
        argv += ['--spin-cpus', *map(str, cpus[:5]), '--controller-cpu', str(cpus[5]),
                 '--holder-timeout-ms', str(args.holder_timeout_ms)]
    else:
        require(args.cpus is None and args.holder_timeout_ms is None, 'spin arguments on mutex run')
    env = dict(LC_ALL='C', LANG='C', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
               KDLOCK_RECOVERY_CONFIRMED='1', KDLOCK_SNAPSHOT_TAG=args.recovery_tag)
    (args.receipts / 'dmesg-before.txt').write_text(command(['dmesg', '--color=never']))
    result = observe(args, argv, args.receipts, env, args.output.parent)
    record['runner'] = result
    if result['observer_stop'] or result['returncode'] != 0:
        return 124 if result['observer_stop'] else result['returncode']
    record['after_idle'] = idle()
    (args.receipts / 'dmesg-after.txt').write_text(command(['dmesg', '--color=never']))
    record['after_identity'] = identity()
    require(record['after_identity'] == {**before, 'taint': 12288}, 'guest identity or taint changed unexpectedly')
    require(verify_inputs(args) == record['verified_inputs'] and digest(module) == record['module_sha256'],
            'source, module or kernel outputs changed during run')
    finish_live(args, record, compiled['module_sha256'], success)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'manifest', 'state', 'build-inputs', 'kernel-source', 'kernel-build',
                'kernel-pins', 'output', 'receipts'):
        parser.add_argument('--' + key, type=Path, required=True)
    for key in ('manifest-sha256', 'state-sha256', 'build-inputs-sha256', 'kernel-pins-sha256',
                'expected-boot', 'source-commit', 'core-commit', 'package-source-commit'):
        parser.add_argument('--' + key, required=True)
    for key in ('space-floor', 'root-floor'):
        parser.add_argument('--' + key, type=int, required=True)
    parser.add_argument('--seconds', type=float, required=True)
    modes = parser.add_subparsers(dest='mode', required=True)
    builder = modes.add_parser('build')
    builder.add_argument('--jobs', type=int, required=True)
    runner = modes.add_parser('live')
    runner.add_argument('variant', choices=FIXTURES)
    for key in ('postboot', 'gs-proof', 'module-result', 'python'):
        runner.add_argument('--' + key, type=Path, required=True)
    for key in ('postboot-sha256', 'gs-proof-sha256', 'module-result-sha256', 'build-id', 'recovery-tag'):
        runner.add_argument('--' + key, required=True)
    for key in ('dependency-page-limit', 'total-source-byte-limit', 'wire-log-byte-limit',
                'event-capacity', 'workers', 'iterations'):
        runner.add_argument('--' + key, type=int, required=True)
    runner.add_argument('--deadline', type=float, required=True)
    runner.add_argument('--builtin-source-start', type=lambda value: int(value, 0), default=0)
    runner.add_argument('--builtin-source-size', type=lambda value: int(value, 0), default=0)
    runner.add_argument('--cpus', nargs=6, type=int)
    runner.add_argument('--holder-timeout-ms', type=int)
    runner.add_argument('--prior-result', type=Path)
    runner.add_argument('--prior-result-sha256')
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().machine == 'x86_64', 'designated root VM required')
    before = identity()
    require(before['boot_id'] == args.expected_boot and before['release'] in {NORMAL, RELEASE},
            'actual boot identity differs')
    require(args.root_floor > 0 and args.space_floor > 0 and
            math.isfinite(args.seconds) and args.seconds > 0, 'explicit positive observer bounds required')
    protected = []
    for key in ('input', 'kernel_source', 'kernel_build'):
        path = getattr(args, key)
        require(not path.is_symlink() and path.is_dir(), 'direct source and kernel trees required')
        path = path.resolve(strict=True)
        setattr(args, key, path)
        protected.append(path)
    args.output, args.receipts = args.output.resolve(), args.receipts.resolve()
    for leaf in (args.output, args.receipts):
        require(leaf.parent.is_dir() and not leaf.exists() and all(
            leaf != old and leaf not in old.parents and old not in leaf.parents for old in protected),
            'fresh separate output and receipt leaves required')
    require(args.output != args.receipts and args.output not in args.receipts.parents and
            args.receipts not in args.output.parents, 'output and receipt leaves overlap')
    verified = verify_inputs(args)
    available = space(args, args.output.parent)
    before_idle = idle()
    args.receipts.mkdir(mode=0o700)
    record = dict(mode=args.mode, start_utc=utc(), before_identity=before, before_idle=before_idle,
                  verified_inputs=verified, space_before=available)
    try:
        if args.mode == 'build':
            args.output.mkdir(mode=0o700)
            code = build(args, record)
        else:
            code = live(args, record)
        record.update(status='COMPLETE' if code == 0 else 'FAILED_OR_INCOMPLETE', returncode=code)
    except BaseException as error:
        record.update(status='FAILED_OR_INCOMPLETE', error=repr(error))
        raise
    finally:
        record.update(end_utc=utc(), observed_final_identity=identity())
        save(args.receipts / 'result.json', record)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
