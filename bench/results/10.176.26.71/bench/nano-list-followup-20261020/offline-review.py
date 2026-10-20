#!/usr/bin/env python3
"""Review inert list timing archives on 380G10; execute no archived code."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import statistics
import struct
import sys
import tarfile
from types import SimpleNamespace


BASE = 'bench/results/10.176.26.71/bench/'
SHARED = BASE+'shared-lock-followup-20261020/offline-comparison.py'
SHARED_SHA = '9c66cc3c882da618726a5d04ee60136477ea639601b12343a8bba8eac92916b8'
STAGE = BASE+'nano-list-followup-20261020/'
READ_PREFETCH = {'prefetchnta', 'prefetcht0', 'prefetcht1', 'prefetcht2'}


def load(path, digest, name):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def elf(data):
    """Read section and symbol extents directly from an inert x86-64 object."""
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    assert header[0][:6] == b'\x7fELF\x02\x01' and header[1:3] == (1, 62)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, header[6]+i*header[11])
                for i in range(header[12])]
    get = lambda section: data[section[4]:section[4]+section[5]]
    names = get(sections[header[13]])
    string = lambda table, at: table[at:table.index(b'\0', at)].decode()
    named = {string(names, section[0]): (i, section, get(section))
             for i, section in enumerate(sections)}
    table = named['.symtab'][1]
    strings = get(sections[table[6]])
    symbols = defaultdict(list)
    for offset in range(table[4], table[4]+table[5], table[9]):
        item = struct.unpack_from('<IBBHQQ', data, offset)
        symbols[string(strings, item[0])].append(item)
    return named, symbols, sections


def inspect_listing(a, helper, name, code, receipt, prefetch):
    """Bind every retained instruction to its bytes and every hint to its record."""
    start, cursor, hints = receipt['start'], receipt['start'], []
    a.check(len(code) == receipt['bytes'] and helper.sha(code) == receipt['sha256'] ==
            a.files[name+'.bin'], 'exact_audited_body', name)
    text = a.contents[name+'.txt'].decode()
    for match in re.finditer(
            r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)([^\n]*)$', text, re.M):
        offset, raw, instruction = int(match[1], 16), bytes.fromhex(match[2]), match[3].strip()
        a.check(offset == cursor and raw == code[cursor-start:cursor-start+len(raw)] and
                instruction and '(bad)' not in instruction and '.byte' not in instruction,
                'listing_instruction_bytes', [name, offset])
        words = instruction.split(None, 1)
        mnemonic, operand = words[0], words[1] if len(words) > 1 else ''
        if mnemonic.startswith('prefetch'):
            hints.append(dict(offset=offset, mnemonic=mnemonic, operand=operand))
        cursor += len(raw)
    a.check(cursor == start+len(code) and code and hints == receipt['hints'] and
            all(h['mnemonic'] in READ_PREFETCH for h in hints) and bool(hints) == prefetch,
            'complete_listing_and_prefetch', name)


def code_audits(a, helper, raw, cold, images):
    """Load selected binary members once per archive after inventory verification."""
    needed = set()
    for path, receipt, child in cold:
        needed.add(a.normalized_binary(receipt['binary'], child))
    for prefix, publication, receipt in images:
        entry = publication['entry']
        workspace = prefix+'workspace/daemon/'+hex(entry['entry'])+'/'+str(entry['tgid'])+'/asm/'
        needed.update((workspace+'jit.o', workspace+'jit.bin', prefix+'list-image/loaded.bin'))
    blobs = {}
    for group in a.archive['groups']:
        selected = {n for n in needed if a.members[n]['archive'] == group['file']}
        if not selected:
            continue
        with tarfile.open(raw/group['file'], 'r|gz') as archive:
            for member in archive:
                name = member.name[len(a.prefix):]
                if name in selected:
                    data = archive.extractfile(member).read()
                    a.check(helper.sha(data) == a.files[name], 'binary_reread_hash', name)
                    blobs[name] = data
    a.check(set(blobs) == needed, 'all_selected_binaries_retained')
    for path, receipt, child in cold:
        binary = a.normalized_binary(receipt['binary'], child)
        sections, symbols, _ = elf(blobs[binary])
        a.check(a.files[binary] == receipt['sha256'], 'compiled_audit_binary', path)
        for function, body in receipt['functions'].items():
            a.check(len(symbols[function]) == 1, 'unique_function_symbol', [path, function])
            symbol = symbols[function][0]
            index, section, data = sections[body['section']]
            start, size = symbol[4:6]
            a.check(symbol[3] == index and symbol[1] & 15 == 2 and section[2] & 4 and
                    body['start'] == start and body['bytes'] == size and 0 < size <= len(data)-start,
                    'compiled_symbol_extent', [path, function])
            inspect_listing(a, helper, path.rsplit('/', 1)[0]+'/'+function,
                            data[start:start+size], body, receipt['prefetch'])
    for prefix, publication, receipt in images:
        entry = publication['entry']
        workspace = prefix+'workspace/daemon/'+hex(entry['entry'])+'/'+str(entry['tgid'])+'/asm/'
        upload, loaded = blobs[workspace+'jit.bin'], blobs[prefix+'list-image/loaded.bin']
        sections, symbols, all_sections = elf(blobs[workspace+'jit.o'])
        a.check(len(symbols['generated_body']) == len(symbols['comp_syscall']) == 1,
                'unique_generated_bounds', prefix)
        begin, end = symbols['generated_body'][0], symbols['comp_syscall'][0]
        index, section, text = sections['.text']
        a.check(begin[3] == end[3] == index and section[2] & 4 and text == upload == loaded and
                48 <= begin[4] < end[4] <= len(upload) and receipt['start'] == begin[4] and
                receipt['bytes'] == end[4]-begin[4], 'generated_object_extent', prefix)
        a.check(all(not (s[2] & 2 and s[5] and i != index) and
                    not (s[1] in (4, 9) and s[7] == index and s[5])
                    for i, s in enumerate(all_sections)), 'generated_sections_relocations', prefix)
        a.check(upload[9:16] == b'KDWB002' and upload[25:32] == b'KDWC002' and
                upload[41:45] == b'KDAB' and upload[45] == entry['entry_abi'] and
                upload[46] == 2 and upload[47] == entry['requirements'] and
                entry['entry_abi'] in (1, 2, 3) and
                (entry['requirements'] == 0 or
                 (entry['requirements'] == 2 and entry['entry_abi'] == 1)),
                'loaded_image_abi', prefix)
        inspect_listing(a, helper, prefix+'list-image/generated-body',
                        loaded[begin[4]:end[4]], receipt, receipt['prefetch'])


def measurement(a, arithmetic, row, name):
    m = row['measurement']
    shared = row['lock_kind'] in ('rwlock', 'rwsem')
    a.check(m['schema'] == (1 if shared else 2) and m['complete'] and m['data_ok'],
            'completed_client', name)
    cpu_ns = sum(w['cpu_ns'] for w in m['workers'])
    a.check(m['completed'] == sum(w['completed'] for w in m['workers']),
            'worker_aggregates', name)
    if shared:
        a.check(m['finished_ns'] >= max(w['finished_ns'] for w in m['workers']),
                'collector_after_worker_join', name)
    else:
        a.check(m['worker_cpu_ns'] == cpu_ns and
                m['finished_ns'] == max(w['finished_ns'] for w in m['workers']),
                'exclusive_worker_aggregates', name)
    for i, w in enumerate(m['workers']):
        a.check(w['cpu_ns'] > 0 and w['completed'] % 256 == 0,
                'whole_batches_worker_time', [name, i])
        if shared:
            writes = ((i*17) % 100+w['completed']*20)//100
            a.check(w['writes'] == writes and w['reads']+writes == w['completed'] and
                    w['read_errors'] == w['read_hits'] == 0 and
                    w['checksum'] == arithmetic.checksum(w['completed'], 4),
                    'shared_worker_effects_checksum', [name, i])
    before, after = m['before'], m['after']
    operations = m['writes'] if shared else m['completed']
    if shared:
        a.check(m['reads']+m['writes'] == m['completed'] and
                all(m[k] == sum(w[k] for w in m['workers']) for k in ('reads', 'writes')),
                'shared_aggregates', name)
        for state in (before, after):
            a.check((state['version'], state['backend'], state['workload'], state['lines'],
                     state['post_work_rounds']) ==
                    (1, {'native': 0, 'tclock': 1, 'kdlock': 2}[row['arm']],
                     5 if row['workload'] == 'list-prefetch' else 4, row['list_nodes'], 4) and
                    all(state[k] == 0 for k in ('active', 'cnts', 'gate')),
                    'shared_snapshot_identity_and_drain', name)
        a.check({k: v for k, v in before.items() if k != 'values'} ==
                {k: v for k, v in after.items() if k != 'values'}, 'unchanged_snapshot_identity', name)
        before, after = before['values'], after['values']
    else:
        a.check(m['workload'] == row['workload'] and m['threads'] == row['threads'] and
                m['cachelines'] == row['cachelines'] == 0 and m['iterations'] == 0 and
                m['measurement_mode'] == 'duration' and m['list_integrity_ok'] is True and
                m['list_nodes'] == row['list_nodes'], 'exclusive_list_identity', name)
    a.check(len(before) == len(after) == 16 and
            [last-first for first, last in zip(before, after)] == [operations]+[0]*15 and
            before[1:] == after[1:] == [0]*15, 'protected_list_effects', name)
    extra = {'writes', 'reads', 'worker_writes', 'read_ops_s', 'write_ops_s'}
    plain = dict(m, peak={k: v for k, v in m['peak'].items() if k not in extra})
    whole = m['completed']*1e9/m['wall_ns']
    _, peak = a.peak(dict(row, measurement=plain, whole_throughput_ops_s=whole), name)
    if shared:
        first = m['samples'][peak['start_sample_index']]['completed']
        last = m['samples'][peak['end_sample_index']]['completed']
        writes = [((i*17) % 100+end*20)//100-((i*17) % 100+start*20)//100
                  for i, (start, end) in enumerate(zip(first, last))]
        peak.update(writes=sum(writes), reads=peak['completed']-sum(writes), worker_writes=writes)
        peak.update(read_ops_s=peak['reads']*1e9/peak['elapsed_ns'],
                    write_ops_s=peak['writes']*1e9/peak['elapsed_ns'])
    a.equal('complete_peak_receipt', m['peak'], peak, name)
    return whole, peak['throughput_ops_s'], cpu_ns/m['completed']


def compare(groups, prefetch=False):
    keys = sorted({(g['family'], g['nodes'], g['threads'],
                    g['arm'] if prefetch else g['workload']) for g in groups})
    rows = []
    for family, nodes, threads, variant in keys:
        controls = ('list',) if prefetch else (('native',) if family == 'rwsem' else ('native', 'tclock'))
        for control in controls:
            selector = lambda g: (g['family'], g['nodes'], g['threads']) == (family, nodes, threads)
            left = [g for g in groups if selector(g) and
                    (g['arm'] == variant and g['workload'] == 'list-prefetch' if prefetch else
                     g['arm'] == 'kdlock' and g['workload'] == variant)]
            right = [g for g in groups if selector(g) and
                     (g['arm'] == variant and g['workload'] == 'list' if prefetch else
                      g['arm'] == control and g['workload'] == variant)]
            row = dict(family=family, nodes=nodes, threads=threads, variant=variant,
                       comparator=control, status='INCOMPLETE', reason='', left=left, right=right)
            valid = len(left) == len(right) == 1 and all(g['repeats'] == [0, 1, 2] for g in left+right)
            if not valid:
                row['reason'] = 'SPLIT_CLASS_OR_MISSING_REPETITION'
            elif prefetch and left[0]['execution_class'] != right[0]['execution_class']:
                row['reason'] = 'DIFFERENT_EXECUTION_CLASSES'
            elif any(g['execution_class'] not in ('NATIVE', 'NO_JIT', 'RETURNED_JIT') for g in left+right):
                row['reason'] = 'PARTIAL_OR_UNMEASURED_JIT'
            else:
                one, two = left[0], right[0]
                row.update(whole_ratio=one['whole_median_ops_s']/two['whole_median_ops_s'],
                           peak_ratio=one['peak_max_ops_s']/two['peak_max_ops_s'],
                           separated_loss_5pct=one['whole_max_ops_s'] < .95*two['whole_min_ops_s'])
                row['status'] = 'PASS' if min(row['whole_ratio'], row['peak_ratio']) >= 1 else 'FAIL'
            rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'raw', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    assert socket.gethostname() == '380G10' and not args.report.exists()
    sys.dont_write_bytecode = True
    shared = load(args.repo/SHARED, SHARED_SHA, 'inert_shared_environment')
    helper, arithmetic = shared.load(args.repo, 'archive'), shared.load(args.repo, 'arithmetic')
    a = helper.Audit(SimpleNamespace(**vars(args)))
    archive_groups, links = a.load_archives()
    sources, binaries = a.manifests()
    tasks, plan, manifest, health = (a.jread(n+'.json') for n in
                                   ('tasks', 'task-plan', 'committed-source', 'health'))
    a.check(tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle'] and
            tasks['phase'] == 'timing' and len(tasks['tasks']) == 10, 'completed_supervisor')
    a.check(tasks['source_commit'] == plan['source_commit'] == manifest['commit'] ==
            health['source_commit'] == shared.SOURCE and len(manifest['files']) == 497,
            'source_identity')
    for path, digest in manifest['files'].items():
        for revision in (shared.SOURCE, shared.RESTORED):
            a.check(helper.sha(a.git_bytes(revision, path)) == digest, 'validated_git_source', [revision, path])
    a.check(a.files['run-tasks.py'] == tasks['script_sha256'] == plan['supervisor_sha256'] ==
            helper.sha(a.git_bytes(shared.SOURCE, plan['supervisor'])), 'supervisor_binding')
    a.check(a.files['committed-source.json'] == plan['source_manifest_sha256'], 'manifest_binding')
    a.check(a.files['preflight/historical-plan.json'] == plan['historical_plan_sha256'] and
            plan['phases']['timing'] == a.jread('preflight/historical-plan.json')['phases']['timing'],
            'unchanged_historical_arguments')
    pf = a.jread('preflight/result.json')
    a.check(pf['passed'] and pf['idle'] and pf['source_unchanged'] and pf['planned_sessions'] == 264 and
            pf['script_sha256'] == a.files['preflight/preflight.py'] and
            pf['planned_output']+'/' == a.guest_base and pf['source_commit'] == shared.SOURCE,
            'exact_preflight')
    a.check(a.jread('preflight/task-plan.json') == plan and
            a.jread('preflight/committed-source.json') == manifest and
            a.jread('preflight/host-state.json') == a.jread('host-before.json'), 'preflight_inputs')
    a.check(health['verifier_sha256'] == a.files['verify.py'] ==
            helper.hashfile(args.repo/STAGE/'verify.py'), 'verifier_binding')
    cold, images, retired, loaded, faults, sessions = [], [], [], [], [], []
    totals, classes, family_counts = Counter(), Counter(), Counter()
    source_checks = len(manifest['files'])
    a.windows = []
    for task, selected in zip(tasks['tasks'], plan['phases']['timing']):
        name, root = task['name'], task['name']+'/'
        a.check(name == selected['name'] and task['state'] == 'FINISHED' and task['exit_code'] == 0 and
                task['completed_sessions'] == selected['expected_sessions'], 'completed_child', name)
        original = root+'source/'
        source = a.jread(root+'source-sha256.json')
        overlay = 'bench/spin_cacheline/.build/provider/'
        extra = {path: digest for path, digest in source.items() if path not in manifest['files']}
        provider = original+overlay if extra else root+'build/provider/'
        prepared = a.jread(provider+'manifest.json')
        if extra:
            expected = {overlay+path: digest for path, digest in prepared['prepared'].items()}
            expected[overlay+'manifest.json'] = a.files[provider+'manifest.json']
            a.check(extra == expected and len(extra) == task['reconstructed_provider_files'],
                    'exact_generated_snapshot_set', name)
        a.check(len(source)-len(extra) == task['committed_source_files'] and prepared['complete'],
                'snapshot_source_count', name)
        source_checks += len(source)+len(prepared['prepared'])
        for path, digest in source.items():
            if path not in extra:
                a.check(manifest['files'].get(path) == digest, 'snapshot_git_binding', name+'/'+path)
        changes = a.reconstruct(original, a.contents[original+'bench/spin_cacheline/provider/observation.patch'])
        for path, digest in prepared['prepared'].items():
            data = (a.contents[original+'bench/spin_cacheline/provider/'+Path(path).name]
                    if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c') else
                    changes.get(path, a.contents.get(original+path)))
            a.check(data is not None and helper.sha(data) == digest == a.files[provider+path],
                    'prepared_reconstruction', name+'/'+path)
        a.check(set(changes) <= set(prepared['prepared']), 'all_patch_targets_retained', name)
        for category, prefix in (('production', original), ('observation', original+'bench/spin_cacheline/provider/')):
            for path, digest in prepared[category].items():
                a.check(a.files[prefix+path] == digest, 'prepared_'+category, name+'/'+path)
        for path in a.files:
            if path.startswith(root+'list-audit-') and path.endswith('/audit.json'):
                cold.append((path, a.jread(path), name))
        records, specs, dry = a.jread(root+'records.json'), a.jread(root+'plan.json'), a.jread('preflight/'+name+'.plan.json')
        a.check(len(records) == len(specs) == len(dry) == selected['expected_sessions'], 'child_exact_plan', name)
        for row, spec, dry_spec in zip(records, specs, dry):
            tag, prefix = name+'/'+row['name'], root+row['name']+'/'
            a.check(all(spec.get(k) == v for k, v in dry_spec.items()) and
                    all(row.get(k) == v for k, v in spec.items()), 'frozen_plan_binding', tag)
            saved = a.jread(prefix+'session.json')
            a.check(all(row.get(k) == v for k, v in saved.items()), 'session_binding', tag)
            raw = a.jread(prefix+'measure.json')
            m = row['measurement']
            a.check({k: v for k, v in m.items() if k != 'peak'} ==
                    {k: v for k, v in raw.items() if k != 'peak'}, 'raw_client_binding', tag)
            a.check(row['execution_status'] == 'OK' and row['drained'] and not row.get('cleanup_error') and
                    not any(row.get(k) for k in ('functional', 'diagnostic', 'pmu', 'perf_record')) and
                    row.get('score_eligible') is not False, 'valid_unprofiled_session', tag)
            a.check(row['workload'] in ('list', 'list-prefetch') and row['list_nodes'] in (16, 128) and
                    row['threads'] in (8, 60) and row['cpus'] == list(range(row['threads'])) and
                    (row['collector_cpu'], row['duration_ms'], row['peak_window_ms'],
                     row['peak_settle_ms'], row['sample_ms'], row['warmup_iterations_per_worker']) ==
                    (63, 2000, 300, 300, 10, 48000), 'retained_geometry', tag)
            is_shared = row['lock_kind'] in ('rwlock', 'rwsem')
            if is_shared:
                a.check(row['write_percent'] == 20 and row['post_work_rounds'] == 4, 'shared_mix_postwork', tag)
            whole, peak, cpu = measurement(a, arithmetic, row, tag)
            entries = row['jit_bodies']
            native_delegated = None
            if row['arm'] == 'tclock' and not is_shared:
                a.check('jit_completions' not in row and row['jit_status'] == 'NOT_APPLICABLE',
                        'exclusive_tclock_no_kd_counter', tag)
                completions = 0
                a.check(all(row[k]['quiescent'] == 1 for k in
                            ('tclock_before', 'tclock_after', 'tclock_drained')),
                        'tclock_native_quiescence', tag)
                if row['lock_kind'] == 'mutex':
                    native_delegated = row['tclock_after']['delegated']-row['tclock_before']['delegated']
                    a.check(0 < native_delegated <= m['completed'] and
                            native_delegated == row['delegated_bodies'] and row['delegation_status'] == 'PASS',
                            'tclock_native_delegation', tag)
                else:
                    a.check(row['delegated_bodies'] is None and row['delegation_status'] == 'UNMEASURED',
                            'tclock_spin_delegation_unmeasured', tag)
            else:
                completions = row['jit_completions']
                if row['arm'] == 'tclock':
                    a.check(is_shared and row['tclock_delegation_status'] == 'UNMEASURED' and
                            all(row[k]['quiescent'] == 1 for k in
                                ('tclock_before', 'tclock_after', 'tclock_drained')),
                            'tclock_shared_quiescence_and_scope', tag)
            operations = m['writes'] if is_shared else m['completed']
            a.check(0 <= completions <= entries <= operations, 'bounded_jit_evidence', tag)
            kind = 'NATIVE'
            if row['arm'] == 'kdlock':
                key = 'jit_complete' if is_shared else 'jit_completions'
                a.check(entries == row['jit_after']-row['jit_before'] and
                        completions == row[key+'_after']-row[key+'_before'], 'jit_counter_delta', tag)
                kind = 'RETURNED_JIT' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT'
                required = is_shared or row['lock_kind'] == 'mutex' or row['threads'] >= 20
                a.check(kind != 'PARTIAL_JIT' and (not required or completions > 0), 'original_jit_requirement', tag)
                a.check(row['retired'] == shared.RETIRED, 'exact_retirement', tag)
                retired.append(dict(task=name, name=row['name'], retired=row['retired']))
                publication, image = row['published_before'], row['list_image_audit']
                a.check(publication == row['published_after'] and
                        all(publication['source'][k] == 0 for k in ('state', 'writers', 'frames')),
                        'stable_quiescent_publication', tag)
                a.check(image == a.jread(prefix+'list-image/audit.json') and image['byte_for_byte_match'] and
                        image['prefetch'] == (row['workload'] == 'list-prefetch') and
                        image['loaded_sha256'] == image['uploaded_sha256'] ==
                        a.files[prefix+'list-image/loaded.bin'], 'loaded_receipt_binding', tag)
                entry = publication['entry']
                workspace = prefix+'workspace/daemon/'+hex(entry['entry'])+'/'+str(entry['tgid'])+'/asm/'
                a.check(a.files[workspace+'jit.bin'] == image['uploaded_sha256'] and
                        a.files[workspace+'jit.o'] == image['jit_object_sha256'] and image['entry'] == entry,
                        'loaded_publication_identity', tag)
                for filename, digest in publication['images'].items():
                    a.check(a.files[workspace+filename] == digest, 'published_artifact', tag+'/'+filename)
                for previous in row.get('publications', []):
                    a.check(helper.safe_relative(previous['path']), 'safe_history_path', tag)
                    for filename, digest in previous['images'].items():
                        a.check(a.files[prefix+previous['path']+'/'+filename] == digest,
                                'previous_publication_artifact', tag+'/'+filename)
                images.append((prefix, publication, image))
                loaded.append(dict(task=name, name=row['name'], loaded_sha256=image['loaded_sha256']))
            else:
                a.check(entries == completions == 0, 'control_no_kd_execution', tag)
            for line in a.contents[prefix+'kernel.log'].decode().splitlines():
                if helper.FAULT.search(line):
                    faults.append(dict(session=tag, line=line))
            totals.update(operations=m['completed'], reads=m['reads'] if is_shared else 0,
                          writes=operations, jit_entries=entries, jit_completions=completions)
            classes[row['lock_kind']+':'+row['arm']+':'+kind] += 1
            family_counts[row['lock_kind']] += 1
            sessions.append(dict(path=tag, family=row['lock_kind'], nodes=row['list_nodes'],
                workload=row['workload'], threads=row['threads'], arm=row['arm'], repeat=row['repeat'],
                execution_class=kind, whole_ops_s=whole, peak_ops_s=peak, cpu_ns_per_op=cpu,
                operations=m['completed'], jit_entries=entries, jit_completions=completions,
                tclock_native_delegated=native_delegated))
    a.check(len(sessions) == health['sessions'] == health['functionally_valid'] == health['drained'] == 264 and
            family_counts == dict(spin=72, mutex=72, rwlock=72, rwsem=48), 'all_families_completed')
    a.check(len(cold) == health['compiled_list_audits'] == 44 and len(images) == len(retired) == 96 and
            loaded == health['loaded_images'] and retired == health['exact_retirements'], 'image_retirement_totals')
    a.check(dict(totals) == health['totals'] and dict(classes) == health['execution_classes'], 'health_arithmetic')
    a.check(source_checks == health['source_hashes_checked'] and len(binaries) == health['binary_hashes_checked'],
            'health_input_counts')
    a.check(not faults and faults == health['per_session_kernel_faults'] and health['idle'] and
            health['boot_id'] == tasks['boot_id'] == pf['boot_id'] == a.archive['boot_id'] ==
            'b65f0205-c8f9-4385-8b13-039cbce243a6', 'health_idle_identity')
    code_audits(a, helper, args.raw, cold, images)
    for name, digest in shared.REFERENCE.items():
        a.check(a.files['reference-environment/'+name] == digest ==
                health['reference_environment_sha256'][name], 'reference_environment_hash', name)
    preservation_issues = list(a.issues)
    endpoints = shared.environments(a, health)
    buckets = defaultdict(list)
    for row in sessions:
        buckets[tuple(row[k] for k in ('family', 'nodes', 'workload', 'threads', 'arm', 'execution_class'))].append(row)
    groups = []
    for key, rows in sorted(buckets.items()):
        group = dict(zip(('family', 'nodes', 'workload', 'threads', 'arm', 'execution_class'), key))
        group.update(repeats=sorted(r['repeat'] for r in rows), samples=[r['path'] for r in rows])
        for metric in ('whole_ops_s', 'peak_ops_s', 'cpu_ns_per_op'):
            values = [r[metric] for r in rows]
            for label, function in (('min', min), ('median', statistics.median), ('max', max)):
                field = metric.replace('_ops_s', '_'+label+'_ops_s') if metric != 'cpu_ns_per_op' else metric+'_'+label
                group[field] = function(values)
        group['whole_spread_pct'] = (group['whole_max_ops_s']/group['whole_min_ops_s']-1)*100
        groups.append(group)
    points, hints = compare(groups), compare(groups, prefetch=True)
    output = dict(run_id='nano-list-followup-20261020/'+Path(a.archive['guest_base']).name,
        consistent=not a.issues, evidence_integrity_passed=not preservation_issues,
        issues=a.issues, check_counts=dict(a.counts), checks=sum(a.counts.values()),
        source_commit=shared.SOURCE, archive_groups=archive_groups, source_maps=sources,
        files=len(a.files), symlinks=len(links), binary_entries=len(binaries),
        archives_manifest_sha256=helper.hashfile(args.raw/'archives.json'),
        regular_file_hash_map_sha256=helper.canonical(a.files), totals=dict(totals),
        execution_classes=dict(classes), family_counts=dict(family_counts),
        host_endpoints=endpoints, sessions=sessions, groups=groups, comparisons=points, prefetch_comparisons=hints,
        comparison_counts=dict(Counter(r['family']+':'+r['comparator']+':'+r['status'] for r in points)),
        prefetch_counts=dict(Counter(r['family']+':'+r['status'] for r in hints)),
        script_sha256=helper.hashfile(Path(__file__)), helper_sha256=SHARED_SHA, overall_acceptance='OPEN',
        limits=['Fresh three-repetition groups only; execution classes and families remain separate.',
                'PASS is observed median-whole and best-peak parity, not statistical acceptance.',
                'Prefetch comparisons require the same execution class; no inverse-rate latency claim.',
                'Whole-run JIT counters do not establish the selected peak window execution mix.',
                'Compiled/loaded bytes and retained disassembly are checked; no archived code is executed.',
                'TCLock spin/rwlock delegation, p95 latency and runtime host interference are unmeasured.',
                'TCLock exclusive has no KD completion counter; its native mutex delegation is checked and retained separately.',
                'The seven public-mutex regressions and any failed host endpoints remain unresolved.'])
    args.report.mkdir(parents=True)
    (args.report/'offline-review.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    for filename, rows in (('groups.csv', groups), ('comparisons.csv', points), ('prefetch.csv', hints)):
        flat = [{k: v for k, v in row.items() if k not in ('left', 'right', 'samples', 'repeats')} for row in rows]
        fields = list(dict.fromkeys(k for row in flat for k in row))
        with (args.report/filename).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(flat)
    print(json.dumps({k: output[k] for k in ('run_id', 'consistent', 'evidence_integrity_passed',
        'checks', 'issues', 'totals', 'family_counts', 'comparison_counts', 'prefetch_counts',
        'archives_manifest_sha256')}, sort_keys=True))


if __name__ == '__main__':
    main()
