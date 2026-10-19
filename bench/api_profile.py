#!/usr/bin/env python3
"""Guest-only, unscored function profiles for taskname and xattr tail n16/n128.

Run from the frozen guest checkout after the recovery snapshot and idle checks:
  python3 bench/api_profile.py --output /root/kdlock-evidence/10.176.26.71/bench/api-profile-NEW
For a standalone copy, select the frozen checkout with --source-root PATH.
Defaults: all three backends, 16/60 workers, one diagnostic repetition, 2 seconds,
collector 63, preparation with 16 workers and at most 8 waves. Ordinary runner
payloads, capture, admission, completion checks and teardown remain unchanged.

Function profiling changes cost and can change the admitted/delegated fraction.
These observations have no throughput score. Each function's inclusive timing
may contain other selected functions; timings must never be added together.
Counts include all CPUs/tasks during each measure method, including its control
reads and client startup/checks, but exclude preparation, warmup and teardown.
The explicit ordinary-C allowlist excludes every combiner, dispatcher, wrapper,
context switch, borrowed-stack entry, generated body and assembly return path.
Absent/inlined/notrace functions are recorded, never made traceable forcibly.

Adapted from the recorded rwsem profiling harness; requires Linux ftrace function
profiling and function-graph support. Existing tracing configuration is never
repurposed. Previous trace_stat contents are saved but cannot be restored because
those files are read-only; all writable controls must return to their exact state.
"""
import argparse
from collections import defaultdict
import contextlib
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TRACE = Path('/sys/kernel/tracing')
GROUPS = {
    'source_residency': ('kd_source_pin_target', 'kd_source_pin', 'kd_source_piece',
                         '__module_address'),
    'service_boundary': ('kd_jit_string_prepare', 'copy_from_kernel_nofault',
                         'kd_hostcall_invoke_strcmp', 'kd_hostcall_invoke_strscpy_pad'),
    'frame_checks': ('kd_exec_frame_validate', 'kd_exec_frame_can_borrow_locks',
                     'kd_exec_frame_save_continuation'),
    'original_helper': ('strcmp', 'strscpy_pad', 'strscpy'),
    'native_lock': ('_raw_spin_lock', '_raw_spin_unlock', '_raw_spin_lock_irqsave',
                    '_raw_spin_unlock_irqrestore', 'queued_spin_lock_slowpath',
                    'native_queued_spin_lock_slowpath'),
}
CONTROLS = ('current_tracer', 'function_profile_enabled', 'set_ftrace_filter',
            'set_ftrace_notrace', 'set_graph_function', 'set_graph_notrace',
            'set_ftrace_pid', 'set_ftrace_notrace_pid', 'tracing_on', 'tracing_cpumask',
            'trace_options', 'tracing_thresh', 'events/enable', 'enabled_functions')
DEFAULT_LISTS = ('set_ftrace_filter', 'set_ftrace_notrace', 'set_graph_function',
                 'set_graph_notrace', 'set_ftrace_pid', 'set_ftrace_notrace_pid')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def active_lines(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith('#') and line.strip() != 'no pid']


def state():
    return {name: (TRACE / name).read_text() for name in CONTROLS if (TRACE / name).exists()}


def preflight(*, xattr_adapter=False):
    current = state()
    for name in ('current_tracer', 'function_profile_enabled', 'set_ftrace_filter',
                 'set_ftrace_notrace', 'set_graph_function', 'set_graph_notrace', 'events/enable'):
        require(name in current, 'missing required tracing control: ' + name)
    require(current['current_tracer'].strip() == 'nop', 'an existing tracer is active; leave it unchanged')
    require(current['function_profile_enabled'].strip() == '0', 'an existing profiler is active')
    require(current['events/enable'].strip() == '0', 'existing trace events are enabled')
    require(all(not active_lines(current.get(name, '')) for name in DEFAULT_LISTS),
            'non-default function/graph/PID filter; leave existing tracing unchanged')
    callbacks = active_lines(current.get('enabled_functions', ''))
    if xattr_adapter:
        # The measured syscall runner owns this IPMODIFY callback. Its ftrace
        # operation has a private filter, separate from the function profiler's
        # filter. Preserve the complete callback record and require it unchanged
        # after profiling; never remove or reconfigure the adapter's callback.
        require(Path('/sys/module/real_api').is_dir(), 'xattr adapter is not loaded')
        require(len(callbacks) == 1 and
                re.match(r'^simple_xattr_get\s+\(1\)(?:\s|$)', callbacks[0]),
                'xattr profiling requires only its one simple_xattr_get callback')
    else:
        require(not callbacks, 'existing ftrace callbacks are active')
    require(float(current.get('tracing_thresh', '0').strip()) == 0,
            'a tracing threshold would hide function rows')
    require(Path('/proc/sys/kernel/ftrace_enabled').read_text().strip() == '1',
            'global ftrace is disabled; do not change it implicitly')
    for instance in (TRACE / 'instances').glob('*'):
        if not instance.is_dir():
            continue
        require((instance / 'current_tracer').read_text().strip() == 'nop' and
                (instance / 'events/enable').read_text().strip() == '0',
                'another tracing instance is active: ' + instance.name)
    return current


def profile_files(destination, required=True):
    destination.mkdir()
    paths = sorted((TRACE / 'trace_stat').glob('function[0-9]*'))
    require(paths or not required, 'no per-CPU function profile files')
    hashes = {}
    for path in paths:
        target = destination / path.name
        target.write_text(path.read_text())
        hashes[path.name] = sha(target)
    return hashes


def select_functions(include_native_locks):
    available = (TRACE / 'available_filter_functions').read_text()
    symbols = {line.split()[0] for line in available.splitlines() if line.split()}
    selected, missing, categories = [], [], {}
    wanted = {category: bases for category, bases in GROUPS.items()
              if category != 'native_lock' or include_native_locks}
    for category, bases in wanted.items():
        for base in bases:
            matches = sorted(name for name in symbols if name == base or
                             re.fullmatch(re.escape(base) + r'\.(?:isra|constprop|part)\.\d+', name))
            if not matches:
                missing.append(base)
            for name in matches:
                selected.append(name)
                categories[name] = category
    selected = sorted(set(selected))
    require(selected, 'none of the explicitly allowed ordinary C functions is traceable')
    # Linux 6.1 trace_stat prints only the first 30 function-name characters.
    require(len({name[:30] for name in selected}) == len(selected),
            'selected functions collide in trace_stat name truncation')
    return available, selected, missing, categories


def aggregate(folder, selected, categories):
    names = {name[:30]: name for name in selected}
    by_function = defaultdict(lambda: dict(hits=0, reported_total_us=0.0, cpus=[]))
    per_cpu = []
    unknown = []
    for name in selected:
        by_function[name]
    for path in sorted(folder.glob('function[0-9]*')):
        cpu = int(path.name.removeprefix('function'))
        for line in path.read_text().splitlines():
            match = re.match(r'^\s*(\S+)\s+(\d+)(?:\s+(.*))?$', line)
            if not match:
                continue
            short, hits, timing = match[1], int(match[2]), match[3] or ''
            if short not in names:
                unknown.append(dict(cpu=cpu, line=line))
                continue
            name = names[short]
            durations = re.findall(r'(\d+(?:\.\d+)?)\s*(ns|us|ms|s)\b', timing)
            total_us = None
            if durations:
                value, unit = durations[0]
                total_us = float(value) * {'ns': .001, 'us': 1., 'ms': 1000., 's': 1e6}[unit]
            per_cpu.append(dict(cpu=cpu, function=name, category=categories[name], hits=hits,
                                reported_total_us=total_us, raw_timing_columns=timing))
            item = by_function[name]
            item['hits'] += hits
            item['cpus'].append(cpu)
            if total_us is not None:
                item['reported_total_us'] += total_us
    # Preserve unexpected rows before refusing: do not silently accept a broad
    # profile because the target kernel interpreted the filter differently.
    return dict(functions=[dict(function=name, category=categories[name], **values)
                            for name, values in sorted(by_function.items(),
                                                       key=lambda item: -item[1]['hits'])],
                per_cpu=per_cpu, unexpected_rows=unknown,
                timing_note='Per-function sums across CPUs only; nested function times overlap. '
                            'See captured graph-time and sleep-time options. Never sum different functions.')


class Profiler:
    def __init__(self, session):
        self.session = session
        self.path = session.path / 'function-profile'
        self.path.mkdir()
        self.before = None
        self.armed = False
        self.filter_attempted = False
        self.filter_verified = False
        self.selected = []
        self.categories = {}
        self.xattr_adapter = session.record.get('kind') == 'xattr'

    def start(self):
        require(sha(Path(__file__)) == self.session.record['profiler_sha256'],
                'diagnostic harness changed during the run')
        save(self.path / 'controls-observed.json', state())
        self.before = preflight(xattr_adapter=self.xattr_adapter)
        save(self.path / 'controls-before.json', self.before)
        save(self.path / 'previous-profile-sha256.json',
             profile_files(self.path / 'previous-profile', required=False))
        available, self.selected, missing, self.categories = select_functions(
            self.session.record['profile_native_locks'])
        (self.path / 'available-filter-functions.txt').write_text(available)
        save(self.path / 'selection.json', dict(selected=self.selected, missing_or_notrace=missing,
            categories=self.categories, source='available_filter_functions after benchmark module load',
            excludes='No explicit combiner, assembly switch, wrapper or borrowed-stack entry functions'))
        # Recheck before any mutation, after the read-only snapshots.
        require(preflight(xattr_adapter=self.xattr_adapter) == self.before,
                'tracing controls changed before profiler start')
        self.filter_attempted = True
        (TRACE / 'set_ftrace_filter').write_text('\n'.join(self.selected) + '\n')
        filtered = (TRACE / 'set_ftrace_filter').read_text()
        (self.path / 'filter-readback.txt').write_text(filtered)
        require({line.split()[0] for line in active_lines(filtered)} == set(self.selected),
                'function filter readback differs')
        self.filter_verified = True
        self.armed = True  # We own any effect of this write, including a partial failure.
        (TRACE / 'function_profile_enabled').write_text('1\n')
        require((TRACE / 'function_profile_enabled').read_text().strip() == '1', 'profiler did not enable')
        save(self.path / 'controls-active.json', state())

    def finish(self):
        errors = []
        try:
            if self.armed:
                # This disables only the profiler that this instance enabled.
                # It never changes current_tracer, tracing_on, events or options.
                (TRACE / 'function_profile_enabled').write_text('0\n')
                require((TRACE / 'function_profile_enabled').read_text().strip() == '0',
                        'owned profiler did not stop')
                self.armed = False
                save(self.path / 'raw-profile-sha256.json', profile_files(self.path / 'raw-profile'))
                report = aggregate(self.path / 'raw-profile', self.selected, self.categories)
                save(self.path / 'aggregate.json', report)
                if report['unexpected_rows']:
                    errors.append('profile contains functions outside the selected filter')
        except BaseException as error:
            errors.append('profiler capture/stop: ' + repr(error))
        finally:
            if self.filter_attempted:
                try:
                    now = state()
                    expected = {key: value for key, value in self.before.items()
                                if key not in ('set_ftrace_filter', 'function_profile_enabled', 'enabled_functions')}
                    require(all(now.get(key) == value for key, value in expected.items()),
                            'other tracing controls changed; do not overwrite another user configuration')
                    actual = {line.split()[0] for line in active_lines(now['set_ftrace_filter'])}
                    require(actual == set(self.selected) or not actual or
                            (not self.filter_verified and actual <= set(self.selected)),
                            'function filter changed externally; leave it untouched')
                    require(now['function_profile_enabled'].strip() == '0',
                            'profiler remains active; do not broaden its filter')
                    (TRACE / 'set_ftrace_filter').write_text('\n')
                    require(preflight(xattr_adapter=self.xattr_adapter) == self.before,
                            'tracing controls were not restored exactly')
                except BaseException as error:
                    errors.append('filter restore: ' + repr(error))
            save(self.path / 'restore.json', dict(restored=not errors, errors=errors, controls_after=state()))
        return errors


def records(out):
    plan_path = out / 'plan.json'
    if not plan_path.exists():
        return []
    result = []
    for spec in json.loads(plan_path.read_text()):
        path = out / spec['name'] / 'session.json'
        result.append(json.loads(path.read_text()) if path.exists() else
                      dict(spec, execution_status='NOT_RUN', drained=False))
    return result


def diagnostic_report(out):
    """Keep raw measurements and status evidence, without scoring throughput."""
    save(out / 'records.json', records(out))
    save(out / 'summary.json', [])
    parity = dict(status='DIAGNOSTIC', criterion='Function profiling enabled; no performance score', points=[])
    save(out / 'parity.json', parity)
    return parity


def observations(out, groups):
    rows = []
    for group in groups:
        for record in records(out / group):
            folder = out / group / record['name'] / 'function-profile'
            if not (folder / 'aggregate.json').exists():
                continue
            completed = record.get('measurement', {}).get('completed', 0)
            restored = json.loads((folder / 'restore.json').read_text())['restored']
            valid = (record.get('execution_status') == 'OK' and record.get('drained') is True
                     and restored and completed > 0)
            for function in json.loads((folder / 'aggregate.json').read_text())['functions']:
                rows.append(dict(case=group if group == 'taskname' else
                                 'xattr-tail-n' + str(record['entries']),
                    session=record['name'], backend=record['arm'], threads=record['threads'],
                    repeat=record['repeat'], jit_status=record.get('jit_status'),
                    jit_bodies=record.get('jit_bodies'), jit_completions=record.get('jit_completions'),
                    valid_observation=valid, completed=completed, function=function['function'],
                    category=function['category'], hits=function['hits'],
                    hits_per_completed_op=function['hits'] / completed if valid else None,
                    reported_total_us=function['reported_total_us']))
    save(out / 'function-observations.json', rows)
    if rows:
        with (out / 'function-observations.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def import_runner(name, relative):
    path = ROOT / relative
    # Match normal script execution: real_api imports its local evidence module.
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT,
                        help='frozen guest checkout; allows the profiler itself to run from /tmp')
    parser.add_argument('--cases', nargs='+', choices=('taskname', 'xattr16', 'xattr128'),
                        default=['taskname', 'xattr16', 'xattr128'])
    parser.add_argument('--backends', nargs='+', choices=('native', 'tclock', 'kdlock'),
                        default=['native', 'tclock', 'kdlock'])
    parser.add_argument('--threads', nargs='+', type=int, choices=(16, 60), default=[16, 60])
    parser.add_argument('--repeats', type=int, choices=(1, 3), default=1,
                        help='diagnostic repetitions; neither setting permits throughput scores')
    parser.add_argument('--include-native-locks', action='store_true',
                        help='also profile the explicit native raw-lock list; adds background traffic')
    parser.add_argument('--timeout-seconds', type=int, default=3600)
    parser.add_argument('--kernel-source', type=Path, default=Path('/root/linux-6.1.159-kdclobber2'))
    parser.add_argument('--kernel-baseline', type=Path,
                        default=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))
    args = parser.parse_args()
    ROOT = args.source_root.resolve()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            str(ROOT).startswith('/root/') and ROOT.is_dir() and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'run only in the confirmed recovery guest from its frozen checkout')
    require(all((ROOT / path).is_file() for path in
                ('bench/rwlock_compare/run.py', 'bench/real_api/run.py', 'include/kd_source_api.h')),
            'source root is not a complete KD checkout')
    require(60 <= args.timeout_seconds <= 7200, 'use a bounded 60..7200 second deadline')
    for values in (args.cases, args.backends, args.threads):
        require(len(values) == len(set(values)), 'duplicate diagnostic plan dimension')
    out = args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT), 'use a new external diagnostic directory')
    config_path = args.kernel_source / '.config'
    config = config_path.read_text().splitlines()
    for setting in ('CONFIG_DYNAMIC_FTRACE=y', 'CONFIG_FUNCTION_PROFILER=y', 'CONFIG_FUNCTION_GRAPH_TRACER=y'):
        require(setting in config, 'filtered function profiling requires ' + setting)

    # No subprocess inherits this advisory lock. Other profiling tools still
    # have to be excluded operationally; preflight also refuses active tracing.
    lock = open('/tmp/kd-api-function-profile.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rw = import_runner('kd_api_profile_rw_runner', 'bench/rwlock_compare/run.py')
    api = import_runner('kd_api_profile_syscall_runner', 'bench/real_api/run.py')
    rw.idle()
    for module in ('real_api', 'tclock_mutex_backend_km'):
        require(not Path('/sys/module', module).exists(), 'existing module: ' + module)
    initial_controls = preflight()
    out.mkdir(parents=True)
    shutil.copyfile(Path(__file__), out / 'api_profile.py')
    harness_sha = sha(Path(__file__))
    save(out / 'diagnostic.json', dict(diagnostic=True, score_eligible=False,
        scope='All CPUs/tasks during each measure method, including control reads and client checks; '
              'preparation, helper learning, warmup and cleanup are excluded.',
        script_sha256=harness_sha, kernel_config_sha256=sha(config_path), argv=sys.argv,
        source_root=str(ROOT), tracing_root=str(TRACE), kernel_release=os.uname().release,
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], requested_repetitions=args.repeats,
        include_native_locks=args.include_native_locks,
        notes=['Do not pool profiled timings with the main benchmark.',
               'Nested function times overlap and must not be added together.',
               'Counts include background/control work; they do not establish ownership.',
               'Function profiling may change admission and returned-body proportions.',
               'Missing/inlined/notrace functions are recorded, not forcibly instrumented.',
               'All writable trace controls are restored; previous read-only profile rows are saved only.',
               'Taskname validates its ordinary three-repeat plan, then selects the requested diagnostic repeats.']))
    save(out / 'controls-initial.json', initial_controls)
    originals = dict(rw_measure=rw.RWSession.measure, rw_plan=rw.make_plan, rw_report=rw.report,
                     api_measure=api.SyscallSession.measure, api_plan=api.make_plan)
    commands = []
    finished_groups = []

    def mark_plan(plan):
        for row in plan:
            row.update(diagnostic=True, diagnostic_kind='filtered-function-profiler',
                       score_eligible=False, profiler_sha256=harness_sha,
                       profile_native_locks=args.include_native_locks,
                       diagnostic_requested_repetitions=args.repeats)
        return plan

    def rw_plan(parsed):
        return mark_plan([row for row in originals['rw_plan'](parsed) if row['repeat'] < args.repeats])

    def api_plan(parsed):
        return mark_plan(originals['api_plan'](parsed))

    def wrapped_measure(original, failure_type):
        def measure(session):
            profiler = Profiler(session)
            session.record.update(diagnostic=True, score_eligible=False,
                                  function_profile=str(profiler.path.relative_to(session.path)))
            session.save()
            try:
                try:
                    profiler.start()
                except (RuntimeError, OSError) as error:
                    raise failure_type('PROFILE_PREPARATION_FAILED', str(error)) from error
                return original(session)
            finally:
                errors = profiler.finish()
                if errors:
                    raise failure_type('TRACING_RESTORE_FAILED', '; '.join(errors), unsafe=True)
        return measure

    def interrupted(signum, frame):
        # A timeout does not prove worker drain. Restore tracing in the measure
        # wrapper's finally, but retain runner/module state for recovery review.
        raise KeyboardInterrupt('bounded diagnostic interrupted by signal ' + str(signum))

    handlers = {number: signal.signal(number, interrupted)
                for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
    rw.RWSession.measure = wrapped_measure(originals['rw_measure'], rw.Failure)
    api.SyscallSession.measure = wrapped_measure(originals['api_measure'], api.Failure)
    rw.make_plan, rw.report, api.make_plan = rw_plan, diagnostic_report, api_plan
    signal.alarm(args.timeout_seconds)
    prior_argv = sys.argv
    try:
        common = ['--backends', *args.backends, '--threads', *map(str, args.threads),
                  '--collector-cpu', '63', '--duration-ms', '2000', '--helper-workers', '16',
                  '--helper-waves', '8', '--kernel-source', str(args.kernel_source),
                  '--kernel-baseline', str(args.kernel_baseline)]
        jobs = []
        if 'taskname' in args.cases:
            jobs.append(('taskname', rw, common + ['--lock-kind', 'spin', '--workloads', 'taskname',
                '--write-percent', '0', '--repeats', '3', '--post-work-rounds', '4',
                '--spin-entry-ratio-limit', '2', '--delegate', 'on', '--peak-window-ms', '300',
                '--peak-settle-ms', '300', '--sample-ms', '10',
                '--cpus', *map(str, range(max(args.threads)))]))
        entries = [case.removeprefix('xattr') for case in args.cases if case.startswith('xattr')]
        if entries:
            jobs.append(('xattr', api, common + ['--kinds', 'xattr', '--queries', 'tail',
                '--entries', *entries, '--value-size', '64', '--repeats', str(args.repeats),
                '--warmup', '48000', '--warmup-ms', '1000',
                '--cpus', ','.join(map(str, range(max(args.threads))))]))
        for group, runner, argv in jobs:
            rw.idle()
            require(preflight() == initial_controls, 'tracing controls changed between runner groups')
            argv = argv + ['--output', str(out / group)]
            receipt = dict(group=group, argv=argv, diagnostic=True, score_eligible=False,
                           started_ns=time.monotonic_ns())
            commands.append(receipt)
            save(out / 'commands.json', commands)
            try:
                sys.argv = [str(Path(runner.__file__)), *argv]
                with (out / (group + '.log')).open('w') as log, \
                        contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    rc = runner.main(argv) if runner is rw else runner.main()
                receipt['returncode'] = 0 if rc is None else rc
            finally:
                receipt['finished_ns'] = time.monotonic_ns()
                save(out / 'commands.json', commands)
                if (out / group).exists():
                    diagnostic_report(out / group)
            require(receipt['returncode'] == 0, 'diagnostic failed; preserve its session and inspect the log')
            rw.idle()
            require(preflight() == initial_controls, 'tracing controls were not restored')
            group_records = records(out / group)
            require(group_records and all(row.get('execution_status') == 'OK' and row.get('drained') is True
                                          for row in group_records), 'not every diagnostic session drained')
            finished_groups.append(group)
        observations(out, finished_groups)
        save(out / 'result.json', dict(completed=True, diagnostic=True, score_eligible=False,
            tracing_restored=True, guest_idle=True, sessions=sum(len(records(out / group))
            for group in finished_groups), commands=commands))
    except BaseException as error:
        save(out / 'exception.json', dict(error=repr(error), diagnostic=True, score_eligible=False,
                                         commands=commands, finished_groups=finished_groups))
        observations(out, [name for name in ('taskname', 'xattr') if (out / name).exists()])
        raise
    finally:
        signal.alarm(0)
        sys.argv = prior_argv
        rw.RWSession.measure, rw.make_plan, rw.report = (originals['rw_measure'], originals['rw_plan'],
                                                       originals['rw_report'])
        api.SyscallSession.measure, api.make_plan = originals['api_measure'], originals['api_plan']
        for number, handler in handlers.items():
            signal.signal(number, handler)
        save(out / 'controls-final.json', state())
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
