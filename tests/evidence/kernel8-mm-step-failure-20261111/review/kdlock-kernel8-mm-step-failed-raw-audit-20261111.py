#!/usr/bin/env python3
"""Read recovered failed-run records with the standard library only."""
from pathlib import Path
from collections import Counter, defaultdict
import base64
import hashlib
import json
import struct

B = Path('/tmp/kdlock-kernel8-mm-step-collection-20261111-02')
P = B / 'payload/runtime'
OUT = Path('/tmp/kdlock-kernel8-mm-step-failed-raw-audit-20261111.json')
inputs = {}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def raw(p):
    b = Path(p).read_bytes()
    inputs[str(p)] = {'bytes': len(b), 'sha256': sha(b)}
    return b


def load(p):
    return json.loads(raw(p))


def check(v, why):
    if not v:
        raise ValueError(why)


def one(rows, why):
    check(len(rows) == 1, (why, len(rows)))
    return rows[0]


def frame(b, op, fixed, row_words, blobs):
    a, o, size, n = struct.unpack_from('<4Q', b)
    check((a, o, size) == (1, op, len(b)), 'frame header')
    at = 32
    f = struct.unpack_from('<%dQ' % fixed, b, at) if fixed else ()
    at += 8 * fixed
    rs = []
    for _ in range(n):
        rs.append(struct.unpack_from('<%dQ' % row_words, b, at))
        at += 8 * row_words
    bs = []
    for _ in range(blobs):
        length, = struct.unpack_from('<Q', b, at)
        at += 8
        bs.append(b[at:at+length])
        check(len(bs[-1]) == length, 'short blob')
        at += length
    check(at == len(b), 'frame exact consumption')
    return f, rs, bs


ix = load(B / 'copy-index.json')
check(inputs[str(B / 'copy-index.json')]['sha256'] == '67d00a8ad3f909a7d7bd0ae4c0c649499993bf212d9775e68d8ad5c9a76cc001', 'index pin')
transport = load(B / 'transport.json')
check(len(ix['files']) == len(transport['files']) == 224, '224 selected files')
selected = {}
for r in ix['files']:
    check(r['path'] not in selected and r['identity_before'] == r['identity_after'], 'exact selected identity')
    b = raw(B / 'payload' / r['path'])
    check(len(b) == r['bytes'] and sha(b) == r['sha256'], ('payload', r['path']))
    selected[r['path']] = r
for r in transport['files']:
    b = base64.b64decode(r['data'], validate=True)
    e = selected[r['path']]
    check(len(b) == e['bytes'] == r['bytes'] and sha(b) == e['sha256'] == r['sha256'] and
          b == raw(B / 'payload' / r['path']), 'transport decoded equality')
check(sum(r['bytes'] for r in ix['files']) == 30666498, 'selected bytes')
j = load(P / 'result.json')
check(sha(raw(P / 'result.json')) == 'fd06287ab267b6ef682c623140dbd2735c20a4dfe6f83c5e574bf4fe8cbe99e6', 'inner pin')
check(j['status'] == 'failed_retained' and j['overall_pass'] is False and j['client_returncode'] is None, 'failed verdict preserved')
config = load(P / 'config.json')
check(sha(raw(P / 'config.json')) == j['config_sha256'] ==
      '3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1', 'actual failed run config')
check(sha(raw(P / 'jit_config.input')) == config['sha256']['jit_config'] ==
      'e6b3a905e9cc0952adb3092f3334757cbf3e4ecbcd1efc5071c8b02831f3383b', 'exact 438 byte input')
check(j['boot_id'] == transport['failed_run_boot_id'] == '4a98638f-c01c-4fc9-8de8-69a74346aa0f' and
      transport['boot_id'] == ix['boot_id'] == 'f1442f01-e060-46fa-a480-da508d7ce8a9' and
      transport['recovery_reset_before_copy'] is True, 'failure and recovery collection boots separate')

fields = 'kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split()
old = []
snapshots = []
for f in sorted(P.glob('events-*.bin')):
    b = raw(f)
    abi, words, capacity, n, overflow = struct.unpack_from('<5Q', b)
    check((abi, words, overflow) == (1, 20, 0) and n <= capacity and len(b) == 40 + n*160, 'snapshot layout')
    rows = [dict(zip(fields, r), index=i) for i, r in enumerate(struct.iter_unpack('<20Q', b[40:]))]
    check(rows[:len(old)] == old, 'cumulative raw event prefix')
    old = rows
    snapshots.append({'file': f.name, 'count': n})
rows = old
check(len(rows) == 19248 and len(snapshots) == 5, 'saved event limit')
embedded = 0


def embedded_check(x):
    global embedded
    if isinstance(x, dict):
        if set(x) == set(fields + ['index']):
            check(x == rows[x['index']], 'embedded event/raw equality')
            embedded += 1
        else:
            for v in x.values():
                embedded_check(v)
    elif isinstance(x, list):
        for v in x:
            embedded_check(v)


embedded_check(j)
for f in sorted(P.glob('completion-round-*.json')):
    embedded_check(load(f))

meta = load(P / 'source-metadata.json')
source = raw(P / 'source-export.bin')
check(source == raw(P / 'wire/attempt-00000002/reply.bin'), 'source wire equality')
abi, op, size, region_count = struct.unpack_from('<4Q', source)
check((abi, op, size, region_count) == (1, 8, len(source), 5), 'source header')
epoch, configuration, image_load, gs, bc, slot, old_image = struct.unpack_from('<7Q', source, 32)
check(old_image == 0, 'cold source export')
at = 88
regions = []
for n in range(region_count):
    start, length = struct.unpack_from('<2Q', source, at)
    at += 16
    b = source[at:at+length]
    at += length
    check(b == raw(P / ('source-%d.bin' % n)), 'source exact region')
    check(meta['regions'][n] == {'start': start, 'length': length, 'sha256': sha(b)}, 'source metadata')
    regions.append((start, b))
at += 16 * bc
vl, = struct.unpack_from('<Q', source, at)
at += 8
version = source[at:at+vl]
check(at+vl == len(source) and version.hex() == meta['version_hex'] and sum(len(b) for _, b in regions) == 3214, 'source exact version and size')


def source_bytes(ip, n):
    return one([b[ip-s:ip-s+n] for s, b in regions if s <= ip and ip+n <= s+len(b)], 'source membership')


for call in meta['calls']:
    b = source_bytes(call['site'], call['length'])
    check(b.hex() == call['raw_hex'] and b[0] == 0xe8 and len(b) == 5 and
          call['site'] + 5 + struct.unpack_from('<i', b, 1)[0] == call['target'], 'direct raw CALL arithmetic')
check(source_bytes(0xffffffff818321c0, 5).hex() == '0f1f440000', 'new callee actual live entry NOP')
check(source_bytes(0xffffffff81832246, 5).hex() == 'e8c5d5cfff' and
      source_bytes(0xffffffff81832349, 5).hex() == 'e872f0ffff', 'query and next CALL raw bytes')

wire = []
for d in sorted((P / 'wire').iterdir()):
    rm = load(d / 'request.json')
    rt = load(d / 'result.json')
    request, reply = raw(d / 'request.bin'), raw(d / 'reply.bin')
    e = struct.unpack('<9Q', raw(d / 'returned-envelope.bin'))
    check(e[:3] == (1, rm['operation'], rm['sequence']) and e[4] == len(request) == rm['request_bytes'] and
          e[6] == rm['output_capacity'] and e[7] == len(reply) == rt['reply_bytes'] and
          e[8] == rt['status'] == 0 and rt['completed_response'] is True and e[2] == rt['sequence'], 'successful exact wire attempt')
    wire.append({'attempt': d.name, 'operation': rm['operation'], 'sequence': rm['sequence']})
check([r['operation'] for r in wire] == [0, 8, 1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], 'wire exact operations; no shutdown/archive/settlement')
images = []
publication_details = []
for cycle, build_attempt, stage_attempt, publish_attempt, ack_attempt in [(1, 4, 5, 6, 7), (2, 10, 11, 12, 13)]:
    d = P / ('cycle-%04d' % cycle)
    path = lambda a, n: P / 'wire' / ('attempt-%08d' % a) / n
    build, _, _ = frame(raw(path(build_attempt, 'reply.bin')), 2, 12, 0, 4)
    candidate, bs, image, ins, producer, update, owner, previous, emission, ep, base, cap = build
    check(bs == slot and ep == epoch and previous == (images[-1] if images else 0), 'candidate immutable slot/epoch/base')
    stage, sr, blobs = frame(raw(path(stage_attempt, 'request.bin')), 3, 1, 0, 5)
    check(stage == (candidate,) and not sr and blobs == [raw(d/'image.S'), raw(d/'metadata.c'), raw(d/'manifest.json'), raw(d/'machine-code.bin'), raw(d/'flat-metadata.bin')], 'actual STAGE exact producing artifacts')
    pub, prs, _ = frame(raw(path(publish_attempt, 'reply.bin')), 4, 14, 2, 0)
    check((pub[3], pub[4], pub[5], pub[6], pub[7], pub[9], pub[10], pub[11], pub[12], pub[13]) ==
          (slot, update, owner, previous, image, epoch, emission, ins, producer, candidate) and not prs, 'publication exact candidate source image')
    ack, ackrows, _ = frame(raw(path(ack_attempt, 'reply.bin')), 5, 5, 2, 0)
    check(not ackrows and ack[1] == pub[0], 'zero coverage ACK rows')
    manifest = load(d/'manifest.json')
    for s in manifest['source_sites']:
        check(source_bytes(int(s['ip'], 16), s['length']).hex() == s['bytes_hex'], 'producing manifest source bytes')
    for n in range(4):
        gnu = load(d / ('gnu-%02d.json' % n))
        check(gnu['returncode'] == 0 and gnu['diagnostic_sha256'] == sha(raw(d / ('gnu-%02d.log' % n))), 'actual GNU result')
    entries = [int(x, 0) if isinstance(x, str) else x for x in manifest['entry_sites']]
    check(entries == j['cycles'][cycle-1]['entry_sites'] and j['cycles'][cycle-1]['image'] == image, 'actual compiled entry set')
    images.append(image)
    publication_details.append({'cycle': cycle, 'image': image, 'producer': producer, 'publication': pub[0], 'entries': entries})
check(0xffffffff8183224b not in publication_details[0]['entries'] and 0xffffffff8183224b in publication_details[1]['entries'], 'observed reentry addition')

by = defaultdict(list)
by_control = defaultdict(list)
by_owner = defaultdict(list)
for e in rows:
    by[tuple(e[k] for k in ('state', 'node', 'acquisition', 'origin'))].append(e)
    by_control[(e['state'], e['acquisition'])].append(e)
    by_owner[e['owner']].append(e)
queries = [e for e in rows if e['kind'] == 44]
check(len(queries) == 81, '81 saved query results')
witnesses = []
for q in queries:
    scope = by[tuple(q[k] for k in ('state', 'node', 'acquisition', 'origin'))]
    ctrl = by_control[(q['state'], q['acquisition'])]
    pick = lambda k: one([e for e in scope if e['kind'] == k], ('query episode kind', k))
    reserve, free, grant, exit, operation = [pick(k) for k in (1, 2, 6, 24, 25)]
    enters = [e for e in scope if e['kind'] == 23]
    check(len(enters) == 2 and [e['cursor'] for e in enters] == [0xffffffff817ef5ea, 0xffffffff8183224b], 'root and lookup attempts')
    check(q['image'] == exit['image'] == enters[0]['image'] == enters[1]['image'] == images[0] and
          q['task'] == exit['task'] == operation['task'] == grant['owner_task'] == enters[0]['task'] == enters[1]['task'] != q['origin'], 'exact foreign source and producing image')
    check((exit['ip'], exit['cursor'], exit['related'], exit['result'], exit['phase'], exit['flags']) ==
          (0xffffffff81832246, 0xffffffff81832246, 0xffffffff8152f810, 1, 1, 4), 'pre-CALL typed query exit')
    check((operation['ip'], operation['cursor'], operation['result'], operation['phase'], operation['object']) ==
          (0xffffffff81832246, 0xffffffff8152f810, 17, 2, grant['object']), 'exact prepared physical query')
    check((q['ip'], q['cursor'], q['related'], q['result'], q['phase'], q['object']) ==
          (0xffffffff81832246, 0xffffffff8183224b, 17, 1, 5, grant['object']), 'writer held query true exact return')
    forwarded = pick(28)
    check((forwarded['cursor'], forwarded['related'], forwarded['ip'], forwarded['result'], forwarded['phase'], forwarded['flags']) ==
          (0xffffffff8183224b, 0xffffffff8152f810, 0xffffffff81832246, (1<<64)-2, 0, 0), 'undeclared lookup exact native handback')
    check(enters[0]['index'] < exit['index'] < operation['index'] < q['index'] < enters[1]['index'] < forwarded['index'], 'query/reentry order')
    check(all(reserve[k] == free[k] for k in ('related', 'owner', 'parent')) and free['origin'] == q['origin'], 'exact query slot retirement')
    find_control = lambda k: one([e for e in ctrl if e['kind'] == k], ('query control', k))
    request, source_drop, retire, native = [find_control(k) for k in (11, 16, 20, 29)]
    owner_scope = [e for e in by_owner[grant['owner']] if grant['index'] <= e['index'] < free['index']]
    pb, pe, ore = [one([e for e in owner_scope if e['kind'] == k], ('owner', k)) for k in (18, 19, 21)]
    check(request['task'] == native['task'] == source_drop['task'] == q['origin'] and
          request['related'] == source_drop['related'] == retire['related'] == grant['related'] and
          request['source_user'] == source_drop['source_user'] != 0 and retire['source_user'] == 0, 'native source and exact release user')
    check(forwarded['index'] < request['index'] < pb['index'] < pe['index'] < native['index'] < source_drop['index'] < retire['index'] < ore['index'] < pick(9)['index'] < free['index'], 'complete observed query release order')
    witnesses.append({'state': q['state'], 'node': q['node'], 'acquisition': q['acquisition'], 'origin': q['origin'],
                      'executor': q['task'], 'owner': grant['owner'], 'image': q['image'],
                      'events': {'reserve': reserve['index'], 'grant': grant['index'], 'root_enter': enters[0]['index'],
                                 'query_exit': exit['index'], 'operation': operation['index'], 'query_result': q['index'],
                                 'post_query_attempt': enters[1]['index'], 'forward': forwarded['index'],
                                 'physical_begin': pb['index'], 'physical_end': pe['index'], 'native_unlock': native['index'],
                                 'source_drop': source_drop['index'], 'release_retire': retire['index'],
                                 'owner_retire': ore['index'], 'free': free['index']}})
check(len(j['reentry_candidates']) == 81 and all(x['accepted'] and x['entry'] == 0xffffffff8183224b for x in j['reentry_candidates']) and
      sum(x['new_entry'] for x in j['reentry_candidates']) == 1, 'host exact observed reentry candidates')
check({x['observation']['index'] for x in j['reentry_candidates']} == {q['index'] for q in queries}, 'host reentry candidates raw query equality')
all_enters = [e for e in rows if e['kind'] == 23]
all_exits = [e for e in rows if e['kind'] == 24]
check(len(all_enters) == 207 and len(all_exits) == 126 and all(e['image'] == images[0] for e in all_enters+all_exits), 'attempt versus execution accounting')
munmap = [e for e in all_exits if e['result'] == 3]
check(len(munmap) == 45 and all((e['ip'], e['cursor'], e['related'], e['phase'], e['flags']) ==
      (0xffffffff8185af54, 0xffffffff81858430, 0xffffffff81858430, 2, 1) for e in munmap), 'retained munmap callee-entry frontier')
check(not any(e['kind'] in (23, 24, 28) and e['cursor'] == 0xffffffff818313c0 for e in rows), 'no saved later mmap helper reach')
check(not any(e['kind'] in (23, 24) and e['image'] == images[1] for e in rows), 'no saved second-image execution')
claim_values, facts, tails = frame(raw(P/'cycle-0002/claim.bin'), 1, 3, 12, 1)
check(len(facts) == 45 and claim_values[2] == epoch and tails == [version] and
      all(r[3] == images[0] and r[4:10] == (3, 1, 0xffffffff8185af54, 0xffffffff81858430, 0xffffffff81858430, 2) for r in facts), '45 claimed direct munmap facts')
check(len({r[:2] for r in facts}) == 45 and
      all(r[2] == publication_details[0]['producer'] and r[10:12] == (0, 0) for r in facts), 'distinct exact producer fact keys without observation credit')

stdout = [json.loads(s) for s in raw(P/'client.stdout').decode().splitlines()]
check(stdout == [load(P/('phase-%04d.json' % n)) for n in range(3)] and j['rounds'] == stdout[1:], 'actual completed stdout phases')
totals = Counter()
rounds = []
for n, r in enumerate(j['rounds'], 1):
    w = r['workload']
    check(r['round'] == r['completed_rounds'] == n and w['status'] == 'syscall_completion_pass' and w['overall_pass'] is True and
          w['threads'] == w['created_threads'] == 8 and w['iterations_per_thread'] == 8 and w['completed_iterations'] == 64 and
          w['worker_errors'] == 0 and w['setup_errno'] == w['arena_cleanup_errno'] == 0 and not w['deadline_exceeded'], 'completed syscall round')
    check(len(w['workers']) == 8 and len({x['tid'] for x in w['workers']}) == 8, 'eight actual worker TIDs')
    for worker in w['workers']:
        expected = {'completed': 8, 'mmap_attempts': 24, 'mmap_successes': 24, 'munmap_attempts': 16,
                    'munmap_successes': 16, 'mincore_attempts': 32, 'unmapped_page_checks': 32,
                    'reuse_successes': 8, 'fresh_zero_bytes': 32*w['page_bytes'],
                    'written_bytes': 32*w['page_bytes'], 'readback_bytes': 32*w['page_bytes']}
        check(all(worker[k] == v for k, v in expected.items()) and worker['errno'] == 0 and worker['error'] == 'none' and not worker['deadline_reached'], 'exact worker effects')
        check(worker['slot_address'] == w['arena_address']+(4*worker['id']+1)*w['page_bytes'], 'slot/guard geometry')
        totals.update(expected)
    rounds.append({'round': n, 'completed_iterations': 64, 'worker_tids': [x['tid'] for x in w['workers']],
                   'physical_begins': r['profile']['native']['physical_begins'], 'physical_ends': r['profile']['native']['physical_ends'],
                   'snapshot_pool_idle': r['profile']['native']['pool_idle']})

fault_state, fault_node, fault_acq = 0xff11000113ce5c00, 0xff11000109f80068, 0xff11000109f80329
earlier = [e for e in rows if e['node'] == fault_node and e['acquisition'] == fault_acq]
check(not any(e['state'] == fault_state for e in rows), 'fault state absent from retained prefix')
prior = []
for key, es in by.items():
    if key[1:3] == (fault_node, fault_acq):
        rr = [e for e in es if e['kind'] == 1]
        ff = [e for e in es if e['kind'] == 2]
        if not rr:
            continue
        prior.append({'state': key[0], 'origin': key[3], 'first_index': es[0]['index'], 'last_index': es[-1]['index'],
                      'reserves': [e['index'] for e in rr], 'frees': [e['index'] for e in ff]})
check(len(prior) == 2 and len(earlier) == 28, 'reused node/acquisition addresses require incarnation disambiguation')
serial_path = Path('/tmp/kdlock-kernel8-mm-step-20261111-01/serial-full-01/first-diagnostic.txt')
first = raw(serial_path)
check(b'kernel BUG at kernel/kdlock/kernel/jit.c:855!' in first and b'Oops: invalid opcode: 0000 [#1]' in first and
      b'kd_jit_acquire+0x45d/0x4b0' in first and b'RAX: 00000000fffffff0' in first, 'first-fault evidence')
report = {
    'status': 'FAILED_RUN_RETAINED_PREFIX_AUDIT_COMPLETE', 'runtime_verdict': j['status'], 'overall_pass': False,
    'error': j['error'], 'client_returncode': None,
    'selected_files': 224, 'selected_bytes': 30666498, 'transport_base64_all_exact': True,
    'failed_boot': j['boot_id'], 'collection_after_reset_boot': transport['boot_id'],
    'config_sha256': j['config_sha256'],
    'snapshots': snapshots, 'saved_event_count': len(rows), 'embedded_raw_events_checked': embedded,
    'completed_rounds': rounds, 'completed_worker_totals': dict(totals), 'requested_rounds': 3,
    'third_round_complete_receipt_present': False, 'third_round_work_not_inferred': True,
    'source_regions': 5, 'source_bytes': 3214, 'do_mmap_actual_first_five_bytes': source_bytes(0xffffffff818321c0, 5).hex(),
    'query_call_bytes': source_bytes(0xffffffff81832246, 5).hex(), 'query_target': 0xffffffff8152f810,
    'query_post_return': 0xffffffff8183224b, 'query_result_count': len(queries), 'query_all_predicates': [1],
    'query_lifetimes_with_matching_slot_free': len(witnesses), 'query_witnesses': witnesses,
    'entry_attempts': len(all_enters), 'executed_entries_with_exit': len(all_exits),
    'executed_root_counts': {'mmap_query_prefix': 81, 'munmap_prefix': 45},
    'post_query_attempts': 81, 'post_query_executed_entries_with_exit': 0,
    'post_query_handback': 'Image1 lacks this entry: exact -ENOENT forward to 0xffffffff8183224b after one completed query; no query replay.',
    'accepted_reentry_candidates': 81, 'new_reentry_entries': 1,
    'publications': publication_details, 'second_image_runtime_entry_observed': False,
    'next_mmap_helper': {'source_callsite': 0xffffffff81832349, 'raw_bytes': source_bytes(0xffffffff81832349, 5).hex(),
                         'callee': 0xffffffff818313c0, 'admitted_source': False, 'runtime_handback_observed': False},
    'munmap_call_staged_exits': 45, 'munmap_unexecuted_callee': 0xffffffff81858430,
    'claimed_direct_call_facts': len(facts), 'coverage_ack_rows': 0, 'shutdown_archive_settle_commands_present': False,
    'no_saved_archive_or_settle_receipt': True, 'no_final_cleanup_or_drain_claim': True,
    'protected_mm_completion': 'not established by this failed record',
    'first_fault': {'source': 'jit.c:855', 'rip': 'kd_jit_acquire+0x45d/0x4b0', 'error': '-EBUSY',
                    'state_rbx': fault_state, 'node_r14': fault_node, 'acquisition_r15': fault_acq,
                    'matching_state_rows': 0, 'earlier_same_node_acquisition_rows': len(earlier),
                    'earlier_other_state_incarnations': prior,
                    'actual_failing_queue_interleaving_observed': False,
                    'limitation': 'Earlier address reuse does not connect other S_W incarnations to the failed source state. No third-round snapshot was saved.'},
    'wire': wire, 'event_counts': dict(Counter(e['kind'] for e in rows)),
    'scope': 'Offline standard-library reads of recovered saved records only; no test, VM command, cleanup, replay or source mutation.',
    'inputs': inputs, 'script_sha256': sha(Path(__file__).read_bytes()),
}
OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'path': str(OUT), 'bytes': OUT.stat().st_size, 'sha256': sha(OUT.read_bytes()),
                  'script_sha256': report['script_sha256'], 'status': report['status'],
                  'completed_iterations': totals['completed'], 'queries': len(queries),
                  'post_query_executed': 0, 'later_mmap_helper_observed': False}, sort_keys=True))
