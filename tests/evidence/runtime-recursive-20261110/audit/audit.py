"""Independent stdlib receipt analysis; never import the runner/compiler or replay source."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path('/tmp/kdlock-live5-proof-audit')
COLLECTION = Path('/tmp/kdlock-live5-collection-20261110-UTC-01/guest/runtime')
fields = 'kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split()
names = 'SLOT_RESERVE SLOT_FREE ENQUEUE SELECT_LOCAL SELECT_PROXY GRANT PROXY_RETURN QUEUE_DONE NODE_RETIRE_READY RELEASE_BIND RELEASE_REQUEST RELEASE_DEFER RELEASE_UNWIND RELEASE_NOTIFY_DONE RELEASE_HANDLED RELEASE_SOURCE_DROP RELEASE_RETURN_DROP PHYSICAL_BEGIN PHYSICAL_END RELEASE_RETIRE OWNER_RETIRE FRAME_PREPARE JIT_ENTER JIT_EXIT JIT_OPERATION CHILD_RETURN EPISODE_DONE FORWARD NATIVE_UNLOCK OWNER_STOP'.split()
K = {n: i + 1 for i, n in enumerate(names)}
raw = (ROOT / 'observations-final.bin').read_bytes()
abi, words, capacity, count, overflow = struct.unpack_from('<5Q', raw)
assert (abi, words, capacity, count, overflow) == (1, 20, 65536, 4691, 0)
assert len(raw) == 40 + 160 * count
rows = [dict(zip(fields, values), row_id=i, name=names[values[0] - 1])
        for i, values in enumerate(struct.iter_unpack('<20Q', raw[40:]))]
result = json.loads((ROOT / 'result.json').read_text())
image = result['warm_image_identity']
assert result['status'] == 'protected_jit_recursive_mechanism_pass'
assert result['warm_claim_empty'] is True and result['observation_overflow'] == overflow


def one(scope, kind, **values):
    found = [r for r in scope if r['kind'] == K[kind] and all(r[k] == v for k, v in values.items())]
    assert len(found) == 1, (kind, values, [r['row_id'] for r in found])
    return found[0]


def record(row):
    # Preserve the exact 20 integers, a zero-based raw row ID and a readable tag.
    return row


def completion(scope, node, executor, expected):
    done = one(scope, 'EPISODE_DONE', node=node, task=executor, result=expected)
    start = one(scope, 'FRAME_PREPARE', node=node, acquisition=done['acquisition'])
    segment = [r for r in scope if start['row_id'] <= r['row_id'] <= done['row_id']
               and r['state'] == done['state']]
    assert done['flags'] & 1536 == 1536
    assert not any(r['name'] == 'FORWARD' for r in segment)
    enters = [r for r in segment if r['name'] == 'JIT_ENTER']
    exits = [r for r in segment if r['name'] == 'JIT_EXIT']
    assert enters and len(enters) == len(exits)
    assert all(r['image'] == image and r['task'] != r['origin'] for r in enters)
    assert all(r['image'] == image and r['result'] == 1 for r in exits)
    unlocks = [r for r in segment if r['name'] == 'JIT_OPERATION' and r['result'] == 2 and r['related'] == node]
    assert unlocks
    calls = {r['site']: r for r in result['actual_call_records'] if r.get('operation') == 'unlock'}
    for unlock in unlocks:
        call = calls[unlock['ip']]
        source = bytes.fromhex(call['raw_hex'])
        assert source[0] == 0xe8 and len(source) == call['length'] == 5
        assert (call['site'] + 5 + int.from_bytes(source[1:], 'little', signed=True)) % (1 << 64) == call['target']
        assert unlock['cursor'] == call['site'] + 5 and unlock['image'] == image
        assert any(r['ip'] == unlock['ip'] and r['related'] == call['target'] for r in exits)
    return {'done': record(done), 'frame': record(start), 'enters': enters, 'exits': exits,
            'accepted_unlocks': unlocks, 'forward_count': 0}


def release_proof(scope, enqueue, done):
    node, state, acq = enqueue['node'], enqueue['state'], enqueue['acquisition']
    grant = one(scope, 'GRANT', node=node, state=state, acquisition=acq)
    owner, executor, release = grant['owner'], grant['owner_task'], grant['related']
    member = [r for r in scope if r['owner'] == owner and r['related'] == release and
              r['state'] == state and r['acquisition'] == acq]
    bind = one(member, 'RELEASE_BIND'); assert bind['source_user']
    requested = one(member, 'RELEASE_REQUEST', phase=1)
    handled = one(member, 'RELEASE_HANDLED', phase=4, task=executor)
    returned = [r for r in member if r['name'] == 'RELEASE_RETURN_DROP']
    stopped = one(scope, 'OWNER_STOP', owner=owner, task=executor)
    assert stopped['flags'] & 128
    begin = one(scope, 'PHYSICAL_BEGIN', owner=owner, task=executor, object=grant['object'], phase=1)
    end = one(scope, 'PHYSICAL_END', owner=owner, task=executor, object=grant['object'], phase=2, result=0)
    assert begin['related'] == end['related'] and begin['related']
    drop = one(member, 'RELEASE_SOURCE_DROP', phase=5, source_user=bind['source_user'])
    retired = one(member, 'RELEASE_RETIRE', phase=6, task=executor)
    ready = one(scope, 'NODE_RETIRE_READY', node=node, state=state, acquisition=acq, phase=6)
    free = one(scope, 'SLOT_FREE', node=node, state=state, acquisition=acq, phase=3)
    owner_retired = one(scope, 'OWNER_RETIRE', owner=owner, task=executor, phase=3)
    assert bind['row_id'] < requested['row_id'] < handled['row_id'] < begin['row_id'] < end['row_id']
    assert stopped['row_id'] < begin['row_id'] and done['row_id'] < stopped['row_id']
    assert end['row_id'] < drop['row_id'] < retired['row_id'] < ready['row_id'] < free['row_id']
    assert end['row_id'] < owner_retired['row_id']
    assert ready['flags'] & 15 == 15 and not ready['flags'] & 16
    assert free['flags'] & 0x86f == 0x86f and not free['flags'] & 16
    assert all(not r[k] for r in (retired, ready, free) for k in ('source_user', 'return_user', 'notifier'))
    out = {'node': node, 'state': state, 'acquisition': acq, 'object': grant['object'],
           'original_owner': owner, 'original_owner_task': executor, 'release': release,
           'grant': grant, 'bind': bind, 'request': requested, 'handled': handled,
           'control_stopped': stopped, 'physical_begin': begin, 'physical_end': end,
           'source_drop': drop, 'return_drops': returned, 'release_retire': retired,
           'node_retire_ready_before_store': ready, 'slot_free_after_retirable_acquire': free,
           'owner_retire': owner_retired}
    if requested['result'] == 2:
        deferred = one(member, 'RELEASE_DEFER', phase=2, result=2)
        unwind = one(member, 'RELEASE_UNWIND', phase=3, result=2, notifier=deferred['notifier'])
        notified = one(member, 'RELEASE_NOTIFY_DONE', notifier=deferred['notifier'])
        assert deferred['notifier'] and requested['return_user']
        returned_token = one(member, 'RELEASE_RETURN_DROP', return_user=requested['return_user'])
        assert requested['return_user'] == deferred['return_user'] == unwind['return_user']
        assert requested['row_id'] < deferred['row_id'] < unwind['row_id'] < handled['row_id']
        assert done['row_id'] > unwind['row_id']  # Root completes after the inner export notification.
        assert notified['row_id'] < retired['row_id'] and returned_token['row_id'] < retired['row_id']
        out.update(deferred=deferred, unwind=unwind, notification_done=notified,
                   exact_return_drop=returned_token)
    return out


proofs = []
table = ['# Independent live5 raw-event audit', '',
         'IDs are zero-based payload row numbers after the 40-byte header. No project code or runner oracle was imported or executed.', '',
         '| Case | Exact generated execution and return rows | Physical release and retirement rows |',
         '| --- | --- | --- |']
for case in result['warm_completion'][1:]:
    mode = case['mode']; scope = rows[case['start']:case['end']]
    W = case['roles'][4]; CA = case['roles'][2]; CB = case['roles'][3]
    root = one(scope, 'ENQUEUE', node=case['root'], origin=W, task=W, state=case['state'])
    child = one(scope, 'ENQUEUE', node=case['child'], origin=W, task=CA, state=case['state'])
    assert root['node'] != child['node'] and root['acquisition'] != child['acquisition']
    parent_head = one(scope, 'SELECT_LOCAL', node=root['related'], task=CA, owner_task=CA)
    child_head = one(scope, 'SELECT_LOCAL', node=child['related'], task=CB, owner_task=CB)
    select_root = one(scope, 'SELECT_PROXY', node=root['node'], task=CA, owner=parent_head['owner'])
    select_child = one(scope, 'SELECT_PROXY', node=child['node'], task=CB, owner=child_head['owner'])
    assert root['row_id'] < select_root['row_id'] and child['row_id'] < select_child['row_id']
    cprepare = one(scope, 'FRAME_PREPARE', node=child['node'], parent=root['node'], state=case['state'])
    lock = one(scope, 'JIT_OPERATION', node=root['node'], related=child['node'], result=1, task=CA)
    a = completion(scope, root['node'], CA, 3)
    b = completion(scope, child['node'], CB, 5 if mode == 2 else 3)
    returning = one(scope, 'CHILD_RETURN', node=root['node'], related=child['node'], task=CA)
    assert returning['result'] == b['done']['result'] and returning['flags'] & 1024
    assert returning['source_user'] == a['enters'][0]['related']
    assert len({returning['source_user'], returning['return_user'], b['done']['related']}) == 3
    assert b['done']['row_id'] < returning['row_id'] < a['done']['row_id']
    assert returning['cursor'] == b['done']['cursor']
    assert a['enters'][0]['row_id'] < lock['row_id'] < child['row_id'] < b['enters'][0]['row_id']
    if mode == 1:
        resume = one(scope, 'JIT_ENTER', node=root['node'], task=CA,
                     related=returning['return_user'], cursor=returning['cursor'])
        assert returning['row_id'] < resume['row_id'] < a['done']['row_id']
    else:
        resume = None
        assert a['done']['related'] == returning['return_user'] and a['done']['cursor'] == returning['cursor']
    A = release_proof(scope, root, a['done']); B = release_proof(scope, child, b['done'])
    if mode == 2:
        assert b['done']['row_id'] < A['unwind']['row_id'] < returning['row_id']
        assert A['request']['task'] == CB and A['handled']['task'] == CA
        outer_op = one(scope, 'JIT_OPERATION', node=child['node'], related=root['node'], result=2, task=CB, phase=2)
        assert A['deferred']['row_id'] < outer_op['row_id'] < b['done']['row_id']
    else:
        outer_op = None
    status = dict(token.split('=', 1) for token in case['raw_status'].split() if '=' in token)
    assert int(status['w_core'], 16) == int(status['w_regs'], 16) == case['state']
    assert status['finished'] == '5' and status['overflow'] == '0'
    source = {'mode': mode, 'row_window': [case['start'], case['end']], 'state': case['state'],
        'worker_regs_address': int(status['w_regs'], 16), 'native_status': case['raw_status'],
        'W': W, 'C_A': CA, 'C_B': CB, 'fixed_image': image,
        'root_enqueue': root, 'child_enqueue': child, 'root_head': parent_head,
        'child_head': child_head, 'root_proxy_selection': select_root, 'child_proxy_selection': select_child,
        'child_frame_parent': cprepare, 'accepted_child_lock': lock,
        'root_generated': a, 'child_generated': b, 'child_return': returning,
        'parent_generated_reentry': resume, 'outer_deferred_operation': outer_op,
        'root_physical_and_retirement': A, 'child_physical_and_retirement': B}
    proofs.append(source)
    table.append(f"| Recursive {mode} | CA enter {a['enters'][0]['row_id']} → child enqueue {child['row_id']} → CB enter {b['enters'][0]['row_id']} → child DONE {b['done']['row_id']} ({b['done']['result']}) → CA returned {returning['row_id']} → root DONE {a['done']['row_id']} (3) | A callback {A['physical_begin']['row_id']}/{A['physical_end']['row_id']}, source drop {A['source_drop']['row_id']}, retire/ready/free {A['release_retire']['row_id']}/{A['node_retire_ready_before_store']['row_id']}/{A['slot_free_after_retirable_acquire']['row_id']}; B callback {B['physical_begin']['row_id']}/{B['physical_end']['row_id']}, source drop {B['source_drop']['row_id']}, retire/ready/free {B['release_retire']['row_id']}/{B['node_retire_ready_before_store']['row_id']}/{B['slot_free_after_retirable_acquire']['row_id']} |")

plain = result['warm_completion'][0]; plainrows = rows[plain['start']:plain['end']]
plain_proofs = []
for selected in (r for r in plainrows if r['name'] == 'SELECT_PROXY'):
    previous = [r for r in plainrows if r['name'] == 'FRAME_PREPARE' and r['node'] == selected['node'] and r['row_id'] < selected['row_id']]
    assert previous
    start = previous[-1]['row_id']
    ends = [r for r in plainrows if r['name'] == 'SLOT_FREE' and r['node'] == selected['node'] and r['row_id'] > selected['row_id']]
    stop = ends[0]['row_id'] if ends else plain['end'] - 1
    section = [r for r in plainrows if start <= r['row_id'] <= stop]
    item = completion(section, selected['node'], selected['task'], 3)
    plain_proofs.append({'selection': selected, 'generated': item})
assert plain_proofs

publications = []
previous = 0
for path in sorted(COLLECTION.glob('cycle-*/commit.bin')):
    payload = path.read_bytes(); header = struct.unpack_from('<4Q', payload)
    assert header[:2] == (1, 4) and header[2] == len(payload)
    values = struct.unpack_from('<14Q', payload, 32)
    assert values[6] == values[8] == previous
    publications.append({'path': str(path), 'publication': values[0], 'old': values[6],
                         'new': values[7], 'returned_old': values[8], 'included_count': header[3]})
    previous = values[7]
assert len(publications) == 4 and previous == image
summary = {'status': 'INDEPENDENT_RAW_EVENT_RELATIONS_VERIFIED',
    'scope': 'Protected JIT lock/unlock episodes and selected recursive/deferred mechanism; no whole-C-function JIT epilogue, general progress or performance claim.',
    'header': {'abi': abi, 'words': words, 'capacity': capacity, 'count': count, 'overflow': overflow},
    'row_numbering': 'zero based, first 160-byte payload row after 40-byte header is 0',
    'inputs': {n: {'bytes': (ROOT/n).stat().st_size, 'sha256': hashlib.sha256((ROOT/n).read_bytes()).hexdigest()}
               for n in ('observations-final.bin', 'result.json', 'source-metadata.json')},
    'fixed_image_publications': publications, 'warm_plain_positive_count': len(plain_proofs),
    'warm_plain_proofs': plain_proofs, 'recursive_cases': proofs}
(ROOT / 'proof.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
table += ['', f"Warm plain: {len(plain_proofs)} exact proxy selections each have a positive protected DONE with actual fixed-image entry/exit and accepted unlock; no native forward in those intervals.", '',
    'Mode 2 outer A: request 4636 → deferred marker 4637 → inner DONE 4644 → post-export unwind publication 4645 → release notifier membership drops 4646 → actual original owner handles 4660; return token drops 4662. The frozen source places unwind publication after common-drive binding export; row 4644 itself is the pre-export completion event. Physical A release follows later at 4678/4680; source user drops 4683, all three release users are zero at retirement 4684. Physical completion and final slot retirement are distinct observations.', '',
    'READY records precede the final retirable store. FREE flags 0x86f independently observe acquired retirable, queue/result completion, no result user, empty pool users and idle controls; their three release-user fields are zero. OWNER_RETIRE is recorded separately. Scalar identities are joined within SLOT lifetimes, never treated as new references.', '',
    'The four actual publication replies chain old/new/returned-old identities to the fixed fourth image. EPISODE_DONE intentionally has image 0; image association comes from its exact preceding JIT entry/exit/accepted-operation records.']
(ROOT / 'proof.md').write_text('\n'.join(table) + '\n')
print(json.dumps({'status': summary['status'], 'plain_positive': len(plain_proofs),
    'recursive_cases': len(proofs), 'fixed_image': hex(image),
    'proof_sha256': hashlib.sha256((ROOT/'proof.json').read_bytes()).hexdigest()}, indent=2))
