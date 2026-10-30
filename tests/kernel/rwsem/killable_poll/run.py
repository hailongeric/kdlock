#!/usr/bin/env python3
"""Guest-only real-signal observations of exact source-extracted admission helpers."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode = True
BASE_COMMIT = '22d62d5c13cad3c61c97dd47524da908769f1a52'
SOURCE_SHA256 = 'f2d665cd09453c9da6517ce0072bf5a6dec13929ab2de9e63caf53b4a419d38e'
HERE = Path(__file__).resolve().parent
HEADER = ('abi', 'cases', 'errors', 'inconclusive', 'joined', 'phase_idle', 'complete', 'timeouts')
FIELDS = ('id', 'signal', 'busy', 'send_error', 'pending_before', 'fatal_before',
          'preempt_before', 'irq_before', 'reserve_calls', 'reserve_wins',
          'resched_calls', 'resched_true', 'signal_calls', 'signal_true', 'relax_calls',
          'returned', 'admission_after', 'cleanup_ok', 'preempt_after', 'irq_after',
          'errors', 'inconclusive')
SIZE = 8 * (len(HEADER) + 4 * len(FIELDS))
RUN = (2 << 30) | (SIZE << 16) | (ord('K') << 8) | 0x73


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def definition(source, signature):
    matches = list(re.finditer(r'(?m)^' + re.escape(signature) + r'$', source))
    if len(matches) != 1:
        raise ValueError('expected one definition: ' + signature)
    start = matches[0].start()
    end = source.index('\n}', start) + 2
    return source[start:end] + '\n'


def client():
    data = bytearray(SIZE)
    with open('/dev/kd_rwsem_poll_probe', 'rb', buffering=0) as device:
        fcntl.ioctl(device, RUN, data, True)
    values = struct.unpack('=' + str(SIZE // 8) + 'Q', data)
    result = dict(zip(HEADER, values[:len(HEADER)]))
    result['rows'] = [dict(zip(FIELDS, values[len(HEADER) + i * len(FIELDS):
                                              len(HEADER) + (i + 1) * len(FIELDS)]))
                      for i in range(4)]
    print(json.dumps(result, sort_keys=True), flush=True)


def validate(observed, rt):
    rt.require(observed['abi'] == 1 and observed['cases'] == observed['joined'] == 4 and
               observed['complete'] == observed['phase_idle'] == 1 and
               observed['errors'] == observed['inconclusive'] == observed['timeouts'] == 0,
               'failed/inconclusive/incomplete poll observations')
    for i, row in enumerate(observed['rows']):
        busy = int(i < 2)
        rt.require(row['id'] == i and row['signal'] == (9 if i % 2 else 10) and
                   row['busy'] == busy and row['send_error'] == 0 and
                   row['pending_before'] == 1 and row['fatal_before'] == i % 2 and
                   row['preempt_before'] == row['preempt_after'] == 0 and
                   row['irq_before'] == row['irq_after'] == 0 and
                   row['reserve_calls'] == 1 and row['reserve_wins'] == 1 - busy and
                   row['returned'] == 1 - busy and row['relax_calls'] == 0 and
                   row['resched_calls'] == row['signal_calls'] == row['signal_true'] == busy and
                   row['resched_true'] == 0 and row['admission_after'] == 2**64 - 1 and
                   row['cleanup_ok'] == 1 and row['errors'] == row['inconclusive'] == 0,
                   'real signal/phase observation differs: ' + str(i))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=HERE.parents[3])
    parser.add_argument('--source-state', type=Path)
    parser.add_argument('--source-state-sha256')
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--source-manifest-sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cpu', type=int, default=0)
    parser.add_argument('--client', action='store_true')
    preliminary, _ = parser.parse_known_args()
    if preliminary.client:
        client()
        return
    root = preliminary.source_root.resolve()
    sys.path.insert(0, str(root / 'bench/spin_cacheline'))
    import bench_runtime as rt
    import kernel_identity
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(root).startswith('/root/') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    rt.require(args.output and args.source_state and args.source_manifest and args.cpu >= 0,
               'output and actual source synchronization inputs required')
    rt.require(digest(args.source_state) == args.source_state_sha256 and
               digest(args.source_manifest) == args.source_manifest_sha256,
               'synchronization receipt hashes differ')
    state = json.loads(args.source_state.read_bytes())
    sources = json.loads(args.source_manifest.read_bytes())
    rt.require(state.get('git_head') == BASE_COMMIT and state.get('git_status') == '' and
               state.get('files') == len(sources) and sources.get('kernel_module/kd_rwsem.c') == SOURCE_SHA256,
               'exact clean22d frozen production source required')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(HERE),
               'new external output required')

    def idle():
        rt.idle()
        for name in ('rwsem_probe', 'rwlock_bench', 'rwlock_test', 'real_api',
                     'kd_rwsem_poll_probe', 'kd_mmap_probe', 'kd_mmap1_identity'):
            rt.require(not Path('/sys/module', name).exists(), 'existing module: ' + name)
        for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
            try:
                name = path.read_text().strip()
            except FileNotFoundError:
                continue
            rt.require(name not in ('kd-rwpoll', 'kd_rwsem_probe', 'kd_rwsem_cancel',
                                    'rb_worker', 'mmap1_threads', 'mmap1_processes'),
                       'existing task: ' + str(path) + ': ' + name)

    def verify_sources():
        rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot,
                   'boot changed')
        rt.require(all(digest(root / name) == value for name, value in sources.items()),
                   'frozen production source changed')

    verify_sources()
    idle()
    out.mkdir(parents=True)
    result = dict(schema=1, state='PREPARATION', passed=False, drained=False, final_idle=False,
                  accepted=False, scored=False, source_commit=BASE_COMMIT, source_sha256=SOURCE_SHA256,
                  boot_id=boot, cpu=args.cpu, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                  scope='source-extracted real-kernel admission helper with observation wrappers',
                  provider_binary_proved=False, queued_cancellation_proved=False, jit_bodies=0,
                  files={}, source_state_sha256=args.source_state_sha256,
                  source_manifest_sha256=args.source_manifest_sha256)
    rt.write_json(out / 'result.json', result)
    fd = None
    messages = ''
    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out / 'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain probe')

    files = {}
    def copy(original, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        files[str(original)] = files[str(target)] = digest(target)

    def verify():
        verify_sources()
        rt.require(all(digest(path) == value for path, value in files.items()),
                   'probe source, support or binary changed')

    try:
        result['kernel_identity'] = kernel_identity.capture(args, out, rt.command)
        copy(args.source_state, out / 'source-state.json')
        copy(args.source_manifest, out / 'source-sha256.json')
        copy(Path(__file__).resolve(), out / 'runner.py')
        copy(HERE / 'README.md', out / 'README.md')
        build = out / 'build'
        for name in ('Makefile', 'module.c', 'api.h'):
            copy(HERE / 'payload' / name, build / name)
        # Include types exactly as selected by the frozen tracked manifest;
        # no provider object or generated Kbuild source is copied into the build.
        for name in sources:
            if name.startswith('include/'):
                copy(root / name, out / 'source' / name)
        original = root / 'kernel_module/kd_rwsem.c'
        copy(original, out / 'source/kernel_module/kd_rwsem.c')
        text = original.read_text()
        macro = '#define KD_RWSEM_LOCAL_WRITER (-1L)\n'
        rt.require(text.count(macro) == 1, 'phase constant differs')
        extracted = {
            'reserve-source.inc': macro + definition(text, 'static bool kd_rwsem_reserve_local(struct kd_rwsem *sem)'),
            'poll-source.inc': definition(text, 'static __always_inline bool kd_rwsem_poll_killable(struct kd_rwsem *sem)'),
        }
        extraction = dict(source_sha256=SOURCE_SHA256, source_commit=BASE_COMMIT,
                          text_transformed=False, wrapper_interposition=True, files={})
        for name, body in extracted.items():
            (build / name).write_text(body)
            files[str(build / name)] = digest(build / name)
            extraction['files'][name] = dict(sha256=digest(build / name), bytes=len(body.encode()))
        rt.write_json(out / 'extraction.json', extraction)
        # Preserve Python support and private implementation fragments. Kernel
        # bundle inputs are captured separately; large historical assembly and
        # build artifacts are not runtime inputs to this standalone probe.
        for directory in ('bench/spin_cacheline', 'kernel_baseline', 'kernel_integration/linux70',
                          'disassem', 'tests/protocols'):
            for name in sources:
                if name.startswith(directory + '/') and Path(name).suffix in ('.py', '.inc'):
                    copy(root / name, out / 'support' / name)
        verify()
        rt.command(['make', '-C', build, 'KDIR=' + str(args.kernel_source),
                    'KDLOCK_INCLUDE=' + str(out / 'source/include'), 'W=1', 'UBSAN_SANITIZE=n'],
                   out / 'build.log', timeout=180)
        module = build / 'kd_rwsem_poll_probe.ko'
        files[str(module)] = digest(module)
        vermagic = rt.command(['modinfo', '-F', 'vermagic', module], out / 'vermagic.log')
        rt.require(vermagic.split()[0] == os.uname().release, 'module release differs')
        verify()
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        result.update(state='RUNNING', files=files, module_sha256=digest(module),
                      extraction_sha256=digest(out / 'extraction.json'))
        rt.write_json(out / 'result.json', result)
        rt.command(['insmod', module, 'cpu=' + str(args.cpu)], out / 'load.log')
        logs()
        data = rt.command([sys.executable, out / 'runner.py', '--client'], out / 'observed.json', timeout=20)
        observed = json.loads(data)
        result['observations'] = observed
        result['observed_sha256'] = digest(out / 'observed.json')
        logs()
        verify()
        rt.require(observed['abi'] == 1 and observed['complete'] == observed['phase_idle'] == 1 and
                   observed['joined'] == observed['cases'], 'worker/phase drain not established')
        # A joined inconclusive case is safe to unload normally, but stays failed.
        rt.command(['rmmod', 'kd_rwsem_poll_probe'], out / 'unload.log')
        logs()
        idle()
        verify()
        result.update(drained=True, final_idle=True)
        validate(observed, rt)
        result.update(state='COMPLETE', passed=True)
        print('PASS source-extracted killable poll:4 real-signal cases; no provider/JIT/performance claim')
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        try:
            logs()
        except BaseException as error:
            result.update(state='FAILED', passed=False, log_error=repr(error))
            raise
        finally:
            if fd is not None:
                os.close(fd)
            result['files'] = files
            rt.write_json(out / 'result.json', result)


if __name__ == '__main__':
    main()
