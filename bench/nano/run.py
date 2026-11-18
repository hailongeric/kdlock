#!/usr/bin/env python3
"""VM-only selected nano family/backend; preserve failed runs and loaded state."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from protocol import DEVICE, DESTROY, DRAIN, snapshot, set_recording
from oracle import require, validate


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_scope(scope, backend):
    require(scope != 'recorder-pair' or backend == 'kdlock',
            'recorder-pair scope requires the KD backend')
    require(scope not in ('native-current', 'mutex-uncontended') or backend in ('native', 'kdlock'),
            'single-worker comparison requires Native or KD')
    require(scope != 'rwsem-split' or backend in ('native', 'kdlock'),
            'rwsem-split scope requires Native or KD')


def measurement_plan(scope, stage, backend=None):
    if scope == 'rwsem-split':
        validate_scope(scope, backend)
        modes = ('on', 'off') if backend == 'kdlock' else ('unavailable',)
        plan = [(f'functional-w{count}-{mode}', count, False, mode)
                for mode in modes for count in (1, 8)]
        if stage == 'timing':
            mode = 'off' if backend == 'kdlock' else 'unavailable'
            plan.extend((f'timed-r{repeat + 1}-w{count}-{mode}', count, True, mode)
                        for repeat in range(3) for count in (1, 8))
        return plan
    if scope in ('native-current', 'mutex-uncontended'):
        validate_scope(scope, backend)
        modes = ('on', 'off') if backend == 'kdlock' else ('unavailable',)
        plan = [(f'functional-{mode}', 1, False, mode) for mode in modes]
        if stage == 'timing':
            mode = 'off' if backend == 'kdlock' else 'unavailable'
            plan.extend((f'timed-r{repeat + 1}-{mode}', 1, True, mode) for repeat in range(3))
        return plan
    if scope == 'recorder-pair':
        plan = [(f'functional-{mode}', 1, False, mode) for mode in ('on', 'off')]
        if stage == 'timing':
            for repeat in range(3):
                modes = ('on', 'off') if repeat % 2 == 0 else ('off', 'on')
                plan.extend((f'timed-r{repeat + 1}-{mode}', 1, True, mode) for mode in modes)
        return plan
    mode = ('unavailable' if scope == 'mutex-comparison' and backend != 'kdlock' else 'on')
    plan = [(f'functional-{count}', count, False, mode) for count in (1, 8, 36)]
    if stage == 'timing':
        plan.extend((f'timed-r{repeat + 1}-w{count}', count, True, mode)
                    for repeat in range(3) for count in (1, 8, 36))
    return plan


def validate_prerequisites(prior, scope, family, build_sha256, boot_id, runner_sha256=None,
                           collector_cpu=63):
    require(all(p['status'] == 'FUNCTIONAL_PASS' and p['build_receipt_sha256'] == build_sha256 and
                p['boot_id'] == boot_id for p in prior), 'functional build/boot receipt differs')
    if scope == 'mutex-comparison':
        require(family == 'mutex' and len(prior) == 3 and
                {p['backend'] for p in prior} == {'native', 'kdlock', 'tclock'} and
                all(p['family'] == family and p.get('scope') == scope and
                    p.get('stage') == 'functional' and p.get('runner_sha256') == runner_sha256 and
                    p.get('collector_cpu') == collector_cpu and
                    p.get('kd_delegation') == ('on' if p['backend'] == 'kdlock' else None)
                    for p in prior), 'three matched mutex functional receipts required')
    elif scope == 'rwsem-split':
        require(bool(runner_sha256) and family == 'rwsem' and len(prior) == 3 and
                {(p['backend'], p.get('kd_delegation')) for p in prior} ==
                {('native', None), ('kdlock', 'on'), ('kdlock', 'off')} and
                all(p['family'] == family and p.get('scope') == scope and
                    p.get('stage') == 'functional' and p.get('runner_sha256') == runner_sha256 and
                    p.get('recorder_modes') == (['on', 'off'] if p['backend'] == 'kdlock' else ['unavailable'])
                    for p in prior), 'matching Native, KD delegation-off/on functional receipts required')
    elif scope == 'mutex-uncontended':
        require(bool(runner_sha256) and family == 'mutex' and len(prior) == 2 and
                {p['backend'] for p in prior} == {'native', 'kdlock'} and
                all(p['family'] == family and p.get('scope') == scope and
                    p.get('stage') == 'functional' and p.get('runner_sha256') == runner_sha256 and
                    p.get('collector_cpu') == collector_cpu and
                    p.get('kd_delegation') == ('on' if p['backend'] == 'kdlock' else None) and
                    p.get('recorder_modes') == (['on', 'off'] if p['backend'] == 'kdlock' else ['unavailable'])
                    for p in prior), 'matched single-worker mutex functional receipts required')
    elif scope == 'native-current':
        require(len(prior) == 4 and {(p['family'], p['backend']) for p in prior} ==
                {(f, b) for f in ('mutex', 'rwsem') for b in ('native', 'kdlock')} and
                all(p.get('scope') == scope and p.get('stage') == 'functional' and
                    p.get('recorder_modes') == (['on', 'off'] if p['backend'] == 'kdlock' else ['unavailable'])
                    for p in prior), 'all four current Native/KD functional lanes required')
        require(bool(runner_sha256) and all(p.get('runner_sha256') == runner_sha256 for p in prior),
                'functional runner identity differs')
    elif scope == 'recorder-pair':
        require(len(prior) == 1 and prior[0]['family'] == family and prior[0]['backend'] == 'kdlock' and
                prior[0].get('scope') == scope and prior[0].get('recorder_modes') == ['on', 'off'],
                'current family recorder-on/off functional receipt required')
    else:
        require({(p['family'], p['backend']) for p in prior} ==
                {(f, b) for f in ('mutex', 'rwsem') for b in ('native', 'kdlock', 'tclock')} and
                all(p.get('scope', 'comparison') == 'comparison' for p in prior),
                'all six current functional lanes required')


def phase_recording(scope, backend, mode):
    # Native has no KD observation subscription or recorder-control ioctl.
    if backend == 'kdlock' and scope in ('recorder-pair', 'native-current', 'mutex-uncontended', 'rwsem-split'):
        require(mode in ('on', 'off'), 'KD recorder mode differs')
        return set_recording(mode == 'on')
    return None


def validate_kernel_receipt(receipt, expected_release, kernel_sha256):
    require(receipt['status'] == 'NANO_MODULES_BUILT_SIGNED', 'module build incomplete')
    require(receipt['kernel_release'] == expected_release and
            receipt['kernel_files']['vmlinux'] == kernel_sha256, 'module build/kernel ELF identity differs')


def validate_builtin_source(symbols, expected_start, code):
    matches = [int(fields[0], 16) for fields in map(str.split, symbols.splitlines())
               if len(fields) == 3 and fields[1] in ('t', 'T') and fields[2] == 'its_return_thunk']
    require(expected_start != 0 and matches == [expected_start], 'live ITS return thunk address differs')
    require(code == b'\xc3\xcc', 'captured ITS return thunk differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--family', choices=('mutex', 'rwsem'), required=True)
    parser.add_argument('--backend', choices=('native', 'kdlock', 'tclock'), required=True)
    parser.add_argument('--stage', choices=('functional', 'timing'), required=True)
    parser.add_argument('--scope', choices=('comparison', 'mutex-comparison', 'mutex-uncontended', 'recorder-pair', 'native-current', 'rwsem-split'), default='comparison')
    parser.add_argument('--delegation', choices=('on', 'off'), default='on',
                        help='Immutable KD runtime mode; independent of recorder state')
    parser.add_argument('--collector-cpu', type=int, default=63,
                        help='Dedicated CPU for the measurement client and controller')
    parser.add_argument('--timing-round', type=int, choices=(1, 2, 3),
                        help='Run one numbered mutex comparison round for alternating backends')
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--expected-release', default='7.0.0-38-kdrebuild9',
                        help='Exact running/module-build release; default preserves the kernel9 baseline')
    parser.add_argument('--builtin-source-start', type=lambda value: int(value, 0),
                        default=0xffffffff8276eee0,
                        help='Exact live/ELF its_return_thunk address; default is kernel9')
    parser.add_argument('--kernel-elf', type=Path, required=True)
    parser.add_argument('--gs-proof', type=Path, required=True)
    parser.add_argument('--prerequisite', type=Path, action='append', default=[])
    args = parser.parse_args()
    validate_scope(args.scope, args.backend)
    mutex_pair = args.scope in ('mutex-comparison', 'mutex-uncontended')
    require(not mutex_pair or args.family == 'mutex', 'mutex comparison requires mutex')
    require(args.timing_round is None or (mutex_pair and args.stage == 'timing'),
            'a selected round requires mutex comparison timing')
    require(args.scope != 'rwsem-split' or args.family == 'rwsem', 'rwsem-split requires rwsem')
    require(args.delegation == 'on' or args.backend == 'kdlock', 'delegation-off requires KD')
    require(args.delegation == 'on' or args.family == 'rwsem',
            'the contended local-only witness currently covers rwsem')
    require(os.uname().release == args.expected_release and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
            'running kernel/boot identity differs')
    taint = int(Path('/proc/sys/kernel/tainted').read_text())
    require(taint in ((0, 4096) if mutex_pair else (4096,)),
            'unexpected prior kernel taint')
    require({line.split()[0] for line in Path('/proc/modules').read_text().splitlines()} <= {'nls_iso8859_1'},
            'a previous experiment remains loaded')
    require(not Path(DEVICE).exists(), 'previous workload device remains')
    args.output.mkdir()
    plan = measurement_plan(args.scope, args.stage, args.backend)
    max_workers = max([8 if args.backend == 'kdlock' else 1] + [p[1] for p in plan])
    require(args.collector_cpu >= max_workers, 'collector overlaps worker placement')
    os.sched_setaffinity(0, {args.collector_cpu})
    sys.path.insert(0, str(args.repo))
    from compiler import Compiler, symbol_size, executable_elf_bytes
    from evidence import validate_kd
    receipt = json.loads(args.build_receipt.read_text())
    kernel_sha256 = sha(args.kernel_elf)
    runner_sha256 = sha(Path(__file__))
    validate_kernel_receipt(receipt, args.expected_release, kernel_sha256)
    if args.stage == 'timing':
        prior = [json.loads(p.read_text()) for p in args.prerequisite]
        validate_prerequisites(prior, args.scope, args.family, sha(args.build_receipt), args.boot_id,
                               runner_sha256, args.collector_cpu)
    row = dict(status='STARTED', family=args.family, backend=args.backend, stage=args.stage,
               scope=args.scope, recorder_modes=list(dict.fromkeys(
                   mode for _, _, _, mode in measurement_plan(args.scope, 'functional', args.backend))),
               runner_sha256=runner_sha256, collector_cpu=args.collector_cpu,
               timing_round=args.timing_round,
               profile='mutex-throughput' if args.family == 'mutex' else 'rwsem-throughput-mixed',
               boot_id=args.boot_id, kernel_release=os.uname().release,
               kernel_elf_sha256=kernel_sha256,
               build_receipt_sha256=sha(args.build_receipt), measurements=[], commands=[],
               workload='single 64-byte-padded counter, deterministic mix, post256, bulk ioctl',
               instrumentation='bounded per-origin exact request/completion records for KD; original TCLock counters',
               kd_delegation=args.delegation if args.backend == 'kdlock' else None,
               kd_proxy_limit=(16 if args.delegation == 'on' else 0) if args.backend == 'kdlock' else None,
               tclock_batch_limit=1024,
               timing_qualification='exploratory; host strict timing qualification is separate')
    if args.scope == 'recorder-pair':
        row['instrumentation'] = 'quiescent recorder on/off; off completion/retirement observations unavailable'
    elif args.scope in ('native-current', 'mutex-uncontended', 'rwsem-split'):
        row['instrumentation'] = ('KD training and functional recording on/off; all timings off with '
                                  'completion/retirement observations unavailable' if args.backend == 'kdlock'
                                  else 'Native has no KD recorder or generated-completion observations')
    save(args.output / 'started.json', row)

    def command(label, argv, seconds=60):
        log = args.output / (label + '.log')
        record = dict(argv=list(map(str, argv)), started_unix=time.time())
        row['commands'].append(record)
        with log.open('xb') as stream:
            child = subprocess.Popen(record['argv'], stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True)
            record['pid'] = child.pid
            save(args.output / (label + '-started.json'), record)
            end = time.monotonic() + seconds
            while child.poll() is None:
                if time.monotonic() >= end or log.stat().st_size > 64 * 1024 * 1024:
                    record['returncode'] = None
                    save(args.output / (label + '-incomplete.json'), record)
                    raise TimeoutError('observer ended; child and module state retained: ' + label)
                time.sleep(0.05)
            stream.flush()
            os.fsync(stream.fileno())
        record.update(returncode=child.returncode, elapsed_seconds=time.time() - record['started_unix'],
                      log_sha256=sha(log))
        save(args.output / (label + '-result.json'), record)
        require(child.returncode == 0, 'command failed: ' + label)
        return log.read_text()

    def module(key, label, parameters=()):
        item = receipt['modules'][key]
        require(sha(item['signed']) == item['signed_sha256'], 'signed module changed: ' + key)
        command(label, ['/usr/sbin/insmod', item['signed'], *parameters])
        return item

    def fault_check(label):
        text = command(label, ['/usr/bin/dmesg', '--color=never'])
        require(text.startswith(before_log), 'kernel log prefix changed')
        added = text[len(before_log):]
        require(not any(token in added for token in ('BUG:', 'kernel BUG at', 'Oops:',
                    'general protection fault', 'WARNING: CPU:', 'Kernel panic')), 'new kernel fault')

    compiler = None
    provider_name = 'tclock_' + args.family + '_backend_km'
    tc_params = Path('/sys/module') / provider_name / 'parameters'
    try:
        before_log = command('dmesg-before', ['/usr/bin/dmesg', '--color=never'])
        if args.backend == 'tclock':
            module('tclock-' + args.family, 'load-tclock', ['komb_batch_size=1024'])
        item = receipt['modules'][args.family + '-' + args.backend]
        params = []
        if args.backend == 'kdlock':
            proof = json.loads(args.gs_proof.read_text())
            require(proof['verified_for_running_kernel'] and proof['boot_id'] == args.boot_id and
                    kernel_sha256 == proof['kernel_elf_sha256'], 'exact live GS/kernel proof differs')
            gs = int(proof['current_task_gs_offset'], 0)
            builtin_start, builtin_size = args.builtin_source_start, 2
            builtin = executable_elf_bytes(args.kernel_elf, builtin_start, builtin_size)
            validate_builtin_source(Path('/proc/kallsyms').read_text(), builtin_start, builtin)
            row['builtin_source_start'] = builtin_start
            write_size = symbol_size(item['signed'], 'rb_write', '/usr/bin/nm', 60)
            read_size = symbol_size(item['signed'], 'rb_read', '/usr/bin/nm', 60)
            version = 'nano-' + item['signed_sha256'] + '-' + proof['kernel_elf_sha256']
            params = [f'gs_offset={gs}', 'gs_verified=1', 'immutable_text=1', 'auxiliary_contract=1',
                      f'source_size={write_size}', f'step_size={read_size}', 'dependency_page_limit=16',
                      'total_source_byte_limit=131072', f'builtin_source_start={builtin_start}',
                      f'builtin_source_size={builtin_size}', 'source_version=' + version]
            params.append('delegation=' + ('1' if args.delegation == 'on' else '0'))
        module(args.family + '-' + args.backend, 'load-workload', params)
        if args.backend == 'kdlock':
            mode = Path('/sys/module/kd_nano/parameters/delegation').read_text().strip()
            require(mode == ('Y' if args.delegation == 'on' else 'N'),
                    'loaded immutable delegation mode differs')
            row['delegation_control'] = dict(parameter=mode, proxy_limit=row['kd_proxy_limit'],
                                             immutable=True, independent_of_recording=True)
        layout = snapshot()
        require(layout['values'] == [0] * 16 and not any(layout[n] for n in ('cnts', 'gate', 'active')),
                'initial workload not empty')
        row['layout'] = layout
        if args.backend == 'tclock':
            (tc_params / 'target_lock').write_text(str(layout['lock_addr']))
            require((tc_params / 'quiescent').read_text().strip() == '1', 'TCLock initial state not quiescent')
        if args.backend == 'kdlock':
            symbols = [line.split() for line in Path('/proc/kallsyms').read_text().splitlines()]
            writers = [int(s[0], 16) for s in symbols if len(s) == 4 and s[2:] == ['rb_write', '[kd_nano]']]
            require(len(writers) == 1 and writers[0], 'exact loaded writer symbol missing')
            compiler = Compiler(args.repo, args.output / 'compiler', gs, builtin_start, builtin, writers[0])

        def phase(label, workers, *, duration=0, iterations=256, timed=False, recorder=None):
            if recorder is None:
                recorder = ('unavailable' if args.scope in ('native-current', 'mutex-uncontended', 'rwsem-split', 'mutex-comparison')
                            and args.backend != 'kdlock' else 'on')
            control = phase_recording(args.scope, args.backend, recorder)
            spec = dict(arm=args.backend, lock_kind=args.family, workload='cacheline', cachelines=1,
                        post_work_rounds=256, threads=workers, cpus=list(range(workers)), collector_cpu=args.collector_cpu,
                        write_percent=100 if args.family == 'mutex' else 20, duration_ms=duration,
                        iterations=iterations, sample_ms=10, peak_window_ms=300, peak_settle_ms=300,
                        recorder=recorder, delegation=args.backend == 'kdlock' and args.delegation == 'on')
            save(args.output / (label + '.spec.json'), spec)
            if args.backend == 'tclock':
                tc_before = {k: int((tc_params / k).read_text()) for k in ('delegated', 'batches', 'parks')}
            text = command(label, [sys.executable, '-B', args.repo / 'bench/nano/client.py',
                                   '--spec', args.output / (label + '.spec.json')], 120)
            measurement = json.loads(text)
            require(measurement['data_ok'] is True, 'client body/mix/post-work validation failed')
            peak = validate(measurement, spec)
            measurement.update(label=label, timed=timed, spec=spec,
                whole_run_ops_s=measurement['completed'] * 1e9 / measurement['wall_ns'], peak=peak)
            if compiler is not None:
                measurement['generated'] = validate_kd(measurement, compiler, recording=recorder == 'on')
                if args.scope in ('recorder-pair', 'native-current', 'mutex-uncontended', 'rwsem-split'):
                    measurement.update(recording_control=control, fixed_image=compiler.old)
            if args.backend == 'tclock':
                # The client process has exited; task registration references
                # can now drain through the provider's exact task/queue checks.
                with open(DEVICE, 'rb', buffering=0) as device:
                    fcntl.ioctl(device, DRAIN)
                require((tc_params / 'quiescent').read_text().strip() == '1', 'TCLock exact drain incomplete')
                measurement['tclock'] = {p.name: p.read_text().strip() for p in tc_params.iterdir()
                                         if p.name != 'drain'}
                measurement['tclock_delta'] = {k: int(measurement['tclock'][k]) - v
                                                for k, v in tc_before.items()}
                require(all(v >= 0 for v in measurement['tclock_delta'].values()),
                        'TCLock phase counters went backwards')
            save(args.output / (label + '.json'), measurement)
            row['measurements'].append(measurement)
            fault_check(label + '-dmesg')
            print(json.dumps(dict(phase=label, backend=args.backend, family=args.family,
                                  completed=measurement['completed'], generated=measurement.get('generated'),
                                  whole_run_ops_s=measurement['whole_run_ops_s'])), flush=True)
            return measurement

        phase('local-1', 1, iterations=32)
        if compiler is not None:
            compiler.cycle(force=True)
            for number in range(4):
                trained = phase(f'learn-{number}', 8)
                cycle = compiler.cycle()
                local_queue = sum(w.get('ordinary_queued_write', 0)
                                  for w in trained['kd_evidence']['workers'])
                if not cycle['claim_rows'] and (trained['generated']['jit_completions']
                        if args.delegation == 'on' else local_queue > 0):
                    break
            else:
                raise ValueError('bounded training lacks the requested foreign-completion or contended local witness')
        # Recorder changes leave each module load's selected delegation mode fixed.
        # Every switch and claim occurs between fully returned worker phases.
        for label, count, timed, recorder in plan:
            if timed and args.timing_round and not label.startswith(f'timed-r{args.timing_round}-'):
                continue
            checked = phase(label, count, duration=2000 if timed else 0,
                            timed=timed, recorder=recorder)
            if compiler is not None:
                cycle = compiler.cycle(claim_only=True)
                require(not cycle['claim_rows'] and not cycle['published'], 'fixed image acquired new feedback')
                if not timed and count > 1 and recorder == 'on' and args.delegation == 'on':
                    require(checked['generated']['jit_completions'] > 0,
                            'contended functional phase has no completed generated body')
        if compiler is not None:
            row['shutdown'] = compiler.close(item['signed_sha256'])
            with open(DEVICE, 'rb', buffering=0) as device:
                fcntl.ioctl(device, DESTROY)
        if args.backend == 'tclock':
            # End the provider's object pointer before freeing the workload.
            (tc_params / 'target_lock').write_text('0')
        command('unload-workload', ['/usr/sbin/rmmod', 'kd_nano'])
        if args.backend == 'tclock':
            command('unload-tclock', ['/usr/sbin/rmmod', provider_name])
        fault_check('dmesg-final')
        require(not Path(DEVICE).exists() and not Path('/dev/kd_nano_source').exists(), 'device remains after unload')
        require(int(Path('/proc/sys/kernel/tainted').read_text()) == 4096, 'kernel taint changed')
        row['status'] = 'FUNCTIONAL_PASS' if args.stage == 'functional' else 'TIMING_COMPLETE'
        save(args.output / 'result.json', row)
        return 0
    except BaseException as error:
        row.update(status='FAILED_OR_INCOMPLETE_RETAINED', error=repr(error))
        save(args.output / 'result.json', row)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
