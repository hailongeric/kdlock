#!/usr/bin/env python3
"""VM-only, period-weighted analysis of six retained flat cycles:k profiles.

Read existing perf script/report output; never run perf or any measured code.
Keep each source version and worker count separate. All figures are diagnostic.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re


ARMS = ('compact-bucket', 'precompact-256', 'compact-rcu')
SAMPLE = re.compile(
    r'^\s*(?P<comm>.+?)\s+(?P<pid>\d+)\s*/\s*(?P<tid>\d+)\s+'
    r'\[(?P<cpu>\d+)\]\s+(?P<time>\d+\.\d+):\s+'
    r'(?P<period>\d+)\s+(?P<event>cycles:k):\s+'
    r'(?P<ip>(?:0x)?[0-9a-fA-F]+)\s+(?P<symbol>.*?)\s+\((?P<dso>.*)\)\s*$')
LOST = re.compile(r'^\s*#\s*Total Lost Samples:\s*([\d,]+)\s*$', re.M)
EVENT = re.compile(r"^\s*#\s*Samples:\s*(.*?)\s+of event '([^']+)'\s*$", re.M)
PERIOD_TOTAL = re.compile(r'^\s*#\s*Event count \(approx\.\):\s*([\d,]+)\s*$', re.M)
FOCUS = {
    'queued_spin_lock_symbols': r'(?:^|_)queued_spin_lock(?:_|$)',
    'raw_spin_helpers': r'^(?:_raw|__raw)_spin_',
    'aux_try_ref': r'^kd_mutex_aux_try_ref$',
    'aux_put': r'^kd_mutex_aux_put$',
    'combiner_active': r'^kd_mutex_combiner_active$',
    'aux_all': r'^kd_mutex_aux_',
    'lock_text_symbols': r'__lock_text_|\.lock\.text',
    'mutex_slowpath': r'^__kd_mutex_lock_slowpath$',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def summary(period, samples, denominator):
    return dict(observed_sum_period=period, samples=samples,
                percent_of_denominator=100 * period / denominator if denominator else None)


def normalize_symbol(symbol):
    # Retain raw labels in tables. Only focus filters ignore compiler suffixes
    # and a displayed instruction offset; no inferred call-graph attribution.
    return re.sub(r'\.(?:constprop|isra|part)\.\d+$', '', symbol.split('+0x', 1)[0])


def analyze(base, arm, record, source_commit, source_identity):
    folder = base / arm / 'profile' / record['name']
    raw_path, report_path = folder / 'perf-samples.txt', folder / 'perf-report.txt'
    text, report = raw_path.read_text(), report_path.read_text()
    periods, counts = Counter(), Counter()
    cpu_periods, cpu_counts = Counter(), Counter()
    pids, tids, events = set(), set(), set()
    errors, loss_records = [], []
    headers = blanks = sample_count = nonempty = 0
    timestamps = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            blanks += 1
            continue
        nonempty += 1
        if line.lstrip().startswith('#'):
            headers += 1
            continue
        if 'PERF_RECORD_LOST' in line:
            loss_records.append(dict(line=number, text=line))
            continue
        match = SAMPLE.fullmatch(line)
        if not match:
            errors.append(dict(line=number, text=line, reason='unrecognized nonempty sample line'))
            continue
        row = match.groupdict()
        period = int(row['period'])
        if not period or not row['symbol'] or not row['dso']:
            errors.append(dict(line=number, text=line, reason='zero period or missing symbol/DSO'))
            continue
        comm = row['comm'].strip()
        key = (comm, row['symbol'], row['dso'])
        periods[key] += period
        counts[key] += 1
        cpu_key = (comm, int(row['cpu']))
        cpu_periods[cpu_key] += period
        cpu_counts[cpu_key] += 1
        pids.add(int(row['pid'])); tids.add(int(row['tid'])); events.add(row['event'])
        timestamps.append(row['time'])
        sample_count += 1
    require(nonempty == sample_count + headers + len(loss_records) + len(errors),
            f'{folder}: internal line accounting differs')
    all_period = sum(periods.values())
    worker_period = sum(period for key, period in periods.items() if key[0] == 'sc_worker')
    worker_count = sum(n for key, n in counts.items() if key[0] == 'sc_worker')
    lost_values = [int(v.replace(',', '')) for v in LOST.findall(report)]
    event_headers = [dict(displayed_samples=n, event=e) for n, e in EVENT.findall(report)]
    approx_counts = [int(v.replace(',', '')) for v in PERIOD_TOTAL.findall(report)]
    reasons = []
    if errors:
        reasons.append('unparsed sample text')
    if loss_records or lost_values != [0]:
        reasons.append('sample loss present or report loss count missing/ambiguous')
    if len(event_headers) != 1 or event_headers[0]['event'] != 'cycles:k' or events != {'cycles:k'}:
        reasons.append('event identity differs or missing')
    if not all_period or not worker_period:
        reasons.append('missing all-kernel or sc_worker sample denominator')
    if not (record.get('execution_status') == 'OK' and record.get('drained') is True
            and record.get('score_eligible') is False and record.get('diagnostic') is True
            and record.get('perf_record') is True and record.get('pmu') is False
            and record.get('jit_acceptance') == 'PASS' and record.get('jit_bodies', 0) > 0):
        reasons.append('profile session validity/instrumentation differs')
    symbols = defaultdict(lambda: [0, 0, 0, 0])
    commands = defaultdict(lambda: [0, 0])
    raw_rows = []
    for key in sorted(periods, key=lambda k: (-periods[k], k)):
        comm, symbol, dso = key
        period, n = periods[key], counts[key]
        worker = comm == 'sc_worker'
        raw_rows.append(dict(comm=comm, symbol=symbol, dso=dso,
                             all_kernel=summary(period, n, all_period),
                             sc_worker=summary(period if worker else 0, n if worker else 0, worker_period)))
        bucket = symbols[symbol, dso]
        bucket[0] += period; bucket[1] += n
        if worker:
            bucket[2] += period; bucket[3] += n
        commands[comm][0] += period; commands[comm][1] += n
    symbol_rows = [dict(symbol=symbol, dso=dso,
                        all_kernel=summary(values[0], values[1], all_period),
                        sc_worker=summary(values[2], values[3], worker_period))
                   for (symbol, dso), values in sorted(symbols.items(), key=lambda item: (-item[1][0], item[0]))]
    focus = {}
    for name, expression in FOCUS.items():
        matched = [(key, value) for key, value in symbols.items()
                   if re.search(expression, normalize_symbol(key[0]))]
        sums = [sum(values[i] for _, values in matched) for i in range(4)]
        focus[name] = dict(symbol_regex=expression, matched_symbols=[dict(symbol=k[0], dso=k[1]) for k, _ in matched],
                           all_kernel=summary(sums[0], sums[1], all_period),
                           sc_worker=summary(sums[2], sums[3], worker_period))
    files = ('perf.data', 'perf-samples.txt', 'perf-report.txt', 'session.json', 'kallsyms', 'modules')
    missing = [name for name in files if not (folder / name).is_file()]
    if missing:
        reasons.append('missing frozen profile artifacts: ' + ', '.join(missing))
    return dict(arm=arm, source_commit=source_commit, source_identity=source_identity,
                name=record['name'], threads=record['threads'], repeat=record['repeat'],
                profile_path=str(folder.relative_to(base)), score_eligible=False,
                complete=not reasons, issues=reasons, event='cycles:k',
                sampling_frequency_hz=199, caller_shell=record.get('caller_shell'),
                source_lock_bytes=record.get('layout', {}).get('lock_bytes'),
                parsed_sample_lines=sample_count, nonempty_lines=nonempty,
                header_lines=headers, blank_lines=blanks, parse_errors=errors,
                lost_event_lines=loss_records, report_lost_samples=lost_values,
                report_event_headers=event_headers, report_approx_event_counts=approx_counts,
                report_approx_count_minus_observed_sum_period=(approx_counts[0] - all_period)
                    if len(approx_counts) == 1 else None,
                denominator_all_kernel=dict(observed_sum_period=all_period, samples=sample_count),
                denominator_sc_worker=dict(observed_sum_period=worker_period, samples=worker_count),
                observed_pid_count=len(pids), observed_tid_count=len(tids),
                first_sample_time=timestamps[0] if timestamps else None,
                last_sample_time=timestamps[-1] if timestamps else None,
                commands=[dict(comm=comm, **summary(v[0], v[1], all_period))
                          for comm, v in sorted(commands.items(), key=lambda item: (-item[1][0], item[0]))],
                cpus=[dict(comm=comm, cpu=cpu, **summary(cpu_periods[comm, cpu], cpu_counts[comm, cpu],
                          worker_period if comm == 'sc_worker' else all_period),
                           denominator='sc_worker' if comm == 'sc_worker' else 'all_kernel')
                      for comm, cpu in sorted(cpu_periods)],
                symbols=symbol_rows, comm_symbols=raw_rows, focus=focus,
                input_sha256={n: digest(folder / n) for n in files if (folder / n).is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(os.uname().release == '6.1.159-kdclobber2', 'run only in the recovery VM')
    rows, inputs = [], []
    for arm in ARMS:
        folder = args.base / arm / 'profile'
        records_path = folder / 'records.json'
        records = read(records_path)
        require(len(records) == 2 and {(r['threads'], r['repeat']) for r in records} == {(8, 0), (60, 0)},
                f'{folder}: expected exactly two profiles, eight and sixty workers')
        require(all(r.get('arm') == 'kdlock' and r.get('workload') == 'cacheline'
                    and r.get('cachelines') == 8 and r.get('lock_kind') == 'mutex' for r in records),
                f'{folder}: unexpected profile workload/protocol')
        command_path = args.base / arm / 'profile-command.json'
        command = read(command_path)
        require(command.get('version') == arm and command.get('source_commit'), f'{arm}: missing source version receipt')
        source_path = folder / 'source-sha256.json'
        source = read(source_path)
        source_identity = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        inputs.append(dict(arm=arm, source_commit=command['source_commit'], source_identity=source_identity,
                           records_sha256=digest(records_path), source_manifest_sha256=digest(source_path),
                           command_sha256=digest(command_path)))
        rows.extend(analyze(args.base, arm, r, command['source_commit'], source_identity) for r in records)
    report = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(),
                  complete=all(r['complete'] for r in rows), profiles=rows, inputs=inputs,
                  notes=[
                      'These six diagnostic profiles are excluded from plain throughput scoring; source versions and worker counts are never pooled.',
                      'Weight is the observed cycles:k sample period, not one vote per sample. All-kernel means all retained kernel-only samples in the profiled client/process tree, not all CPUs system-wide.',
                      'The sc_worker denominator contains only samples whose recorded comm is exactly sc_worker. Symbol/DSO rows retain both all-kernel and worker percentages.',
                      'Each nonempty perf-script line must be a sample, a # header, or an explicitly retained loss event. Unrecognized lines or missing/nonzero loss counts make the report incomplete.',
                      'Focus filters can overlap (for example aux_put is included in aux_all), so their percentages must not be added as disjoint categories.',
                      'Flat instruction-pointer samples have skid and no call graph. Inlined operations can be charged to enclosing symbols; lock-text labels do not identify their caller or lock.',
                      'Observed period sums are sampling weights, not elapsed time or exact cycle cost per operation. Profile percentages do not establish a throughput gain.',
                      'Artifacts and source manifests are hash-bound here; the separate comparison report verifies frozen source snapshots and session validity.',
                  ])
    out = args.output or args.base / 'profile-analysis.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(complete=report['complete'], profiles=len(rows),
                          parsed_samples=sum(r['parsed_sample_lines'] for r in rows), output=str(out))))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
