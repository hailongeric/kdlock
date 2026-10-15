"""Validate raw timed progress and select an observed full-cohort window.

Progress is published after complete operations in batches, not inferred from
JIT bodies. No interpolation or fixed nominal-duration divisor is used. Read
brackets conservatively enclose each selected window; checkpoint quantization
and non-simultaneous per-worker reads remain measurement limitations.
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unsigned(value):
    return type(value) is int and value >= 0


def analyze_peak(measurement, spec):
    """Return derived peak metadata; never mutate the raw client result."""
    m = measurement
    for field, source in (('duration_ns', 'duration_ms'),
                          ('peak_window_ns', 'peak_window_ms'),
                          ('peak_settle_ns', 'peak_settle_ms'),
                          ('sample_period_ns', 'sample_ms')):
        require(unsigned(m[field]) and m[field] == spec[source] * 1000000,
                'timed setting differs: ' + field)
    require(0 < m['sample_period_ns'] <= m['peak_window_ns'] and
            m['peak_settle_ns'] + m['peak_window_ns'] < m['duration_ns'],
            'invalid timed window settings')
    require(unsigned(m['started_ns']) and
            m['deadline_ns'] == m['started_ns'] + m['duration_ns'],
            'timed deadline differs')
    shared = spec.get('collector_shared', False)
    require(type(shared) is bool and type(m.get('collector_shared', False)) is bool
            and m.get('collector_shared', False) == shared,
            'collector sharing identity differs')
    require(unsigned(m['collector_cpu']) and m['collector_cpu'] == spec['collector_cpu']
            and ((shared and spec['cpus'] == list(range(64)) and spec['threads'] == 64
                  and m['collector_cpu'] == 63)
                 or (not shared and m['collector_cpu'] not in spec['cpus'])),
            'collector CPU differs or has unapproved overlap')
    require(m['collector_observed_cpu'] == m['collector_cpu'] and m['collector_error'] == 0,
            'collector affinity/setup failed')
    require(m['progress_batch'] == 256, 'unexpected progress checkpoint size')
    workers = m['workers']
    require(len(workers) == spec['threads'] and
            [worker['cpu'] for worker in workers] == spec['cpus'],
            'progress worker geometry differs')
    for worker in workers:
        require(all(unsigned(worker[key]) for key in
                    ('active_started_ns', 'kernel_finished_ns', 'finished_ns', 'completed'))
                and m['started_ns'] <= worker['active_started_ns'] < m['deadline_ns']
                <= worker['kernel_finished_ns'] <= worker['finished_ns'] <= m['finished_ns'],
                'worker did not span the timed deadline')
    active_start = max(worker['active_started_ns'] for worker in workers)
    active_end = min(m['deadline_ns'], *(worker['kernel_finished_ns'] for worker in workers))
    eligible_start = active_start + m['peak_settle_ns']
    require(active_end - eligible_start >= m['peak_window_ns'],
            'no full-cohort interval after settling')

    samples = m['samples']
    require(isinstance(samples, list) and len(samples) >= 2, 'insufficient progress samples')
    previous_end = m['started_ns']
    previous = [0] * len(workers)
    eligible = []
    widths = []
    for index, sample in enumerate(samples):
        begin, end = sample['started_ns'], sample['finished_ns']
        counts = sample['completed']
        require(unsigned(begin) and unsigned(end) and previous_end <= begin <= end,
                'progress sample times overlap or move backward')
        require(isinstance(counts, list) and len(counts) == len(workers) and
                all(unsigned(value) and old <= value <= worker['completed']
                    for value, old, worker in zip(counts, previous, workers)),
                'progress counts move backward or exceed final totals')
        for value, worker in zip(counts, workers):
            require(end >= worker['active_started_ns'] or value == 0,
                    'progress precedes worker start')
            require(begin < worker['kernel_finished_ns'] or value == worker['completed'],
                    'finished worker progress differs from exact total')
        widths.append(end - begin)
        if begin >= eligible_start and end <= active_end:
            eligible.append(index)
        previous_end, previous = end, counts

    best = None
    candidate_windows = 0
    # For every observed start, use its earliest observed endpoint reaching
    # the requested duration. This fixes the search rule across all backends;
    # a delayed collector produces a longer reported window, not interpolation.
    for position, start_index in enumerate(eligible):
        start = samples[start_index]
        for end_index in eligible[position + 1:]:
            end = samples[end_index]
            elapsed = end['finished_ns'] - start['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            deltas = [last - first for first, last in zip(start['completed'], end['completed'])]
            completed = sum(deltas)
            candidate_windows += 1
            # Alive-but-starved workers do not form an accepted cohort window.
            if all(delta > 0 for delta in deltas) and (best is None or
                    completed * best['elapsed_ns'] > best['completed'] * elapsed):
                best = dict(start_sample_index=start_index, end_sample_index=end_index,
                            started_ns=start['started_ns'], finished_ns=end['finished_ns'],
                            start_snapshot_span_ns=start['finished_ns'] - start['started_ns'],
                            end_snapshot_span_ns=end['finished_ns'] - end['started_ns'],
                            elapsed_ns=elapsed, completed=completed, worker_completed=deltas,
                            throughput_ops_s=completed * 1e9 / elapsed,
                            amortized_ns_op=elapsed / completed)
            break
    require(best is not None, 'no positive full-cohort peak window')
    best.update(policy='observed_full_cohort_earliest_endpoint',
                requested_window_ns=m['peak_window_ns'], settle_ns=m['peak_settle_ns'],
                active_started_ns=active_start, active_finished_ns=active_end,
                eligible_started_ns=eligible_start, eligible_samples=len(eligible),
                candidate_windows=candidate_windows, progress_batch=m['progress_batch'],
                # This bounds count quantization alone, not all sampling error.
                # The 256th operation can finish just before its publication.
                progress_count_error_bound=len(workers) * m['progress_batch'],
                max_snapshot_span_ns=max(widths),
                sample_period_ns=m['sample_period_ns'], collector_cpu=m['collector_cpu'],
                collector_shared=shared)
    return best
