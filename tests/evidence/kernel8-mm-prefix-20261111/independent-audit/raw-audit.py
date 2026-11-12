#!/usr/bin/env python3
"""Read saved MM prefix bytes with the Python standard library only."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import struct
import tarfile

BASE = Path('/tmp/kdlock-kernel8-mm-prefix-collection-20261111-01')
P = BASE / 'payload/runtime'
OUT = Path('/tmp/kdlock-kernel8-mm-prefix-independent-audit-20261111.json')
SELF = Path(__file__)
inputs = {}


def digest(b):
    return hashlib.sha256(b).hexdigest()


def raw(p):
    p = Path(p)
    b = p.read_bytes()
    inputs[str(p)] = {'bytes': len(b), 'sha256': digest(b)}
    return b


def load(p):
    return json.loads(raw(p))


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def one(seq, detail):
    require(len(seq) == 1, (detail, len(seq)))
    return seq[0]


def token(x):
    return int.from_bytes(bytes.fromhex(x['bytes_hex']), 'little')


def fact_key(x):
    f = x['fields']
    return (token(f['epoch_identity']), token(f['record_identity']), f['incarnation'])


def frame(b, operation, fixed, row_words, blobs):
    abi, op, size, count = struct.unpack_from('<4Q', b)
    require((abi, op, size) == (1, operation, len(b)), ('frame header', operation))
    at = 32
    values = struct.unpack_from('<' + str(fixed) + 'Q', b, at) if fixed else ()
    at += fixed * 8
    rows = []
    for _ in range(count):
        rows.append(struct.unpack_from('<' + str(row_words) + 'Q', b, at))
        at += row_words * 8
    tails = []
    for _ in range(blobs):
        n, = struct.unpack_from('<Q', b, at)
        at += 8
        tails.append(b[at:at+n])
        require(len(tails[-1]) == n, 'short blob')
        at += n
    require(at == len(b), ('frame exact consumption', operation, at, len(b)))
    return values, rows, tails


ix = load(BASE / 'copy-index.json')
require(inputs[str(BASE / 'copy-index.json')]['sha256'] ==
        '5f1a8c78a528864de642817b3b6d38c98295dabf3c824558cb3756b538ec8097', 'collection pin')
require((ix['count'], ix['bytes']) == (176, 51325789), 'collection size')
seen = set()
total = 0
for row in ix['files']:
    require(row['path'] not in seen, 'duplicate collection path')
    seen.add(row['path'])
    b = raw(BASE / row['path'])
    require(len(b) == row['bytes'] and digest(b) == row['sha256'], ('payload hash', row['path']))
    total += len(b)
require(len(seen) == ix['count'] and total == ix['bytes'], 'payload totals')
tar_path = BASE / '.collection/copy.tar'
raw(tar_path)
tar_names = set()
with tarfile.open(tar_path) as t:
    by_name = {r['name']: r for r in ix['files']}
    for m in t:
        require(m.isfile() and m.name not in tar_names and m.name in by_name, ('tar membership', m.name))
        tar_names.add(m.name)
        b = t.extractfile(m).read()
        row = by_name[m.name]
        require(len(b) == row['bytes'] and digest(b) == row['sha256'], ('tar bytes', m.name))
require(tar_names == set(by_name), 'tar complete membership')

j = load(P / 'result.json')
require(inputs[str(P / 'result.json')]['sha256'] ==
        '08d9660d0d81faf2481c63eedacc8d1e382318fc7084e6895e09a2df701e6bb6', 'inner result pin')
require(j['status'] == 'syscall_and_borrowed_jit_prefix_pass' and j['overall_pass'], 'reported success')
require(j['protected_mm_completion_observed'] is False and
        j['meaningful_returned_mm_body'] == 'not_established', 'full completion boundary')
require(len(j['protected_completion_final_gates']) == 9 and
        all(v is True for v in j['protected_completion_final_gates'].values()), 'nine final gates')

obs = load(P / 'observations.json')
fields = obs['fields']
require(fields == 'kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split(), 'event field layout')
records = obs['records']
previous = []
snapshots = []
for f in sorted(P.glob('events-*.bin')):
    b = raw(f)
    abi, words, capacity, count, overflow = struct.unpack_from('<5Q', b)
    require((abi, words, overflow) == (1, 20, 0) and count <= capacity, 'event header')
    require(len(b) == 40 + count * 160, 'event exact bytes')
    rows = [dict(zip(fields, x), index=n) for n, x in enumerate(struct.iter_unpack('<20Q', b[40:]))]
    require(rows[:len(previous)] == previous, 'monotonic snapshot prefix')
    previous = rows
    snapshots.append({'file': f.name, 'count': count, 'overflow': overflow})
require(records == previous and len(records) == 28743, 'JSON/raw final equality')

# Every event embedded by the host in its conclusions must equal its raw row.
embedded = 0


def check_embedded(x):
    global embedded
    if isinstance(x, dict):
        if set(fields + ['index']) == set(x):
            require(x == records[x['index']], 'embedded event differs from raw')
            embedded += 1
        else:
            for v in x.values():
                check_embedded(v)
    elif isinstance(x, list):
        for v in x:
            check_embedded(v)


check_embedded(j)
for f in sorted(P.glob('completion-round-*.json')):
    check_embedded(load(f))
check_embedded(load(P / 'protected-completion-final.json'))
for f in sorted(P.glob('roots-*.json')):
    check_embedded(load(f))

meta = load(P / 'source-metadata.json')
source_export = raw(P / 'source-export.bin')
require(source_export == raw(P / 'wire/attempt-00000002/reply.bin'), 'source wire export equality')
abi, op, size, region_count = struct.unpack_from('<4Q', source_export)
require((abi, op, size, region_count) == (1, 8, len(source_export), 4), 'source export header')
epoch, configuration, image_load, gs, boundary_count, slot, initial_image = struct.unpack_from('<7Q', source_export, 32)
require(initial_image == 0, 'cold initial image')
at = 88
regions = []
for n in range(region_count):
    start, length = struct.unpack_from('<2Q', source_export, at)
    at += 16
    b = source_export[at:at+length]
    at += length
    require(b == raw(P / ('source-' + str(n) + '.bin')), 'source region wire equality')
    require(meta['regions'][n] == {'start': start, 'length': length, 'sha256': digest(b)}, 'source metadata equality')
    regions.append((start, b))
boundaries = [struct.unpack_from('<2Q', source_export, at + n * 16) for n in range(boundary_count)]
at += boundary_count * 16
version_size, = struct.unpack_from('<Q', source_export, at)
at += 8
version = source_export[at:at+version_size]
require(at + version_size == len(source_export) and version.hex() == meta['version_hex'], 'source version exact')
require(sum(len(b) for _, b in regions) == 1558, 'source total')


def source_bytes(ip, n):
    return one([b[ip-start:ip-start+n] for start, b in regions
                if start <= ip and ip+n <= start+len(b)], 'source byte membership')


for c in meta['calls']:
    b = source_bytes(c['site'], c['length'])
    require(b.hex() == c['raw_hex'] and b[0] == 0xe8 and len(b) == 5 and not c['indirect'], 'raw direct CALL')
    require(c['site'] + 5 + struct.unpack_from('<i', b, 1)[0] == c['target'], 'direct CALL target arithmetic')

manifest = load(P / 'cycle-0001/manifest.json')
for s in manifest['source_sites']:
    require(source_bytes(int(s['ip'], 16), s['length']).hex() == s['bytes_hex'], 'manifest source bytes')
assembly = raw(P / 'cycle-0001/image.S')
require(assembly == raw(P / 'cycle-0001/build/image.S'), 'generated assembly staging equality')
require(raw(P / 'cycle-0001/machine-code.bin') == raw(P / 'cycle-0001/build/image.bin'), 'machine code equality')
for n in range(4):
    g = load(P / ('cycle-0001/gnu-%02d.json' % n))
    require(g['returncode'] == 0 and g['diagnostic_sha256'] == digest(raw(P / ('cycle-0001/gnu-%02d.log' % n))), 'GNU result/diagnostic equality')

wire = []
for d in sorted((P / 'wire').iterdir()):
    rq = raw(d / 'request.bin')
    reply = raw(d / 'reply.bin')
    rm = load(d / 'request.json')
    returned = load(d / 'result.json')
    envelope = struct.unpack('<9Q', raw(d / 'returned-envelope.bin'))
    require(envelope[:3] == (1, rm['operation'], rm['sequence']) and
            envelope[4] == len(rq) == rm['request_bytes'] and
            envelope[6] == rm['output_capacity'] and envelope[7] == len(reply) and
            envelope[8] == returned['status'] == 0 and returned['completed_response'] is True and
            returned['reply_bytes'] == len(reply) and returned['sequence'] == rm['sequence'], 'wire envelope identity/actual success')
    wire.append({'attempt': d.name, 'operation': rm['operation'], 'sequence': rm['sequence'],
                 'request_bytes': len(rq), 'reply_bytes': len(reply)})
require([x['operation'] for x in wire] == [0, 8, 1, 2, 3, 4, 5, 6, 1, 6, 9, 10, 11, 6], 'exact wire operations')
require(len({x['sequence'] for x in wire}) == 14 and j['wire']['attempts'] == 14, 'wire unique sequence')
build, _, bt = frame(raw(P / 'wire/attempt-00000004/reply.bin'), 2, 12, 0, 4)
candidate, build_slot, image, build_inputs, producer, update, owner, old, emission, build_epoch, code_base, code_capacity = build
require(build_slot == slot and build_epoch == epoch and old == 0 and code_capacity and len(bt) == 4, 'build epoch/image/producer binding')
pub, pubrows, pubtail = frame(raw(P / 'wire/attempt-00000006/reply.bin'), 4, 14, 2, 0)
require(not pubrows and not pubtail and (pub[3], pub[4], pub[5], pub[6], pub[7], pub[9], pub[10], pub[11], pub[12], pub[13]) ==
        (slot, update, owner, old, image, epoch, emission, build_inputs, producer, candidate), 'actual publication complete candidate/image/source binding')
ack, ackrows, _ = frame(raw(P / 'wire/attempt-00000007/reply.bin'), 5, 5, 2, 0)
require(not ackrows and sum(c['acknowledged'] for c in j['cycles']) == 0, 'zero exact coverage ACK rows')
require(len(j['cycles']) == 2 and sum(c['published'] for c in j['cycles']) == 1 and
        all(c['image'] == image for c in j['cycles']), 'two cycles one immutable image publication')

specs = {
    0xffffffff817ef5ea: ('mmap', 0xffffffff817ef5e5, 0xffffffff817ef4d3, 0xffffffff818321c0, 0xffffffff817ef48d, 144),
    0xffffffff8185b00e: ('munmap', 0xffffffff8185b009, 0xffffffff8185af54, 0xffffffff81858430, 0xffffffff8185af13, 103),
}
require(set(j['entry_sites']) == set(specs), 'both admitted roots')
emitted = set(int(x, 16) for x in manifest['emitted_sites'])
for root, (name, lock_call, source_call, target, seq_add, count) in specs.items():
    require(root == lock_call + 5, 'root is real lock CALL return address')
    lock = one([c for c in meta['calls'] if c['site'] == lock_call and c.get('operation') == 'lock'], 'typed root source CALL')
    require(lock['target'] == 0xffffffff8152f710, 'same killable wrapper target')
    require(source_bytes(seq_add, 7).hex() == '8380d801000001' and seq_add in emitted, 'nonempty sequence store admitted')
    block = assembly.decode().split('.Lkd_src_%x:\n' % source_call, 1)[1].split('\n.Lkd_runtime_', 1)[0]
    require(('0x%X' % (source_call+5)) in block and
            'LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]' in block and
            'MOV             QWORD PTR [R13], R15' in block and
            ('0x%x' % target) in block, 'generated CALL exactly stages real source return word')
    require(not any(start <= target < start+len(b) for start, b in regions), 'callee omitted from admitted text')

by_acquisition = defaultdict(list)
by_owner = defaultdict(list)
for e in records:
    by_acquisition[(e['state'], e['acquisition'])].append(e)
    if e['owner']:
        by_owner[e['owner']].append(e)
counts = Counter()
witnesses = []
all_fact_exits = Counter()
for item in j['borrowed_jit_evidence']:
    enter = item['enter']
    root = enter['cursor']
    name, lock_call, source_call, target, seq_add, expected_count = specs[root]
    rows = by_acquisition[(enter['state'], enter['acquisition'])]
    of_kind = lambda k: one([e for e in rows if e['kind'] == k], ('episode unique kind', enter['index'], k))
    selected = {k: of_kind(k) for k in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 15, 16, 20, 22, 23, 24, 28, 29, 30)}
    r, free, grant, exit, forward = [selected[k] for k in (1, 2, 6, 24, 28)]
    require(selected[23] == enter and item['reserve'] == r and item['grant'] == grant and
            item['first_exit'] == exit and item['final_free'] == [free], 'embedded episode exact join')
    require(grant['owner_task'] == grant['task'] == enter['task'] != enter['origin'] == grant['origin'] and
            r['task'] == r['origin'] == enter['origin'], 'foreign physical executor and logical origin')
    require(r['state'] == free['state'] and r['node'] == free['node'] and r['acquisition'] == free['acquisition'] and
            all(r[k] == free[k] for k in ('related', 'owner', 'parent')), 'exact slot lifetime identity')
    require(selected[22]['parent'] == 0 and selected[22]['image'] == enter['image'] == exit['image'] == image and
            selected[22]['origin'] == enter['origin'], 'root frame exact image/origin')
    require((exit['result'], exit['phase'], exit['flags'], exit['ip'], exit['cursor'], exit['related']) ==
            (3, 2, 1, source_call, target, target), 'CALL_STAGED exact first exit')
    require(all(forward[k] == exit[k] for k in ('task', 'state', 'origin', 'node', 'acquisition', 'image', 'ip', 'cursor', 'related', 'phase')) and
            forward['flags'] == 3, 'FORWARD target/canonical state exact join')
    require(not item['typed_unlocks'] and not item['episode_completions'] and
            item['source_progress_to_another_ip'] is True and
            item['meaningful_mm_body_completion'] == 'not_established', 'prefix/full-body distinction')
    owner_rows = [e for e in by_owner[grant['owner']] if grant['index'] <= e['index'] < free['index']]
    pb = one([e for e in owner_rows if e['kind'] == 18], 'physical begin')
    pe = one([e for e in owner_rows if e['kind'] == 19], 'physical end')
    owner_retire = one([e for e in owner_rows if e['kind'] == 21], 'owner retire')
    require(all(e['object'] == grant['object'] and e['owner_task'] == enter['task'] and e['task'] == enter['task'] for e in (pb, pe)), 'physical callback executor/object')
    require(pb['related'] == pe['related'] and (pb['phase'], pe['phase']) == (1, 2), 'exact physical callback pair')
    release = selected[10]
    require(all(e['related'] == release['related'] and e['owner'] == grant['owner'] and
                e['owner_task'] == grant['owner_task'] for e in [selected[k] for k in (11, 15, 16, 20)]), 'exact release object lifecycle')
    require(release['source_user'] and all(selected[k]['source_user'] == release['source_user'] for k in (11, 15, 16)) and
            selected[20]['source_user'] == 0, 'source-use drop before release retirement')
    require(selected[11]['task'] == selected[16]['task'] == selected[29]['task'] == enter['origin'], 'original-task native continuation and source release')
    require(r['index'] < selected[22]['index'] < selected[3]['index'] < selected[5]['index'] <
            release['index'] < grant['index'] < enter['index'] < exit['index'] < forward['index'] <
            selected[30]['index'] < selected[7]['index'] < selected[11]['index'] < selected[15]['index'] <
            pb['index'] < selected[8]['index'] < pe['index'] < selected[29]['index'] < selected[16]['index'] <
            selected[20]['index'] < owner_retire['index'] < selected[9]['index'] < free['index'], 'complete observed lifecycle partial order')
    counts[name] += 1
    all_fact_exits[(3, 1, source_call, target, target, 2)] += 1
    witnesses.append({'root': name, 'state': enter['state'], 'node': enter['node'],
                      'acquisition': enter['acquisition'], 'origin': enter['origin'], 'executor': enter['task'],
                      'image': image, 'physical_owner': grant['owner'], 'release': release['related'],
                      'source_user': release['source_user'], 'slot_free_task': free['task'],
                      'events': {obsname: selected[k]['index'] for obsname, k in obs['kinds'].items() if k in selected},
                      'physical_begin': pb['index'], 'physical_end': pe['index'], 'owner_retire': owner_retire['index']})
require(counts == Counter({s[0]: s[5] for s in specs.values()}) and len(witnesses) == 247, 'both-root episode counts')
require(Counter(e['kind'] for e in records)[23] == len(witnesses), 'no unjoined generated entry')

archive_bytes = raw(P / 'shutdown-archive.json')
archive = json.loads(archive_bytes)
require(digest(archive_bytes) == j['archive_sha256'] and archive['learning_closed'] is True, 'durable archive exact digest')
ef = archive['epoch']['fields']
require((token(ef['identity']), token(ef['configuration_identity']), token(ef['load_identity']), ef['current_task_gs_offset']) ==
        (epoch, configuration, image_load, gs) and bytes.fromhex(ef['version']['bytes_hex']) == version, 'archive epoch exact exported source binding')
producer_row = one(archive['producers'], 'one archived producer')
require(token(producer_row['producer_identity']) == producer and token(producer_row['image_identity']) == image and
        producer_row['epoch'] == archive['epoch'], 'archived exact producing image')
require(producer_row['construction']['fields']['assembly'].encode() == assembly, 'archived producing construction exact assembly')
keys = [fact_key(k) for k in archive['claim']['keys']]
require(len(keys) == len(set(keys)) == 247 and all(k[0] == epoch for k in keys), '247 distinct exact fact incarnations')
fact_keys = []
archived_exits = Counter()
for f in archive['facts']:
    key = fact_key(f['key'])
    fact_keys.append(key)
    ff = f['fact']
    require((token(ff['record_identity']), ff['incarnation']) == key[1:] and ff['epoch'] == archive['epoch'] and
            token(ff['image_identity']) == image and token(ff['producer_identity']) == producer, 'fact exact producing epoch/image/key')
    require(not f['acknowledgment_identities'] and not f['publication_identities'] and
            not f['emitted_candidate_identities'] and not f['input_candidate_identities'] and
            f['merge']['name'] in ('NON_OBSERVATION', 'CLOSED_EPOCH_LATE'), 'no fact coverage or ordinary observation credit')
    ex = ff['exit']['fields']
    archived_exits[tuple(ex[k] for k in ('kind', 'detail', 'source_ip', 'target', 'cursor', 'phase'))] += 1
require(keys == fact_keys and archived_exits == all_fact_exits, 'archive exact key order and exit multiplicities')
claim_raw = raw(P / 'wire/attempt-00000012/reply.bin')
require(bytes.fromhex(archive['raw_claim']['bytes_hex']) == claim_raw, 'archive raw claim exact wire reply')
claim_values, claim_rows, claim_tail = frame(claim_raw, 10, 3, 12, 1)
claim_id, holder, claim_epoch = claim_values
require((claim_id, holder) == (token(archive['claim']['identity']), token(archive['claim']['holder'])) and
        claim_epoch == epoch and claim_tail == [version], 'archive claim identity')
require([(epoch, r[0], r[1]) for r in claim_rows] == keys, 'all exact archive wire keys')
require(Counter(tuple(r[k] for k in (4, 5, 6, 7, 8, 9)) for r in claim_rows) == all_fact_exits and
        all(r[2:4] == (producer, image) and r[10:12] == (0, 0) for r in claim_rows), 'wire fact producer and exact exits')
settle_values, settle_rows, settle_tail = frame(raw(P / 'wire/attempt-00000013/request.bin'), 11, 2, 2, 1)
require(settle_values == (claim_id, holder) and settle_rows == [k[1:] for k in keys] and
        settle_tail == [bytes.fromhex(digest(archive_bytes))], 'actual SETTLE request all exact keys and archived digest')
settled_values, settled_rows, _ = frame(raw(P / 'wire/attempt-00000013/reply.bin'), 11, 3, 2, 0)
require(settled_values[1:] == (claim_id, holder) and settled_rows == settle_rows and j['settled_keys'] == 247, 'actual successful SETTLE receipt keys')
require(not any(f['acknowledged'] for f in j['facts']) and len(j['facts']) == 247, 'zero result fact ACK')

stdout_records = [json.loads(line) for line in raw(P / 'client.stdout').decode().splitlines()]
require(stdout_records == [load(P / ('phase-%04d.json' % n)) for n in range(6)], 'actual client stdout exact phase records')
require(j['rounds'] == stdout_records[1:4] and j['client_final'] == stdout_records[-1], 'final result actual client join')
worker_totals = Counter()
rounds = []
for number, r in enumerate(j['rounds'], 1):
    w = r['workload']
    require(r['round'] == r['completed_rounds'] == number and r['phase'] == 'jit_round_complete' and
            w['status'] == 'syscall_completion_pass' and w['overall_pass'] is True and
            w['threads'] == w['created_threads'] == 8 and w['iterations_per_thread'] == 8 and
            w['completed_iterations'] == 64 and w['mapping_pages'] == 2 and w['worker_errors'] == 0 and
            not w['deadline_exceeded'] and w['setup_errno'] == w['arena_cleanup_errno'] == 0 and
            w['arena_reservations'] == 1 and w['arena_bytes'] == 8 * 4 * w['page_bytes'], 'actual bounded workload round')
    require(len(w['workers']) == 8 and len({a['tid'] for a in w['workers']}) == 8, 'eight distinct actual workers')
    for a in w['workers']:
        require(a['completed'] == 8 and a['errno'] == 0 and a['error'] == 'none' and not a['deadline_reached'], 'worker completion')
        expected = {'mmap_attempts': 24, 'mmap_successes': 24, 'munmap_attempts': 16,
                    'munmap_successes': 16, 'mincore_attempts': 32, 'unmapped_page_checks': 32,
                    'reuse_successes': 8, 'fresh_zero_bytes': 32*w['page_bytes'],
                    'written_bytes': 32*w['page_bytes'], 'readback_bytes': 32*w['page_bytes']}
        require(all(a[k] == v for k, v in expected.items()), 'per-worker actual syscall/effect counters')
        require(a['slot_address'] == w['arena_address'] + (4*a['id']+1)*w['page_bytes'], 'distinct arena slot and guard geometry')
        worker_totals.update({k: a[k] for k in expected})
        worker_totals['completed_iterations'] += a['completed']
    native = r['profile']['native']
    require(native['physical_begins'] == native['physical_ends'] and native['pool_idle'] == 1 and
            native['gate_locked'] == native['gate_write_locked'] == native['gate_contended'] == 0 and
            native['owner_threads'] == 1 and r['profile']['event_overflow'] == 0, 'per-round gate and actor drain')
    rounds.append({'round': number, 'iterations': w['completed_iterations'], 'elapsed_ns': w['elapsed_ns'],
                   'actual_worker_tids': [a['tid'] for a in w['workers']], 'arena': w['arena_address'],
                   'mmap': sum(a['mmap_successes'] for a in w['workers']),
                   'munmap': sum(a['munmap_successes'] for a in w['workers'])})
require(worker_totals['completed_iterations'] == 192 and worker_totals['mmap_successes'] == 576 and
        worker_totals['munmap_successes'] == 384 and worker_totals['reuse_successes'] == 192 and
        worker_totals['unmapped_page_checks'] == 768, 'whole-run explicit worker counters')
final = j['client_final']
n = final['profile']['native']
require(j['client_returncode'] == 0 and final['overall_pass'] is True and final['all_rounds_pass'] is True and
        final['leave_attempts'] == final['end_attempts'] == 1 and final['leave_errno'] == final['end_errno'] == 0 and
        final['profile']['state'] == 5 and final['profile']['owner_left'] == 1 and final['profile']['roles'] == 0 and
        final['profile']['source_identity'] == final['profile']['storage_identity'] == final['profile']['runtime_identity'] == 0 and
        n['physical_begins'] == n['physical_ends'] == 994 and n['queue_enqueues'] == 1241 and n['local_selections'] == 747 and
        n['pool_idle'] == 1 and n['gate_locked'] == n['gate_write_locked'] == n['gate_contended'] == 0 and
        n['native_read_acquires'] == n['native_read_releases'] == 410, 'final actual native gate/source/storage retirement')
require(j['boot_id'] == j['post_boot_id'] == '2ae5991e-d024-48ac-9f86-24a0a8910172' and
        j['release'] == '7.0.0-38-kdrebuild8' and j['post_taint'] == 4096, 'actual run identity')
require(raw(P / 'config.json') == raw(BASE / 'payload/input/host-config.json') and
        digest(raw(P / 'config.json')) == j['config_sha256'] == 'c38376355e1b34c5a7dd7c645c8666b8737c201aefe12c31b6d69ba38ba3ec54', 'exact activated input config')

report = {
    'status': 'SAVED_MM_PREFIX_RAW_AUDIT_COMPLETE',
    'scope': 'Read-only standard-library audit of already collected actual syscall run; no new execution or runtime instrumentation.',
    'collection': {'files': len(seen), 'payload_bytes': total, 'complete_tar_members': len(tar_names)},
    'observation_count': len(records), 'snapshots': snapshots, 'embedded_event_dicts_checked': embedded,
    'event_counts': {name: sum(e['kind'] == k for e in records) for name, k in obs['kinds'].items()},
    'epoch': epoch, 'configuration': configuration, 'load': image_load, 'gs': gs,
    'source_version_hex': version.hex(), 'source_bytes': 1558, 'source_regions': len(regions),
    'image': image, 'producer': producer, 'entry_counts': dict(counts),
    'roots': [{'root': name, 'root_continuation': hex(root), 'typed_lock_callsite': hex(lock_call),
               'source_callsite': hex(source_call), 'source_call_raw_hex': source_bytes(source_call, 5).hex(),
               'staged_real_return_address': hex(source_call+5), 'unexecuted_native_callee_entry': hex(target),
               'exit_kind': 3, 'exit_detail': 1, 'exit_phase': 'CALL_STAGED (2)',
               'canonical_cursor_equals_target': True, 'forward_cursor_equals_target': True,
               'mm_sequence_add_site': hex(seq_add), 'episodes': count}
              for root, (name, lock_call, source_call, target, seq_add, count) in specs.items()],
    'source_progress': {'nonempty_borrowed_prefix_for_both_roots': True,
                        'basis': 'Exact raw JIT_ENTER/root and CALL_STAGED exits at later source CALLsites, linked to original exported bytes and generated producing assembly. The successful path includes the admitted sequence increment and argument preparation. CALL has already staged its real return word; native resumes at omitted callee entry without replay.',
                        'per_instruction_runtime_count_measured': False,
                        'meaningful_returned_mm_body': 'not_established', 'protected_mm_completion_observed': False,
                        'typed_generated_unlocks': 0, 'generated_episode_completions': 0},
    'episode_witnesses': witnesses,
    'feedback': {'archive_sha256': digest(archive_bytes), 'keys': keys, 'distinct_exact_keys': len(keys),
                 'exit_multiplicities': [{'kind': k[0], 'detail': k[1], 'source_ip': k[2], 'target': k[3], 'cursor': k[4], 'phase': k[5], 'count': v} for k, v in archived_exits.items()],
                 'archive_claim': claim_id, 'holder': holder, 'settlement': settled_values[0],
                 'archive_equals_actual_claim': True, 'actual_settle_request_digest_equals_archive': True,
                 'actual_settle_request_and_reply_equal_all_247_exact_keys': True,
                 'coverage_ack_rows': 0, 'merge_dispositions': dict(Counter(f['merge']['name'] for f in archive['facts'])),
                 'ordinary_compiler_observation_credit': False},
    'wire': wire, 'cycles': len(j['cycles']), 'publications': 1,
    'rounds': rounds, 'explicit_worker_totals': dict(worker_totals),
    'counter_scope': 'Explicit worker counters only; three parent arena reservations and releases, pthread/libc activity and kernel lock episodes are separate.',
    'final_native': n, 'nine_final_gates': j['protected_completion_final_gates'],
    'assumptions': {'native_helper_inclusive_16KiB': 'Previously accepted experimental premise, not established by this saved-record audit.',
                    'full_auxiliary_context_proof': False, 'all_kernel_stack_bound_measured': False,
                    'whole_kernel_integration_or_performance_claim': False},
    'inputs': inputs,
    'script': {'path': str(SELF), 'bytes': SELF.stat().st_size, 'sha256': digest(SELF.read_bytes())},
}
OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'path': str(OUT), 'bytes': OUT.stat().st_size, 'sha256': digest(OUT.read_bytes()),
                  'status': report['status'], 'entries': dict(counts), 'keys': len(keys),
                  'raw_events': len(records), 'embedded_event_dicts': embedded,
                  'script_sha256': report['script']['sha256']}, sort_keys=True))
