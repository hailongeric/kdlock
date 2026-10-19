#!/usr/bin/env python3
"""VM-only compact, period-weighted flat pipe profile analysis.

Read ARM/profile/pipe. Keep every source/worker cohort separate, explicitly
compare profiled and plain execution shares, and retain capped parse examples.
Sampled symbol offsets are observations subject to skid, never exact cost
counts. ELF instruction inspection remains a separate source-host operation.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re


SAMPLE = re.compile(r'^\s*(?P<comm>.+?)\s+(?P<pid>\d+)\s*/\s*(?P<tid>\d+)\s+'
                    r'\[(?P<cpu>\d+)\]\s+(?P<time>\d+\.\d+):\s+(?P<period>\d+)\s+'
                    r'(?P<event>cycles:k):\s+(?P<ip>(?:0x)?[0-9a-fA-F]+)\s+'
                    r'(?P<symbol>.*?)\s+\((?P<dso>.*)\)\s*$')
LOST = re.compile(r'^\s*#\s*Total Lost Samples:\s*([\d,]+)\s*$', re.M)
EVENT = re.compile(r"^\s*#\s*Samples:\s*(.*?)\s+of event '([^']+)'\s*$", re.M)
PERIOD_TOTAL = re.compile(r'^\s*#\s*Event count \(approx\.\):\s*([\d,]+)\s*$', re.M)
FOCUS = {
    'aux_try_ref': r'^kd_mutex_aux_try_ref$',
    'aux_acquire': r'^kd_mutex_aux_(?:try_ref|find_ref|get|lookup|ref)$',
    'aux_put': r'^kd_mutex_aux_put$',
    'combiner_active': r'^kd_mutex_combiner_active$',
    'outer_retry': r'^kd_mutex_outer_retry$',
    'hint_retry_helpers': r'^kd_mutex_(?:combiner_active|outer_retry)$',
    'aux_all': r'^kd_mutex_aux_',
    'mutex_slowpath': r'^__kd_mutex_lock_slowpath$',
    'mutex_execute_cs': r'^kd_mutex_execute_cs$',
    'physical_lock_unlock': r'^kd_(?:origin_mutex|mutex_local)_(?:lock|unlock)',
}
OFFSET_FOCUS = ('aux_acquire', 'aux_put', 'hint_retry_helpers')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def normalized(symbol):
    return re.sub(r'\.(?:constprop|isra|part)\.\d+$', '', symbol.split('+0x', 1)[0])


def weight(period, count, denominator):
    return dict(observed_sum_period=period, samples=count,
                percent_of_denominator=100 * period / denominator if denominator else None)


def matched(symbol):
    return any(re.search(pattern, normalized(symbol)) for pattern in FOCUS.values())


def plain_context(base, summary_path, arm, threads, commit):
    path = base / arm / 'pipe/records.json'
    if not path.is_file():
        return dict(available=False, complete=False, n=0, issues=['plain records unavailable'])
    recorded = [row for row in read(path) if row.get('threads') == threads]
    result = dict(available=True, complete=False, n=0, recorded_count=len(recorded), issues=[],
                  records_sha256=digest(path), measured_returned_jit_share=None, whole_mops=None)
    if not summary_path.is_file():
        result['issues'].append('validated comparison summary unavailable; run summarize.py first')
        return result
    summary = read(summary_path)
    result['comparison_sha256'] = digest(summary_path)
    collections = [row for row in summary.get('collections', []) if row['arm'] == arm and row['collection'] == 'pipe']
    if len(collections) != 1 or collections[0].get('records_sha256') != result['records_sha256']:
        result['issues'].append('comparison summary does not bind the current plain records')
        return result
    rows = [row for row in summary.get('sessions', []) if row['arm'] == arm and
            row['collection'] == 'pipe' and row['threads'] == threads]
    result['excluded_sessions'] = [dict(name=row['name'], issues=row['issues'],
                                        valid=row['valid'], score_eligible=row['score_eligible'])
                                   for row in rows if not row['valid'] or not row['score_eligible']]
    result['n'] = sum(row['valid'] and row['score_eligible'] for row in rows)
    groups = [row for row in summary.get('groups', []) if row['arm'] == arm and
              row['collection'] == 'pipe' and row['threads'] == threads]
    if not (len(rows) == len(recorded) == 3 and len(groups) == 1 and groups[0]['status'] == 'COMPLETE' and
            {row['repeat'] for row in rows} == {0, 1, 2} and all(row['valid'] and row['score_eligible'] and
            row['source_commit'] == commit for row in rows) and len({row['jit_class'] for row in rows}) == 1):
        result['issues'].append('plain cohort is incomplete, invalid, mixed, or uses a different source; comparison withheld')
        return result
    group = groups[0]
    result.update(complete=True, source_commit=commit, source_identity=group['source_identity'],
                  execution_class=group['jit_class'], measured_operations=sum(row['completed'] for row in rows),
                  measured_returned_bodies=sum(row['jit_completions'] for row in rows),
                  measured_returned_jit_share=group['measured_returned_jit_share'], whole_mops=group['whole_mops'])
    return result


def analyze(base, summary_path, arm, record, commit, source_id, top):
    folder = base / arm / 'profile/pipe' / record['name']
    raw_path, report_path = folder / 'perf-samples.txt', folder / 'perf-report.txt'
    text, report = raw_path.read_text(), report_path.read_text()
    counts, periods, ip_counts, ip_periods = Counter(), Counter(), Counter(), Counter()
    commands, cpus, pids, tids = Counter(), set(), set(), set()
    errors, loss_records, timestamps = [], [], []
    headers = blanks = samples = 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            blanks += 1
            continue
        if 'PERF_RECORD_LOST' in line:
            loss_records.append(dict(line=number, text=line))
            continue
        if line.lstrip().startswith('#'):
            headers += 1
            continue
        match = SAMPLE.fullmatch(line)
        if not match or int(match['period']) <= 0 or not match['symbol'] or not match['dso']:
            errors.append(dict(line=number, text=line))
            continue
        row = match.groupdict()
        comm, period, symbol, dso = row['comm'].strip(), int(row['period']), row['symbol'], row['dso']
        key = comm == 'sc_worker', symbol, dso
        periods[key] += period; counts[key] += 1; commands[comm] += period
        pids.add(int(row['pid'])); tids.add(int(row['tid'])); timestamps.append(float(row['time']))
        if comm == 'sc_worker':
            cpus.add(int(row['cpu']))
        if any(re.search(FOCUS[name], normalized(symbol)) for name in OFFSET_FOCUS):
            ip_key = (*key, int(row['ip'], 16))
            ip_periods[ip_key] += period; ip_counts[ip_key] += 1
        samples += 1
    all_period = sum(periods.values())
    worker_period = sum(period for key, period in periods.items() if key[0])
    worker_count = sum(count for key, count in counts.items() if key[0])
    lost_values = [int(value.replace(',', '')) for value in LOST.findall(report)]
    event_headers = [dict(displayed_samples=count, event=event) for count, event in EVENT.findall(report)]
    approx = [int(value.replace(',', '')) for value in PERIOD_TOTAL.findall(report)]
    issues = []
    if errors:
        issues.append('unparsed/invalid sample lines')
    if loss_records or lost_values != [0]:
        issues.append('sample loss present or report loss count missing/ambiguous')
    if len(event_headers) != 1 or event_headers[0]['event'] != 'cycles:k':
        issues.append('missing/ambiguous/different event identity')
    if approx != [all_period]:
        issues.append('report period total does not match retained sample periods')
    if not all_period or not worker_period:
        issues.append('zero all-kernel or sc_worker denominator')
    if cpus != set(record['cpus']):
        issues.append('worker samples do not cover exactly the planned CPUs')
    if pids != {record.get('client_pid')}:
        issues.append('sample process identity differs from client')
    if not (record.get('execution_status') == 'OK' and record.get('drained') is True and
            record.get('score_eligible') is False and record.get('diagnostic') is True and
            record.get('perf_record') is True and record.get('pmu') is False and
            record.get('jit_completions', 0) > 0 and record.get('jit_status') == 'PASS'):
        issues.append('profile execution/instrumentation/completion differs')
    if record.get('perf_exit_code') != 0 or record.get('perf_control_acks') != ['enable', 'disable', 'stop']:
        issues.append('recorder clean exit/control acknowledgements missing')
    symbols = defaultdict(lambda: [0, 0, 0, 0])
    for (worker, symbol, dso), period in periods.items():
        bucket = symbols[symbol, dso]
        bucket[0] += period; bucket[1] += counts[worker, symbol, dso]
        if worker:
            bucket[2] += period; bucket[3] += counts[worker, symbol, dso]
    def symbol_row(key, values):
        return dict(symbol=key[0], dso=key[1], all_kernel=weight(*values[:2], all_period),
                    sc_worker=weight(*values[2:], worker_period))
    focus = {}
    for name, expression in FOCUS.items():
        selected = [(key, values) for key, values in symbols.items() if re.search(expression, normalized(key[0]))]
        sums = [sum(values[index] for _, values in selected) for index in range(4)]
        focus[name] = dict(symbol_regex=expression, matched_symbols=[dict(symbol=key[0], dso=key[1]) for key, _ in selected],
                           all_kernel=weight(*sums[:2], all_period), sc_worker=weight(*sums[2:], worker_period))
    # Kallsyms is retained while the provider is loaded. Resolve only exact
    # symbol/module matches; an unresolved sampled offset remains null.
    addresses = {}
    for line in (folder / 'kallsyms').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and matched(fields[2]):
            addresses[fields[2], fields[3] if len(fields) > 3 else '[kernel.kallsyms]'] = int(fields[0], 16)
    offsets, by_function = [], defaultdict(list)
    for key in ip_periods:
        by_function[normalized(key[1])].append(key)
    selected_ips = [key for function in sorted(by_function)
                    for key in sorted(by_function[function], key=lambda value: -ip_periods[value])[:top]]
    for key in selected_ips:
        worker, symbol, dso, ip = key
        bare = symbol.split('+0x', 1)[0]
        origin = addresses.get((bare, dso))
        offset = ip - origin if origin and ip >= origin else None
        offsets.append(dict(comm_scope='sc_worker' if worker else 'other_client', symbol=symbol, dso=dso,
                            ip=hex(ip), symbol_offset=hex(offset) if offset is not None else None,
                            **weight(ip_periods[key], ip_counts[key], worker_period if worker else all_period)))
    measured = record['measurement']
    fraction = record['jit_completions'] / measured['completed']
    plain = plain_context(base, summary_path, arm, record['threads'], commit)
    plain_fraction = plain.get('measured_returned_jit_share')
    files = ('perf.data', 'perf-samples.txt', 'perf-report.txt', 'perf-record.log', 'session.json', 'kallsyms', 'modules')
    missing = [name for name in files if not (folder / name).is_file()]
    if missing:
        issues.append('missing artifacts: ' + ', '.join(missing))
    return dict(arm=arm, source_commit=commit, source_identity=source_id, name=record['name'],
                threads=record['threads'], repeat=record['repeat'], profile_path=str(folder.relative_to(base)),
                score_eligible=False, complete=not issues, issues=issues, event='cycles:k', sampling_frequency_hz=199,
                parsed_sample_lines=samples, nonempty_lines=samples + headers + len(errors) + len(loss_records),
                header_lines=headers, blank_lines=blanks, parse_error_count=len(errors), parse_errors=errors[:10],
                lost_event_line_count=len(loss_records), lost_event_lines=loss_records[:10], report_lost_samples=lost_values,
                report_event_headers=event_headers, report_approx_event_counts=approx,
                denominator_all_kernel=dict(observed_sum_period=all_period, samples=samples),
                denominator_sc_worker=dict(observed_sum_period=worker_period, samples=worker_count),
                worker_cpus=sorted(cpus), observed_pids=sorted(pids), observed_tid_count=len(tids),
                first_sample_time=min(timestamps) if timestamps else None, last_sample_time=max(timestamps) if timestamps else None,
                measured_operations=measured['completed'], measured_jit_bodies=record['jit_bodies'],
                measured_jit_completions=record['jit_completions'], measured_returned_jit_share=fraction,
                observed_profile_whole_mops=measured['completed'] * 1000 / measured['wall_ns'],
                matching_plain_context=plain,
                profile_minus_plain_jit_percentage_points=100 * (fraction - plain_fraction) if plain_fraction is not None else None,
                attribution_warning=('Profile and plain execution shares differ; this profile may not represent uninstrumented contention.'
                                     if plain_fraction is not None and fraction != plain_fraction else
                                     'A complete validated plain cohort is unavailable; representativeness is unestablished.'
                                     if plain_fraction is None else None),
                focus=focus, top_all_kernel=[symbol_row(key, values) for key, values in sorted(symbols.items(), key=lambda item: -item[1][0])[:top]],
                top_sc_worker=[symbol_row(key, values) for key, values in sorted(symbols.items(), key=lambda item: -item[1][2]) if values[2]][:top],
                focus_sampled_offsets=offsets,
                command_periods=dict(commands), input_sha256={name: digest(folder / name) for name in files if (folder / name).is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--arms', nargs='+', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--comparison', type=Path, help='validated comparison.json; defaults to OUTPUT/comparison.json')
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--top', type=int, default=16)
    args = parser.parse_args()
    if os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run only in the recovery VM')
    if not 1 <= args.top <= 50:
        raise ValueError('--top must be 1..50')
    base, out = args.base.resolve(), (args.output or args.base).resolve()
    summary_path = (args.comparison or out / 'comparison.json').resolve()
    out.mkdir(parents=True, exist_ok=True)
    profiles, inputs, issues = [], [], []
    for arm in args.arms:
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', arm):
            raise ValueError('unsafe arm name')
        folder = base / arm / 'profile/pipe'
        records_path = folder / 'records.json'
        if not records_path.is_file():
            issues.append(arm + ': missing profile records')
            continue
        records = read(records_path)
        command_path = base / arm / 'profile-command.json'
        command = read(command_path)
        commit = command.get('source_commit')
        if command.get('exit_code') != 0 or command.get('version') != arm or not commit:
            issues.append(arm + ': incomplete/different profile command receipt')
        if len(records) != 2 or {(row['threads'], row['repeat']) for row in records} != {(8, 0), (60, 0)}:
            issues.append(arm + ': expected two profiles at eight and sixty workers')
        source_path = folder / 'source-sha256.json'
        source = read(source_path)
        source_id = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        inputs.append(dict(arm=arm, source_commit=commit, source_identity=source_id,
                           records_sha256=digest(records_path), source_manifest_sha256=digest(source_path),
                           command_sha256=digest(command_path)))
        for row in records:
            if Path(row['name']).name != row['name'] or row['name'] in ('.', '..'):
                raise ValueError('unsafe session name')
            if not (row.get('kind') == 'pipebytes' and row.get('query') == 'query' and row.get('entries') == 16 and
                    row.get('arm') == 'kdlock' and row.get('lock_kind') == 'mutex' and row.get('source_identity') == source_id):
                issues.append(arm + '/' + row['name'] + ': workload/source differs')
            profiles.append(analyze(base, summary_path, arm, row, commit, source_id, args.top))
    result = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(),
                  complete=not issues and all(row['complete'] for row in profiles) and len(profiles) == 2 * len(args.arms),
                  profiles=profiles, inputs=inputs, issues=issues,
                  notes=['All profiles are unscored; compare each profile execution share with its own plain cohort before interpreting symbol costs.',
                         'Sampling can alter admission, native acquisition and batching. Sparse delegation profiles may not represent the uninstrumented workload.',
                         'Weights are cycles:k sample periods. All-kernel means the retained client process tree, not all system CPUs; sc_worker is an exact comm filter.',
                         'Auxiliary filters overlap; never add them as disjoint costs. Inlined work may be charged to enclosing functions.',
                         'hint_retry_helpers covers both the original combiner query and a candidate outer_retry helper. The latter also includes physical-owner probes, so this aggregate is not identical code scope across versions.',
                         'Flat sampled IPs have skid. Symbol offsets do not count atomic retries or identify exact cycles per operation; ELF inspection remains separate on the source host.',
                         'Lost and unparsed records invalidate completeness. Capped examples retain total counts and the hash of the full original text.',
                         'Profiles and plain timings, source versions, execution classes and worker counts are never pooled.'])
    (out / 'profile-analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    lines = ['| Arm | Workers | Profile returned JIT | Plain returned JIT | Ref acquire % | Ref put % | Hint/retry helpers % | Samples | Complete |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for row in profiles:
        plain = row['matching_plain_context'].get('measured_returned_jit_share')
        plain_text = '—' if plain is None else f'{100 * plain:.2f}%'
        fractions = [row['focus'][key]['sc_worker']['percent_of_denominator'] for key in ('aux_acquire', 'aux_put', 'hint_retry_helpers')]
        cells = ['—' if value is None else f'{value:.2f}' for value in fractions]
        lines.append(f"| {row['arm']} | {row['threads']} | {100 * row['measured_returned_jit_share']:.2f}% | {plain_text} | " +
                     ' | '.join(cells) + f" | {row['parsed_sample_lines']} | {row['complete']} |")
    lines.extend(['', 'Symbol percentages use the sc_worker period denominator; these profiles are unscored.'])
    (out / 'profile-table.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(complete=result['complete'], profiles=len(profiles),
                          parsed_samples=sum(row['parsed_sample_lines'] for row in profiles), issues=issues, output=str(out))))
    return 0 if result['complete'] or args.allow_partial else 1


if __name__ == '__main__':
    raise SystemExit(main())
