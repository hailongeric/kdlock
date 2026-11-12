"""Validate completion witnesses separately from generated entry counts."""
from oracle import require


def validate_kd(measurement, compiler, *, recording=True):
    evidence = measurement['kd_evidence']
    if not recording:
        require(evidence.get('available') is False and evidence.get('workers') is None,
                'recorder-off phase supplied observations instead of explicit unavailability')
        return dict(jit_status='EVIDENCE_UNAVAILABLE', jit_entries=None, jit_completions=None,
                    completed_writer_share=None, completion_scope='unavailable: phase recorder disabled',
                    retirement_observations_available=False, physical_batch_length_measured=False)
    require(evidence.get('available', True) is True, 'recorder-on evidence unavailable')
    rows = evidence['workers']
    require(len(rows) == len(measurement['workers']), 'evidence worker geometry differs')
    complete = entries = 0
    for counts, worker in zip(rows, measurement['workers']):
        require(counts['attached'] == counts['detached'] == 1 and counts['state'] and counts['origin'],
                'task source/runtime lifecycle incomplete')
        require(counts['errors'] == counts['live'] == 0 and
                counts['reserved'] == counts['freed'] and
                counts['fast_acquired'] == counts['fast_released'] and
                counts['fast_read_acquired'] == counts['fast_read_released'] and
                counts['reserved'] + counts['fast_acquired'] + counts['fast_read_acquired'] == worker['completed'] and
                counts['fast_acquired'] <= worker['writes'] and counts['fast_read_acquired'] <= worker['reads'],
                'exact request lifetime or per-operation accounting differs')
        require(counts['read_acquired'] == counts['read_released'] == worker['reads'],
                'local reader credits differ from completed reads')
        require(not counts['fast_acquired'] or measurement.get('spec', {}).get('lock_kind') == 'mutex',
                'fast mutex evidence appeared outside the mutex family')
        require(not counts['fast_read_acquired'] or measurement.get('spec', {}).get('lock_kind') == 'rwsem',
                'fast read evidence appeared outside the rwsem family')
        require(0 <= counts['completed'] <= counts['entered'] and
                counts['completed'] <= worker['writes'], 'completed JIT bodies exceed eligible writes')
        complete += counts['completed']
        entries += counts['entered']
        if not counts['completed']:
            continue
        require(counts['proof'] == 1, 'completed count lacks an exact retained witness')
        prepare, entry, exit_row, unlock, done, free = counts['records']
        require([r['kind'] for r in counts['records']] == [22, 23, 24, 25, 27, 2],
                'protected completion witness kinds differ')
        for name in ('state', 'node', 'acquisition'):
            require(prepare[name] and all(r[name] == prepare[name] for r in counts['records']),
                    'completion witness crosses a request lifetime: ' + name)
        require(prepare['state'] == counts['state'] and entry['origin'] == counts['origin'] and
                entry['task'] != entry['origin'] and entry['image'] == compiler.old and
                exit_row['image'] == unlock['image'] == compiler.old and exit_row['result'] == 1,
                'foreign generated execution/image/exit differs')
        require(unlock['related'] == prepare['node'] and unlock['ip'] == compiler.unlock['site'] and
                unlock['cursor'] == compiler.unlock['site'] + compiler.unlock['length'],
                'typed unlock is not the actual source CALL and exact request')
        require(done['result'] == 3 and done['flags'] & 1536 == 1536,
                'no positive complete protected episode')
        require(free['flags'] & 96 == 96 and not any(free[name] for name in
                ('source_user', 'return_user', 'notifier')) and not free['flags'] & 16,
                'source/request last users did not retire')
    status = 'PASS' if complete else ('PARTIAL_JIT' if entries else 'NO_JIT')
    return dict(jit_status=status, jit_entries=entries, jit_completions=complete,
                completed_writer_share=complete / measurement['writes'] if measurement['writes'] else 0,
                completion_scope='protected episode; C function epilogue is native',
                physical_batch_length_measured=False)
