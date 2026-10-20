#!/usr/bin/env python3
"""Read and validate sparse complete-operation latency, outside measured work.

This is distinct from acquisition latency. A delegated lock call can resume
after unlock/ACK; timestamps inserted immediately after it would measure a
different interval from a native acquisition. Never subtract clock overhead
from individual observations or derive latency from inverse throughput.
"""
import fcntl
import math
from pathlib import Path
import statistics
import struct

VERSION, STRIDE, CAPACITY, CHUNK = 1, 256, 32768, 256
HEADER = struct.Struct('<4I4Q2IQ')
SAMPLE = struct.Struct('<3Q')
SIZE = HEADER.size + CHUNK * SAMPLE.size
READ = (3 << 30) | (SIZE << 16) | (0xB7 << 8) | 0x40
MASK = (1 << 64) - 1


def selected_ordinals(worker, completed):
    """Independent reconstruction of the per-worker sampling schedule."""
    state = ((worker + 1) * 0x9e3779b97f4a7c15) & MASK
    result = []
    for start in range(0, completed, STRIDE):
        state ^= state >> 12
        state ^= (state << 25) & MASK
        state ^= state >> 27
        offset = ((state * 0x2545f4914f6cdd1d) & MASK) & (STRIDE - 1)
        if start + offset < completed:
            result.append(start + offset)
    return result


def validate_worker(row, worker, completed, begin, end, enabled):
    if (type(enabled) is not bool or type(row['enabled']) is not bool or
            any(type(value) is not int or value < 0 for value in
                (worker, completed, begin, end, row['worker'], row['completed'],
                 row['selected'], row['dropped'])) or begin >= end or
            not isinstance(row['samples'], list) or
            any(not isinstance(sample, (list, tuple)) or len(sample) != 3 or
                any(type(value) is not int or value < 0 for value in sample)
                for sample in row['samples'])):
        raise ValueError('invalid latency field types or extents')
    expected = selected_ordinals(worker, completed) if enabled else []
    if (row['worker'] != worker or row['completed'] != completed or
            row['enabled'] != enabled or row['dropped'] != 0 or
            row['selected'] != len(expected) or len(expected) > CAPACITY or
            [s[0] for s in row['samples']] != expected):
        raise ValueError('latency schedule/count/overflow differs')
    previous = begin
    for ordinal, start, finish in row['samples']:
        if not previous <= start < finish <= end:
            raise ValueError('latency interval is unordered or outside worker execution')
        previous = finish
    values = [finish-start for _, start, finish in row['samples']]
    return values


def percentile(values, percentile=95):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percentile / 100)-1]


def summarize(rows, measurement, enabled, scope):
    all_values, worker_stats = [], []
    workers = measurement['workers']
    if not workers or len(rows) != len(workers):
        raise ValueError('latency worker cohort differs')
    for index, (row, worker) in enumerate(zip(rows, workers)):
        values = validate_worker(row, index, worker['completed'],
            worker['active_started_ns'], worker['kernel_finished_ns'], enabled)
        all_values.extend(values)
        worker_stats.append(dict(worker=index, cpu=worker['cpu'], samples=len(values),
            median_ns=statistics.median(values) if values else None,
            p95_ns=percentile(values), max_ns=max(values) if values else None))
    # Keep sparse, low-count distributions explicit rather than silently
    # labelling a percentile based on very few observations as sufficient.
    return dict(version=VERSION, enabled=enabled, scope=scope, stride=STRIDE,
        percentile_method='nearest_rank', samples=len(all_values),
        minimum_samples_per_worker=1000,
        sufficient=bool(enabled and all(w['samples'] >= 1000 for w in worker_stats)),
        median_ns=statistics.median(all_values) if all_values else None,
        p95_ns=percentile(all_values), max_ns=max(all_values) if all_values else None,
        workers=worker_stats, calibration_subtracted=False,
        limitations='Sampled completed-operation latency; no acquisition-time or unsampled-tail claim')


def read_synthetic(path, measurement, enabled):
    """An open device pins its source module until every drained chunk is read."""
    rows = []
    with Path(path).open('rb', buffering=0) as source:
        for worker in range(len(measurement['workers'])):
            first, row = 0, None
            while True:
                buffer = bytearray(SIZE)
                struct.pack_into('<4I', buffer, 0, VERSION, worker, first, CHUNK)
                fcntl.ioctl(source.fileno(), READ, buffer, True)
                values = HEADER.unpack_from(buffer)
                version, index, offset, capacity, begin, done, selected, dropped, count, active, reserved = values
                if ((version, index, offset, capacity) != (VERSION, worker, first, CHUNK) or
                        reserved or active not in (0, 1) or count > CHUNK or
                        selected > CAPACITY or dropped or begin != measurement['started_ns']):
                    raise ValueError('invalid latency chunk metadata or overflow')
                identity = dict(worker=worker, completed=done, selected=selected,
                                dropped=dropped, enabled=bool(active))
                if row is None:
                    row = dict(identity, samples=[])
                elif any(row[k] != v for k, v in identity.items()):
                    raise ValueError('latency identity changed while reading')
                row['samples'].extend(list(SAMPLE.unpack_from(buffer, HEADER.size+i*SAMPLE.size))
                                      for i in range(count))
                first += count
                if first == selected:
                    break
                if not count or first > selected:
                    raise ValueError('incomplete latency stream')
            rows.append(row)
    summary = summarize(rows, measurement, enabled,
        'Kernel body call through body return; includes lock, business body, unlock/ACK; excludes post-work')
    return dict(rows=rows, summary=summary)
