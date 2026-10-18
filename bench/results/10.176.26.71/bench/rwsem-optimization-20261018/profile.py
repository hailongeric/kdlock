#!/usr/bin/env python3
"""Guest-only, unscored function profiling around RWSession.measure.

Example (after the normal recovery snapshot/idle checks):
  python3 profile.py --output /mnt/kdlock-builds/rwsem-profile-NEW
Optional --rwlock-reference adds separate Native/TCLock spinning-rwlock runs.
No runner file is edited. Three timed repetitions use c01, 60 workers, 20% writes.
The function-graph profiler changes execution cost: never pool these sessions
with performance measurements. Counts cover all CPUs/background activity during
the measure wrapper, not exclusively benchmark threads. Timings may overlap or
include sleep according to the captured graph-time/sleep-time options.

Linux 6.1 references:
https://docs.kernel.org/6.1/trace/ftrace.html
https://github.com/torvalds/linux/blob/v6.1/kernel/trace/ftrace.c
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
import statistics
import sys
import time


ROOT = Path('/root/host_fs/kdlock')
TRACE = Path('/sys/kernel/tracing')
GROUPS = {
    'kd_rwsem': ('kd_down_read', 'kd_down_read_trylock', 'kd_up_read',
                 'kd_rwsem_delegate_enter', 'kd_rwsem_delegate_exit', 'kd_rwsem_wake',
                 'kd_rwsem_reserve_delegate'),
    'native_rwsem': ('down_read', 'up_read', 'down_write', 'up_write',
                     'rwsem_down_read_slowpath', 'rwsem_down_write_slowpath', 'rwsem_wake',
                     'rwsem_mark_wake', 'rwsem_optimistic_spin', 'rwsem_spin_on_owner'),
    'waitqueue': ('prepare_to_wait_event', 'finish_wait', '__wake_up', '__wake_up_common',
                  '__wake_up_common_lock', 'default_wake_function', 'autoremove_wake_function',
                  'wake_up_process', 'wake_up_q'),
    'scheduler': ('schedule', '__schedule', 'schedule_timeout', 'try_to_wake_up',
                  'ttwu_do_activate', 'ttwu_queue'),
    'raw_spin': ('_raw_spin_lock', '_raw_spin_unlock', '_raw_spin_lock_irqsave',
                 '_raw_spin_unlock_irqrestore', '_raw_spin_lock_irq', '_raw_spin_unlock_irq',
                 'queued_spin_lock_slowpath', 'native_queued_spin_lock_slowpath'),
    'rwlock_reference': ('_raw_read_lock', '_raw_read_unlock', '_raw_write_lock',
                         '_raw_write_unlock', 'queued_read_lock_slowpath',
                         'queued_write_lock_slowpath', 'komb_read_lock', 'komb_read_unlock',
                         'komb_write_lock', 'komb_write_unlock'),
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


def preflight():
    current = state()
    for name in ('current_tracer', 'function_profile_enabled', 'set_ftrace_filter',
                 'set_ftrace_notrace', 'set_graph_function', 'set_graph_notrace', 'events/enable'):
        require(name in current, 'missing required tracing control: ' + name)
    require(current['current_tracer'].strip() == 'nop', 'an existing tracer is active; leave it unchanged')
    require(current['function_profile_enabled'].strip() == '0', 'an existing profiler is active')
    require(current['events/enable'].strip() == '0', 'existing trace events are enabled')
    require(all(not active_lines(current.get(name, '')) for name in DEFAULT_LISTS),
            'non-default function/graph/PID filter; leave existing tracing unchanged')
    require(not active_lines(current.get('enabled_functions', '')), 'existing ftrace callbacks are active')
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


def select_functions(arm, lock_kind):
    available = (TRACE / 'available_filter_functions').read_text()
    symbols = {line.split()[0] for line in available.splitlines() if line.split()}
    selected, missing, categories = [], [], {}
    wanted = {category: bases for category, bases in GROUPS.items()
              if category != 'rwlock_reference' or lock_kind == 'rwlock'}
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
    require(selected and any(categories[name] == 'scheduler' for name in selected) and
            any(categories[name] == 'waitqueue' for name in selected),
            'scheduler/waitqueue functions are not available for the requested profile')
    if arm == 'kdlock' and lock_kind == 'rwsem':
        require({'kd_down_read', 'kd_up_read', 'kd_rwsem_delegate_enter', 'kd_rwsem_delegate_exit'} <=
                set(selected), 'loaded KD rwsem APIs are not traceable')
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

    def start(self):
        self.before = preflight()
        save(self.path / 'controls-before.json', self.before)
        save(self.path / 'previous-profile-sha256.json',
             profile_files(self.path / 'previous-profile', required=False))
        available, self.selected, missing, self.categories = select_functions(
            self.session.record['arm'], self.session.record['lock_kind'])
        (self.path / 'available-filter-functions.txt').write_text(available)
        save(self.path / 'selection.json', dict(selected=self.selected, missing_or_notrace=missing,
            categories=self.categories, source='available_filter_functions after benchmark module load',
            excludes='No explicit combiner, assembly switch, wrapper or borrowed-stack entry functions'))
        # Recheck before any mutation, after the read-only snapshots.
        require(preflight() == self.before, 'tracing controls changed before profiler start')
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
                    require(preflight() == self.before, 'tracing controls were not restored exactly')
                except BaseException as error:
                    errors.append('filter restore: ' + repr(error))
            save(self.path / 'restore.json', dict(restored=not errors, errors=errors, controls_after=state()))
        return errors


def diagnostic_report(out):
    records = []
    for spec in json.loads((out / 'plan.json').read_text()):
        path = out / spec['name'] / 'session.json'
        records.append(json.loads(path.read_text()) if path.exists() else
                       dict(spec, execution_status='NOT_RUN', drained=False))
    save(out / 'records.json', records)
    save(out / 'summary.json', [])
    parity = dict(status='DIAGNOSTIC', criterion='Function profiler enabled; performance scoring disabled', points=[])
    save(out / 'parity.json', parity)
    return parity


def diagnostic_comparison(out):
    """Compare individual function counts, never score profiled throughput."""
    observations = []
    for records_path in sorted(out.glob('*/records.json')):
        for row in json.loads(records_path.read_text()):
            report_path = records_path.parent / row['name'] / 'function-profile/aggregate.json'
            if (row.get('execution_status') != 'OK' or row.get('drained') is not True or
                    not report_path.exists()):
                continue
            completed = row['measurement']['completed']
            require(completed > 0, 'successful profiled session has no completed operations')
            for item in json.loads(report_path.read_text())['functions']:
                observations.append(dict(lock_kind=row['lock_kind'], backend=row['arm'],
                    session=row['name'], repeat=row['repeat'], jit_status=row['jit_status'],
                    completed=completed, function=item['function'], category=item['category'],
                    hits=item['hits'], hits_per_completed_op=item['hits'] / completed,
                    reported_total_us=item['reported_total_us']))
    save(out / 'function-observations.json', observations)
    if observations:
        with (out / 'function-observations.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(observations[0]))
            writer.writeheader()
            writer.writerows(observations)
    groups = defaultdict(list)
    for row in observations:
        groups[(row['lock_kind'], row['backend'], row['jit_status'], row['function'])].append(row)
    summary = []
    for key, rows in sorted(groups.items()):
        counts = [row['hits_per_completed_op'] for row in rows]
        summary.append(dict(lock_kind=key[0], backend=key[1], jit_status=key[2], function=key[3],
            category=rows[0]['category'], repetitions=len(rows),
            median_hits_per_completed_op=statistics.median(counts),
            min_hits_per_completed_op=min(counts), max_hits_per_completed_op=max(counts),
            sessions=[row['session'] for row in rows]))
    save(out / 'function-count-summary.json', summary)
    with (out / 'function-count-summary.md').open('w') as handle:
        handle.write('# Diagnostic function counts\n\n'
            'Function profiling changes timing. These observations are excluded from performance scoring. '
            'Counts include all tasks and CPUs during the measure wrapper, including control reads. '
            'Normalization uses benchmark completed operations, so background activity remains a confounder. '
            'Different JIT execution statuses stay separate. Times from nested functions must not be summed.\n\n'
            '| Lock | Backend | JIT status | Function | Repetitions | Calls/op median [min, max] |\n'
            '|---|---|---|---|---:|---:|\n')
        for row in summary:
            handle.write('| {lock_kind} | {backend} | {jit_status} | `{function}` | {repetitions} | '
                '{median_hits_per_completed_op:.6g} [{min_hits_per_completed_op:.6g}, '
                '{max_hits_per_completed_op:.6g}] |\n'.format(**row))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rwlock-reference', action='store_true')
    parser.add_argument('--backends', nargs='+', choices=('native', 'kdlock'), default=['native', 'kdlock'])
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()
    require(os.geteuid() == 0 and ROOT.is_dir() and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'confirmed recovery guest is required')
    require(60 <= args.timeout_seconds <= 3600, 'use a bounded 60..3600 second deadline')
    require(len(args.backends) == len(set(args.backends)), 'duplicate rwsem backends')
    out = args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT), 'use a new external diagnostic directory')
    config_path = Path('/root/linux-6.1.159-kdclobber2/.config')
    config = config_path.read_text()
    for setting in ('CONFIG_DYNAMIC_FTRACE=y', 'CONFIG_FUNCTION_PROFILER=y', 'CONFIG_FUNCTION_GRAPH_TRACER=y'):
        require(setting in config.splitlines(), 'filtered graph profiling requires ' + setting)
    spec = importlib.util.spec_from_file_location('kd_rwsem_profile_runner', ROOT / 'bench/rwlock_compare/run.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.idle()
    preflight()
    out.mkdir(parents=True)
    shutil.copyfile(Path(__file__), out / 'profile.py')
    save(out / 'diagnostic.json', dict(diagnostic=True, score_eligible=False,
        scope='All CPUs and tasks during RWSession.measure, including client startup and publication/counter reads; '
              'excludes preparation, warmup and cleanup',
        script_sha256=sha(Path(__file__)), kernel_config_sha256=sha(config_path),
        argv=sys.argv, source_root=str(ROOT), tracing_root=str(TRACE),
        kernel_release=os.uname().release, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
        notes=['Do not pool with throughput benchmark sessions.',
               'Function profiling uses return-address instrumentation; absent/notrace symbols are recorded.',
               'Selected kernel calls include background work. Counts are diagnostic observations, not ownership.',
               'Prior function-profile rows are preserved, but trace_stat is read-only and its contents cannot be restored.']))
    original_measure, original_plan, original_report = runner.RWSession.measure, runner.make_plan, runner.report
    commands = []

    def make_plan(parsed):
        plan = original_plan(parsed)
        for row in plan:
            row.update(diagnostic=True, diagnostic_kind='filtered-function-profiler', score_eligible=False)
        return plan

    def measure(session):
        profiler = Profiler(session)
        session.record.update(diagnostic=True, score_eligible=False,
                              function_profile=str(profiler.path.relative_to(session.path)))
        session.save()
        try:
            try:
                profiler.start()
            except (RuntimeError, OSError) as error:
                raise runner.Failure('PROFILE_PREPARATION_FAILED', str(error)) from error
            return original_measure(session)
        finally:
            errors = profiler.finish()
            if errors:
                raise runner.Failure('TRACING_RESTORE_FAILED', '; '.join(errors), unsafe=True)

    def interrupted(signum, frame):
        raise KeyboardInterrupt('bounded diagnostic interrupted by signal ' + str(signum))

    old_handlers = {signum: signal.signal(signum, interrupted)
                    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
    lock = open('/tmp/kd-rwsem-function-profile.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    signal.alarm(args.timeout_seconds)
    runner.RWSession.measure, runner.make_plan, runner.report = measure, make_plan, diagnostic_report
    try:
        modes = [('rwsem', args.backends)]
        if args.rwlock_reference:
            modes.append(('rwlock', ['native', 'tclock']))
        for kind, backends in modes:
            runner.idle()
            argv = ['--lock-kind', kind, '--backends', *backends, '--workloads', 'cacheline',
                    '--cachelines', '1', '--write-percent', '20', '--threads', '60',
                    '--collector-cpu', '63', '--repeats', '3', '--duration-ms', '2000',
                    '--output', str(out / kind)]
            begin = time.monotonic()
            receipt = dict(argv=argv, diagnostic=True, score_eligible=False)
            commands.append(receipt)
            save(out / 'commands.json', commands)
            with (out / (kind + '.log')).open('w') as log, \
                    contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                rc = runner.main(argv)
            receipt.update(returncode=rc, seconds=time.monotonic() - begin)
            save(out / 'commands.json', commands)
            require(rc == 0, 'diagnostic stopped; preserve the failed session and inspect its log')
            runner.idle()
            preflight()
        diagnostic_comparison(out)
        save(out / 'result.json', dict(completed=True, diagnostic=True, score_eligible=False,
                                      tracing_restored=True, guest_idle=True, commands=commands))
    except BaseException as error:
        save(out / 'exception.json', dict(error=repr(error), diagnostic=True, score_eligible=False,
                                          commands=commands))
        raise
    finally:
        signal.alarm(0)
        runner.RWSession.measure, runner.make_plan, runner.report = original_measure, original_plan, original_report
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        lock.close()
        save(out / 'controls-final.json', state())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
