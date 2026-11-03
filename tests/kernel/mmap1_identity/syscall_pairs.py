"""Bounded outer-syscall/retained-root joins for unscored mmap1 observations."""
import re

ROOT_EVENT = re.compile(
    r'kd_service event=(\w+) origin=(\d+) executor=(\d+) identity=(?:0x)?([0-9a-fA-F]+) '
    r'generation=(\d+) object=(?:0x)?([0-9a-fA-F]+) depth=(\d+) entry=([0-9a-fA-F]+) may_delegate=([01])')
HEX_FIELDS = {'mm', 'lock', 'backing', 'provider', 'result'}
IDENTITY = ('tid', 'tgid', 'start', 'mm', 'lock', 'backing', 'provider', 'route')
CALL_FIELDS = set(IDENTITY) | {'event', 'op', 'sequence', 'pair', 'cpu', 'time', 'args', 'result'}
STOP_FIELDS = {'event', 'limit', 'tasks', 'pairs', 'unfinished', 'inflight', 'errors',
               'identity_missed', 'mmap_missed', 'mmap_suppressed', 'munmap_missed', 'munmap_suppressed'}


def require(value, message):
    if not value:
        raise ValueError(message)


def marker(line):
    if 'kd_mm_pair:' not in line:
        return None
    _, separator, text = line.partition('kd_mm_pair: ')
    require(separator, 'invalid syscall marker prefix')
    text = text.strip()
    words = text.split()
    require(all(word.count('=') == 1 for word in words), 'invalid syscall marker')
    values = dict(word.split('=', 1) for word in words)
    require(len(values) == len(words), 'duplicate syscall marker field')
    stop = values.get('event') == 'stop'
    require(set(values) == (STOP_FIELDS if stop else CALL_FIELDS), 'syscall marker fields differ')
    for key, value in list(values.items()):
        if key in ('event', 'op'):
            continue
        if key == 'args':
            parts = value.split(',')
            require(len(parts) == 6 and all(re.fullmatch('[0-9a-f]+', part) for part in parts),
                    'original six syscall arguments missing')
            values[key] = tuple(int(part, 16) for part in parts)
            require(all(value < 1 << 64 for value in values[key]), 'syscall argument exceeds raw64')
        else:
            require(re.fullmatch('[0-9a-f]+' if key in HEX_FIELDS else '[0-9]+', value),
                    'invalid syscall marker value')
            values[key] = int(value, 16 if key in HEX_FIELDS else 10)
            require(values[key] < 1 << 64, 'syscall marker value exceeds raw64')
    return values


def validate(messages, snapshot, proof, entry_sites, limit):
    require(type(limit) is int and 1 <= limit <= 8, 'invalid syscall pair sample limit')
    workers = {row['tid']: row for row in snapshot['records']}
    require(workers and len(workers) == len(snapshot['records']), 'distinct observed worker lifetimes required')
    identity = lambda row: (row['origin'], row['identity'], row['generation'])
    completed = {identity(row): row for row in proof['completed_requests']}
    require(len(completed) == len(proof['completed_requests']), 'duplicate completed root identity')
    operation = {entry: name for name, entries in entry_sites.items() for entry in entries}
    require(set(entry_sites) == {'mmap', 'munmap'} and all(entry_sites.values()) and
            len(operation) == sum(map(len, entry_sites.values())), 'exact disjoint syscall entry sites required')
    states = {tid: dict(sequence=0, pairs=0, address=None, call=None) for tid in workers}
    roots, root_stages, seen_roots, joined, summary = {}, {}, set(), [], None
    previous_record = -1
    for line in messages.splitlines():
        event = marker(line)
        found = ROOT_EVENT.search(line)
        if event is None and found is None:
            continue
        record = re.match(r'^\d+,(\d+),\d+,[^;]*;', line)
        require(record and int(record[1]) > previous_record, 'ordered raw kmsg records required')
        previous_record = int(record[1])
        if event is not None:
            require(summary is None, 'syscall event after STOP summary')
            if event['event'] == 'stop':
                require(event['limit'] == limit and not any(event[name] for name in
                    ('unfinished', 'inflight', 'errors', 'identity_missed', 'mmap_missed', 'mmap_suppressed',
                     'munmap_missed', 'munmap_suppressed')), 'syscall capture incomplete or probes missed events')
                summary = event
                continue
            require(event['event'] in ('enter', 'return') and event['op'] in ('mmap', 'munmap') and
                    event['tid'] in workers, 'unexpected syscall marker event/task')
            row, state = workers[event['tid']], states[event['tid']]
            expected = dict(tid=row['tid'], tgid=row['tgid'], start=row['start_boottime_ns'],
                            **{name: row[name] for name in ('mm', 'lock', 'backing', 'provider', 'route')})
            require(all(event[name] == expected[name] for name in IDENTITY), 'syscall worker/MM identity changed')
            require(event['cpu'] == row['cpu'] and event['time'] > 0, 'syscall origin CPU/time differs')
            if event['event'] == 'enter':
                require(state['call'] is None and event['sequence'] == state['sequence'] + 1 and
                        event['pair'] == state['pairs'] + 1 <= limit and event['result'] == 0,
                        'overlapping, repeated or out-of-order syscall invocation')
                args = event['args']
                if event['op'] == 'mmap':
                    require(state['address'] is None and args[:4] == (0, 128 * 1024 * 1024, 3, 0x22) and
                            args[4] & 0xffffffff == 0xffffffff and args[5] == 0,
                            'syscall does not have the original mmap1 arguments')
                else:
                    require(state['address'] is not None and args[:2] == (state['address'], 128 * 1024 * 1024),
                            'munmap does not consume the exact successful mmap address')
                state.update(sequence=event['sequence'], call=dict(entry=event, roots=[]))
            else:
                call = state['call']
                require(call is not None and all(event[name] == call['entry'][name]
                    for name in (*IDENTITY, 'op', 'sequence', 'pair', 'args')) and
                    event['time'] >= call['entry']['time'], 'syscall return has no exact invocation')
                require(call['roots'] and all(key not in roots for key in call['roots']),
                        'origin syscall returned before complete other-task root execution')
                if event['op'] == 'mmap':
                    require(0 <= event['result'] < (1 << 64) - 4095 and event['result'] % 4096 == 0,
                            'sampled mmap did not return a successful aligned address')
                    state['address'] = event['result']
                else:
                    require(event['result'] == 0, 'sampled munmap failed')
                    state.update(address=None, pairs=state['pairs'] + 1)
                joined.append(dict(operation=event['op'], origin=event['tid'],
                    task_start_boottime_ns=event['start'], sequence=event['sequence'], pair=event['pair'],
                    args=list(event['args']), result=event['result'], roots=[list(key) for key in call['roots']],
                    downgraded_read_tails=sum('downgrade' in root_stages[key] for key in call['roots']),
                    origin_wrapper_return_observed=True))
                state['call'] = None
            continue
        origin, depth, entry = int(found[2]), int(found[7]), int(found[8], 16)
        if origin not in states or depth or entry not in operation or states[origin]['call'] is None:
            continue
        event = dict(event=found[1], origin=origin, executor=int(found[3]), identity=int(found[4], 16),
                     generation=int(found[5]), object=int(found[6], 16), entry=entry, may_delegate=int(found[9]))
        key, call = identity(event), states[origin]['call']
        require(operation[entry] == call['entry']['op'] and key in completed and event['may_delegate'] and
                event['executor'] != origin and event['object'] == workers[origin]['backing'] and
                all(event[name] == completed[key][name] for name in ('origin', 'executor', 'identity', 'generation', 'entry')),
                'syscall root differs from completed audited other-task execution')
        if event['event'] == 'enter':
            require(key not in seen_roots, 'repeated root in syscall interval')
            seen_roots.add(key)
            roots[key] = ['enter']
            call['roots'].append(key)
        else:
            require(key in roots, 'root has no enter inside this syscall invocation')
            roots[key].append(event['event'])
            if event['event'] == 'returned':
                require(roots[key] in (['enter', 'release', 'returned'],
                    ['enter', 'downgrade', 'read_release', 'returned']), 'syscall root release sequence differs')
                root_stages[key] = roots.pop(key)
    require(summary is not None and not roots and all(state['call'] is None and state['address'] is None and
            1 <= state['pairs'] <= limit for state in states.values()), 'missing STOP or incomplete syscall pair')
    require(summary['tasks'] == len(workers) and summary['pairs'] == sum(state['pairs'] for state in states.values()),
            'syscall summary does not match sampled worker pairs')
    read_tails = sum(row['downgraded_read_tails'] for row in joined if row['operation'] == 'munmap')
    require(read_tails > 0, 'sampled munmap calls have no completed delegated downgraded read tail')
    return dict(passed=True, sample_limit=limit, completed_pairs=summary['pairs'], syscalls=joined,
        sampled_munmap_read_tails=read_tails,
        origin_wrapper_returns_observed=True, returned_address_pairs_observed=True,
        all_application_invocations_accounted=False, vma_contents_or_structure_observed=False,
        final_user_return_instruction_observed=False, fresh_reader_drain_observed=False,
        scope='bounded exact syscall-wrapper/address pairs; application progress remains separate')
