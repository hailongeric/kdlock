"""Recompute correctness, deterministic mix, progress and JIT writer evidence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'spin_cacheline'))
from peak import analyze_peak


def require(condition, message):
    if not condition:
        raise ValueError(message)


def writes_for(completed, worker, percent):
    return ((worker * 17) % 100 + completed * percent) // 100


def post_work_checksum(completed, rounds):
    """Exponentiate the affine post-work recurrence modulo 2**64."""
    steps, state, multiply, add = completed * rounds, 1, 1664525, 1013904223
    mask = 2**64 - 1
    while steps:
        if steps & 1:
            state = (multiply * state + add) & mask
        add = (multiply * add + add) & mask
        multiply = multiply * multiply & mask
        steps >>= 1
    return state


def check_snapshot(row, spec):
    require((row['version'], row['backend'], row['workload'], row['lines'], row['post_work_rounds']) ==
            (1, {'native': 0, 'tclock': 1, 'kdlock': 2}[spec['arm']],
             {'cacheline': 0, 'rcuht': 1, 'taskname': 2, 'argbounds': 3,
              'list': 4, 'list-prefetch': 5}[spec['workload']],
             spec['cachelines'], spec['post_work_rounds']),
            'workload identity differs')
    require(all(row[name] == 0 for name in ('active', 'cnts', 'gate')), 'rwlock did not drain')
    require(len(row['values']) == 16 and all(type(v) is int and 0 <= v < 2**64 for v in row['values']),
            'invalid payload snapshot')
    if spec['workload'] in ('list', 'list-prefetch'):
        require(spec.get('list_nodes') == row['lines'] and row['lines'] in (16, 128) and
                row['values'][1:] == [0] * 15, 'invalid list identity/unused counters')


def validate(measurement, spec):
    m = measurement
    require(m['schema'] == 1 and m['complete'] is True, 'client did not complete')
    require(m['wall_ns'] == m['finished_ns'] - m['started_ns'] > 0, 'invalid whole-run interval')
    workers = m['workers']
    require(len(workers) == spec['threads'] and [w['cpu'] for w in workers] == spec['cpus'],
            'worker placement differs')
    for index, w in enumerate(workers):
        require(not w.get('error') and w['observed_cpu'] == w['cpu'] and w['cpu_ns'] > 0,
                'worker failed or migrated')
        require(type(w['completed']) is int and w['completed'] > 0 and
                w['completed'] == w['reads'] + w['writes'], 'invalid worker totals')
        require(w['writes'] == writes_for(w['completed'], index, spec['write_percent']),
                'operation mix differs')
        require(w['read_errors'] == 0 and 0 <= w['read_hits'] <= w['reads'], 'reader observed corrupt data')
        require(w['checksum'] == post_work_checksum(w['completed'], spec['post_work_rounds']),
                'post-work amount/result differs')
        require(m['started_ns'] <= w['active_started_ns'] <= w['kernel_finished_ns'] <=
                w['finished_ns'] <= m['finished_ns'], 'invalid worker interval')
        if not spec['duration_ms']:
            require(w['completed'] == spec['iterations'], 'incomplete fixed worker')
        else:
            require(w['completed'] % 256 == 0, 'partial timed batch')
    for name in ('completed', 'reads', 'writes'):
        require(m[name] == sum(w[name] for w in workers), 'incorrect aggregate ' + name)
    before, after = m['before'], m['after']
    for row in (before, after):
        check_snapshot(row, spec)
    require(all(before[key] == after[key] for key in before if key != 'values'),
            'workload changed during measurement')
    delta = [a - b for a, b in zip(after['values'], before['values'])]
    if spec['workload'] == 'cacheline':
        require(delta == [m['writes']] * spec['cachelines'] + [0] * (16 - spec['cachelines']),
                'lost/duplicated write or inactive-line update')
        require(all(w['read_hits'] == 0 for w in workers), 'cacheline reader returned hash hits')
    elif spec['workload'] in ('taskname', 'argbounds', 'list', 'list-prefetch'):
        require(delta == [m['writes']] + [0] * 15, 'lost/duplicated snapshot mutation')
        require(all(w['read_hits'] == 0 for w in workers), 'snapshot returned hash hits')
    else:
        require(delta[0] == m['writes'] == sum(delta[1:4]) and all(x >= 0 for x in delta[:4]) and
                before['values'][4:] == after['values'][4:] == [0] * 12,
                'hash outcome totals differ')
    if not spec['duration_ms']:
        return None
    peak = analyze_peak(m, spec)
    start = m['samples'][peak['start_sample_index']]['completed']
    end = m['samples'][peak['end_sample_index']]['completed']
    writer_counts = [writes_for(last, i, spec['write_percent']) - writes_for(first, i, spec['write_percent'])
                     for i, (first, last) in enumerate(zip(start, end))]
    peak['writes'] = sum(writer_counts)
    peak['reads'] = peak['completed'] - peak['writes']
    peak['worker_writes'] = writer_counts
    peak['read_ops_s'] = peak['reads'] * 1e9 / peak['elapsed_ns']
    peak['write_ops_s'] = peak['writes'] * 1e9 / peak['elapsed_ns']
    return peak


def jit_evidence(before, after, writes, *, backend, delegate, operation='writer', completed=None):
    bodies = after - before
    require(0 <= bodies <= writes, 'JIT count exceeds completed eligible operations')
    require((backend == 'kdlock' and delegate) or bodies == 0, 'native control executed JIT')
    status = ('PASS' if bodies else 'NO_JIT') if backend == 'kdlock' and delegate and writes else 'NATIVE'
    row = dict(jit_bodies=bodies, **{'jit_' + operation + '_share': bodies / writes if writes else 0},
               jit_operation=operation, jit_status=status)
    if completed is not None:
        require(0 <= completed <= bodies, 'completion count exceeds entry witnesses')
        row.update(jit_completions=completed, jit_complete_share=completed / writes if writes else 0)
        if bodies and not completed:
            row['jit_status'] = 'PARTIAL_JIT'
    return row
