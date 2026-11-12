"""Read-only joins over the completed exact MM collection and final postread."""
from pathlib import Path
import collections
import hashlib
import json
import re
import struct

CONTROL = Path('/tmp/kdlock-kernel8-mm-prefix-run-20261111-01')
SAVED = Path('/tmp/kdlock-kernel8-mm-prefix-collection-20261111-01/payload/runtime')
result = json.loads((SAVED/'result.json').read_text())
metadata = json.loads((SAVED/'source-metadata.json').read_text())
records = json.loads((SAVED/'observations.json').read_text())['records']
postraw = (CONTROL/'postread.json').read_bytes()
post = json.loads(postraw)
forward = [row for row in records if row['kind'] == 28]
roots = {
    0xffffffff817ef5ea: {'function': 'vm_mmap_pgoff', 'source_start': 0xffffffff817ef350,
                       'call': 0xffffffff817ef4d3, 'target': 0xffffffff818321c0,
                       'target_function': 'do_mmap'},
    0xffffffff8185b00e: {'function': '__vm_munmap', 'source_start': 0xffffffff8185ae30,
                       'call': 0xffffffff8185af54, 'target': 0xffffffff81858430,
                       'target_function': 'do_vmi_munmap'},
}
counts = collections.Counter()
examples = {}
for proof in result['borrowed_jit_evidence']:
    enter, exit_row = proof['enter'], proof['first_exit']
    root = roots[enter['cursor']]
    stop = min(row['index'] for row in proof['final_free'])
    matches = [row for row in forward if exit_row['index'] < row['index'] < stop
               and all(row[key] == enter[key] for key in ('state', 'origin', 'node', 'acquisition'))]
    assert len(matches) == 1
    handback = matches[0]
    assert enter['task'] != enter['origin'] and proof['grant']['owner_task'] == enter['task']
    assert proof['source_progress_to_another_ip'] is True and exit_row['ip'] != enter['cursor']
    assert (exit_row['ip'], exit_row['related'], exit_row['phase'], exit_row['flags'], exit_row['result']) == (
        root['call'], root['target'], 2, 1, 3)
    assert (handback['ip'], handback['cursor'], handback['related'], handback['phase'], handback['flags']) == (
        root['call'], root['target'], root['target'], 2, 3)
    call = next(row for row in metadata['calls'] if row['site'] == root['call'])
    raw = bytes.fromhex(call['raw_hex'])
    assert len(raw) == 5 and raw[0] == 0xe8 and call['indirect'] is False
    assert root['call']+5+struct.unpack('<i', raw[1:])[0] == call['target'] == root['target']
    counts[enter['cursor']] += 1
    examples.setdefault(enter['cursor'], {'enter': enter, 'exit': exit_row, 'forward': handback,
                                         'final_free_index': stop, 'raw_call_hex': call['raw_hex']})
assert counts == {0xffffffff817ef5ea: 144, 0xffffffff8185b00e: 103}
wire = []
for directory in sorted((SAVED/'wire').iterdir()):
    request = json.loads((directory/'request.json').read_text())
    reply = json.loads((directory/'result.json').read_text())
    envelope = struct.unpack('<9Q', (directory/'returned-envelope.bin').read_bytes())
    assert reply['completed_response'] is True and reply['status'] == 0
    assert reply['sequence'] == request['sequence'] and envelope[:3] == (1, request['operation'], request['sequence'])
    assert envelope[4] == (directory/'request.bin').stat().st_size == request['request_bytes']
    assert envelope[6] == request['output_capacity'] and envelope[7] == reply['reply_bytes']
    assert envelope[7] == (directory/'reply.bin').stat().st_size and envelope[8] == 0
    wire.append({'attempt': directory.name, 'operation': request['operation'],
                 'sequence': request['sequence'], 'status': reply['status']})
assert len(wire) == result['wire']['attempts'] == 14
assert [row['sequence'] for row in wire] == list(range(14))
assert result['observation_count'] == len(records) == 28743
assert result['client_final']['profile']['event_overflow'] == 0
assert result['settled_keys'] == len(result['facts']) == 247
assert all(row['acknowledged'] is False for row in result['facts'])
archive = (SAVED/'shutdown-archive.json').read_bytes()
assert hashlib.sha256(archive).hexdigest() == result['archive_sha256']
workers = [worker for round_row in result['rounds'] for worker in round_row['workload']['workers']]
effects = {name: sum(row[name] for row in workers) for name in (
    'completed', 'mmap_successes', 'munmap_successes', 'unmapped_page_checks',
    'reuse_successes', 'fresh_zero_bytes', 'written_bytes', 'readback_bytes')}
assert len(workers) == 24 and effects['completed'] == 192
assert effects['mmap_successes'] == 576 and effects['munmap_successes'] == 384
before = (SAVED/'command-0001/stdout.log').read_bytes()
after = (SAVED/'command-0004/stdout.log').read_bytes()
assert after.startswith(before)
delta = after[len(before):]
assert len(delta) == 82 and hashlib.sha256(delta).hexdigest() == 'f4a8e80246dde1b460c89d1f2498f428aa92c6ec2df836d8ff9bbccdc266dec0'
current = post['kernel_log']['text'].encode()
assert hashlib.sha256(current).hexdigest() == post['kernel_log']['sha256']


def normalized(data):
    # dmesg under C locale escapes the UTF8 bytes of a pre-existing boot emoji.
    # Both original byte streams remain preserved; normalization is only a join.
    return re.sub(rb'\\x([0-9a-fA-F]{2})', lambda match: bytes([int(match[1], 16)]), data)


assert normalized(current).startswith(normalized(after))
late = normalized(current)[len(normalized(after)):]
assert len(late.splitlines()) == 8 and all(b'comm="who"' in line for line in late.splitlines())
new = normalized(current)[len(normalized(before)):]
diagnostics = re.findall(rb'.*(?:WARNING:|BUG:|Oops:|Call Trace:|general protection fault|kernel BUG|Kernel panic).*', new, re.I)
assert not diagnostics
for name, data in [('kernel-log-run-delta.raw', delta), ('kernel-log-final.raw', current),
                   ('kernel-log-late-delta.raw', late)]:
    with (CONTROL/name).open('xb') as stream:
        stream.write(data)
summary = {
    'status': 'SAVED_MM_PREFIX_STATS_VERIFIED',
    'runner_result_sha256': hashlib.sha256((SAVED/'result.json').read_bytes()).hexdigest(),
    'postread_sha256': hashlib.sha256(postraw).hexdigest(),
    'borrowed_prefix_count': len(result['borrowed_jit_evidence']),
    'roots': [{**value, 'entry': hex(key), 'source_start': hex(value['source_start']),
               'call': hex(value['call']), 'target': hex(value['target']), 'count': counts[key],
               'exit_phase': 2, 'exit_flags': 1, 'exit_result': 3, 'forward_phase': 2,
               'forward_flags': 3, 'example': examples[key]} for key, value in roots.items()],
    'handback': 'CALL_STAGED: CALL stack effect was applied once; FORWARD resumes the first unexecuted callee target, without replaying the CALL site.',
    'source_region_count': len(metadata['regions']), 'source_bytes': sum(row['length'] for row in metadata['regions']),
    'observations': len(records), 'overflow': 0, 'compiler_cycles': len(result['cycles']),
    'publications': sum(row['published'] for row in result['cycles']),
    'coverage_ack_keys': sum(row['acknowledged'] for row in result['cycles']),
    'wire': wire, 'wire_reserved_bytes': result['wire']['reserved_bytes'],
    'settled_keys': result['settled_keys'], 'archive_sha256': result['archive_sha256'],
    'worker_rows': len(workers), 'worker_effects': effects,
    'parent_arena_reservations': sum(row['workload']['arena_reservations'] for row in result['rounds']),
    'ordinary_final_gates': result['protected_completion_final_gates'],
    'protected_mm_completion_observed': False, 'meaningful_returned_mm_body': 'not_established',
    'generated_source_instruction_count': 'not_measured',
    'experimental_native_helper_premise_bytes': 16384,
    'native_helper_callbacks_measured': False, 'complete_auxiliary_requirement_proved': False,
    'run_kernel_log_delta_bytes': len(delta), 'run_kernel_log_delta_sha256': hashlib.sha256(delta).hexdigest(),
    'late_kernel_log_lines': 8, 'late_kernel_log_scope': 'Preserved later audit messages for who, not a WARNING/BUG/Oops or stack trace.',
    'log_representation_note': 'One pre-existing boot emoji is C-escaped in runner logs and UTF8 in the final read; raw bytes are retained and only the prefix join is normalized.',
    'new_kernel_diagnostic_matches': [], 'final_idle': post['idle'],
}
with (CONTROL/'actual-stats.json').open('x') as stream:
    json.dump(summary, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps({'status': summary['status'], 'roots': dict(counts), 'observations': len(records),
                  'wire': len(wire), 'worker_effects': effects}, sort_keys=True))
