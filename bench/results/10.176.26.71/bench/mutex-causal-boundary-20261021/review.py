#!/usr/bin/env python3
"""Read fixed evidence as data; never extract or execute an archived program."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import tarfile

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1] / 'raw' / 'bench'
OLD = 'mutex-recovery-followup-20261021'
MANIFEST_SHA = 'a57c35c0a11df0812b6a621a688c50229e5cc6c9fdde60868e1799640cf281d1'
SNAPSHOT_SHA = '14e94a505c3f343ca8f6136835ff6ce4329a64d9d5d058f58f7f8ab9c94bebaa'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(path):
    with tarfile.open(path, 'r:gz') as stream:
        members = stream.getmembers()
        require(len({m.name for m in members}) == len(members), 'duplicate member')
        # Only ordinary files are read, without filesystem extraction.
        return {m.name: stream.extractfile(m).read() for m in members if m.isfile()}


def fields(line):
    return {k: int(v) for k, v in re.findall(r'\b(\w+)=(\d+)\b', line)}


def unique_line(lines, marker):
    found = [line for line in lines if marker in line]
    require(len(found) == 1, 'missing or duplicate ' + marker)
    return fields(found[0])


def main():
    manifest_bytes = (RAW / OLD / 'archives-1/archives.json').read_bytes()
    require(sha(manifest_bytes) == MANIFEST_SHA, 'archive manifest differs')
    manifest = json.loads(manifest_bytes)
    digests = {}
    for group in manifest['groups']:
        path = RAW / OLD / 'archives-1' / group['file']
        data = path.read_bytes()
        require(len(data) == group['bytes'] and sha(data) == group['sha256'],
                'archive differs: ' + group['file'])
        digests[group['file']] = sha(data)
    measured = archive(RAW / OLD / 'archives-1/measurements.tar.gz')
    metadata = archive(RAW / OLD / 'archives-1/metadata.tar.gz')
    before = json.loads(metadata[OLD + '/host-before-run-1.json'])
    after = json.loads(metadata[OLD + '/host-after-1.json'])
    status = json.loads(measured[OLD + '/run-1/matrix/status.json'])
    old = {row['tid']: row for row in before['qemu'][0]['tasks']}
    new = {row['tid']: row for row in after['qemu'][0]['tasks']}
    require(len(old) == 67 and len(new) == 100, 'historical thread counts differ')
    require(all(new.get(tid) == row for tid, row in old.items()),
            'original TID/name/affinity rows changed')
    extra = [new[tid] for tid in sorted(new.keys() - old.keys())]
    require(all(row['comm'] == 'worker' and row['affinity'] == [63]
                for row in extra), 'extra thread classification differs')
    endpoint = dict(before_utc=before['captured_utc'], after_utc=after['captured_utc'],
        matrix_finished_utc=status['finished_utc'], before_count=len(old),
        after_count=len(new), extra=extra,
        capture_after_matrix_seconds=(datetime.fromisoformat(after['captured_utc']) -
                                     datetime.fromisoformat(status['finished_utc'])).total_seconds(),
        original_tid_name_affinity_rows_equal=True,
        identity_limit='Endpoints omit start ticks; equality is not a TID-lifetime proof.',
        historical_activity_bound=None, strict_endpoint_passed=False)

    records = json.loads(measured[OLD + '/run-1/matrix/records.json'])
    rows = []
    for repeat in range(3):
        for version, arm in (('baseline', 'baseline-kd'), ('current', 'public-kd')):
            name = f'pipecap-t05-r{repeat}-{arm}'
            member = f'{OLD}/run-1/matrix/measurements/{version}/pipecap/{name}/kernel.log'
            data = measured[member]
            lines = data.decode().splitlines()
            stats = unique_line(lines, 'kd_mutex stats:')
            tasks = unique_line(lines, 'kd_mutex tasks:')
            heat = [fields(line) for line in lines if 'kd_hotlock mutex ratio:' in line]
            locks = [fields(line) for line in lines if 'kd_hotlock final:' in line
                     and 'type=mutex ' in line]
            require(sorted(row['cpu'] for row in heat) == list(range(5)),
                    'missing worker CPU heat records')
            matches = [row for row in records if row['name'] == name]
            require(len(matches) == 1, 'missing or duplicate measurement')
            record = matches[0]
            require(record['drained'] and record['measurement']['ok'], 'session failure')
            require(0 <= record['jit_completions'] <= record['jit_bodies'],
                    'returned bodies exceed entry witnesses')
            require(stats['origin_acquires'] == stats['origin_releases'] and
                    stats['active_waiters'] == stats['reserved_nodes'] == tasks['active_tasks'] == 0,
                    'ownership or final drain differs')
            if version == 'baseline':
                require(all(stats[key] == 0 for key in ('slowpath', 'combiner',
                    'jit_success', 'jit_resume', 'origin_acquires', 'origin_releases'))
                    and tasks['task_reroutes'] == 0 and
                    record['jit_bodies'] == record['jit_completions'] == 0
                    and all(row['lock_hot'] == 0 for row in locks), 'OUTER path differs')
            else:
                require(stats['slowpath'] > 0 and record['jit_completions'] > 0 and
                        len(locks) == 5 and all(row['lock_hot'] == 1 for row in locks),
                        'DIRECT path differs')
            rows.append(dict(name=name, log_member=member, log_sha256=sha(data),
                stats=stats, tasks=tasks, final_cpu_heat=heat, final_lock_heat=locks,
                measured_entries=record['jit_bodies'],
                measured_returned_bodies=record['jit_completions'],
                measured_operations=record['measurement']['completed'],
                jit_status=record['jit_status'], drained=record['drained']))

    snapshot_bytes = (RAW / HERE.name / 'qemu-snapshot-1.json').read_bytes()
    require(sha(snapshot_bytes) == SNAPSHOT_SHA, 'new snapshot differs')
    snap = json.loads(snapshot_bytes)
    for boundary in ('before', 'after'):
        observed = {t['tid']: t for t in snap[boundary]['tasks']}
        require(len(observed) == len(snap[boundary]['tasks']), 'duplicate snapshot TID')
        require(all(tid in observed and
                    {key: observed[tid][key] for key in row} == row
                    for tid, row in old.items()), 'original snapshot rows differ')
        require(not set(observed).intersection(t['tid'] for t in extra),
                'historical extra TID remains in later snapshot')
    workers = []
    for task in snap['after']['tasks']:
        require(not task.get('disappeared'), 'task disappeared in new snapshot')
        if task['comm'] != 'worker':
            continue
        require(task['affinity'] == [63], 'new worker placement differs')
        io = dict(line.split(': ', 1) for line in task['files']['io']['text'].splitlines())
        stat = task['stat_after'].rsplit(')', 1)[1].split()
        workers.append(dict(tid=task['tid'], affinity=task['affinity'], state=stat[0],
            start_ticks=int(stat[19]), user_ticks=int(stat[11]), system_ticks=int(stat[12]),
            runtime_ns=int(task['files']['schedstat']['text'].split()[0]),
            read_bytes=int(io['read_bytes']), write_bytes=int(io['write_bytes']),
            wchan=task['files']['wchan']['text']))
    require(len(snap['before']['tasks']) == len(snap['after']['tasks']) == 74 and
            len(workers) == 7 and not {t['tid'] for t in workers}.intersection(
                t['tid'] for t in extra), 'later thread observation differs')
    later = dict(captured_utc=snap['captured_utc'], sha256=SNAPSHOT_SHA,
        before_threads=74, after_threads=74, historical_extra_tids_still_present=[],
        workers=workers, worker_lifetime_runtime_ns=sum(t['runtime_ns'] for t in workers),
        worker_lifetime_write_bytes=sum(t['write_bytes'] for t in workers),
        strict_count_passed=False,
        limit='Different later threads. Cumulative lifetime counters are not deltas '
              'during the historical workload or evidence of its interference.')
    result = dict(schema=1, integrity_passed=True, accepted=False,
        source_revision='930dbeeb607309183465bdbbf42a2512a8fe1182',
        review_source_sha256=sha(Path(__file__).read_bytes()),
        archive_manifest_sha256=MANIFEST_SHA, archive_sha256=digests,
        historical_endpoint=endpoint, pipecap=rows, later_snapshot=later,
        new_vm_tests=0, new_timing_sessions=0, helpers_files_touched=[],
        regressions={key: 'UNRESOLVED_CAUSE' for key in
            ('c08-t03', 'c08-t04', 'c08-t05', 'pipebytes-t03', 'pipebytes-t05',
             'pipecap-t05', 'rcuht-t02')},
        limits=['Final heat residuals do not reconstruct admission chronology.',
                'Provider lifetime counters include warmup.',
                'No matched-path overhead or causal fix established.',
                'Acquisition-only latency remains unresolved.'])
    with (HERE / 'review.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(integrity_passed=True, accepted=False,
                         pipecap_logs=len(rows), new_threads=len(workers))))


if __name__ == '__main__':
    main()
