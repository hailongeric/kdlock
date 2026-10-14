#!/usr/bin/env python3
"""Audit archived native-first correctness evidence; never execute tests.

Run from any directory. New candidate*-validation.tar.gz archives and extracted
unit/live directories are discovered automatically. The default receipt remains
FINAL_VALIDATION_PENDING; --final-unit NAME may select a completed final unit
source generation, without turning selected checks into a full-suite claim.
No frozen Python file is imported or executed. Mutation inventories use AST.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import struct
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/mutex-native-first-20261014'
ESSENTIAL = (
    'include/kd_mutex.h', 'include/kd_owned_mutex_internal.h',
    'include/kd_owned_mutex_direct.h', 'include/kd_owned_mutex_cabi.h',
    'include/exe_info.h', 'include/wrapper.S',
    'kernel_module/owned_mutex/core.c', 'kernel_module/owned_mutex/osq.c',
    'kernel_module/owned_mutex/delegation.c', 'kernel_module/owned_mutex/entry.S',
    'kernel_module/exe.c', 'kernel_module/kd_exec.c',
    'kernel_module/execution/frame_lifecycle.inc',
    'kernel_module/execution/control_calls.inc',
    'kernel_module/execution/wrapper_entry.inc',
    'kernel_module/execution/native.inc',
    'disassem/entry_abi.py', 'disassem/special_inst.py', 'disassem/disassem.py',
)
MUTATIONS = (
    ('core', 'test_owned_mutex_core.py', r'owned mutex fixture rejects ([\w-]+)', ('mutations',)),
    ('preflight', 'test_owned_mutex_preflight.py', r'owned preflight fixture rejects ([\w-]+)', ('mutations',)),
    ('osq', 'test_owned_mutex_osq.py', r'bounded OSQ fixture rejects ([\w-]+)', ('mutations',)),
    ('queue', 'test_owned_mutex_delegation.py', r'PASS rejected mutation: ([\w-]+)', ('mutations', 'notification_mutations')),
    ('profile', 'test_owned_mutex_profile.py', r'diagnostic preflight fixture rejects ([\w-]+)', ('mutations',)),
    ('cabi', 'test_owned_mutex_cabi.py', r'ABI4 mutation detected: ([\w-]+)', ('mutations',)),
    ('capacity', 'execution/test_exec_capacity.py', r'capacity mutation detected: ([\w-]+)', ('mutations', 'constructor_mutations')),
)
FAULT = re.compile(r'BUG:|WARNING: CPU:|Oops:|general protection fault|kernel panic|KASAN:|UBSAN:|soft lockup|hard LOCKUP', re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stream_digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1 << 20), b''):
        value.update(block)
    return value.hexdigest()


def digest(path):
    with path.open('rb') as stream:
        return stream_digest(stream)


def read(path):
    return json.loads(path.read_text())


def relative(path):
    return str(path.resolve().relative_to(ROOT))


def receipt(path):
    return dict(path=relative(path), bytes=path.stat().st_size, sha256=digest(path))


def aggregate(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def archive(path, extracted):
    files, links, roots = {}, {}, set()
    with tarfile.open(path, 'r:gz') as tar:
        for item in tar:
            name = PurePosixPath(item.name)
            require(not name.is_absolute() and '..' not in name.parts, 'unsafe archive member: '+item.name)
            if len(name.parts) >= 2:
                roots.add('/'.join(name.parts[:2]))
            target = extracted.joinpath(*name.parts)
            if item.isdir():
                continue
            if item.issym():
                links[item.name] = item.linkname
                # Absolute workspace links are intentionally not materialized.
                if target.is_symlink():
                    require(str(target.readlink()) == item.linkname, 'symlink target differs: '+str(target))
                else:
                    require(not target.exists(), 'archive link unexpectedly replaced: '+str(target))
                continue
            require(item.isfile(), 'unsupported archive member: '+item.name)
            require(item.name not in files, 'duplicate regular archive member: '+item.name)
            stream = tar.extractfile(item)
            expected = stream_digest(stream)
            require(target.is_file() and not target.is_symlink(), 'missing extracted file: '+str(target))
            require(target.stat().st_size == item.size and digest(target) == expected,
                    'extracted bytes differ: '+str(target))
            files[item.name] = expected
    return dict(**receipt(path), regular_files=len(files), symlinks=len(links),
                extracted_bytes_equal=True, roots=sorted(roots),
                member_hashes_sha256=aggregate(files), symlink_targets_sha256=aggregate(links),
                symlink_policy='Original target strings audited in tar; omitted absolute workspace links are not followed.')


def sources(folder):
    manifest = next((folder/name for name in ('sources.json', 'source-sha256.json') if (folder/name).is_file()), None)
    require(manifest is not None, 'missing source manifest: '+str(folder))
    values = read(manifest)
    require(isinstance(values, dict) and values, 'empty source manifest')
    for name, expected in values.items():
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts, 'unsafe source identity')
        frozen = folder/'source'/name
        require(frozen.is_file() and digest(frozen) == expected, 'source mismatch: '+str(frozen))
    essential = {name: values[name] for name in ESSENTIAL if name in values}
    require('kernel_module/owned_mutex/core.c' in essential, 'missing owned core source')
    # Stage1 precedes ABI4. Later generations must freeze its actual transport.
    if 'KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2' in (folder/'source/include/exe_info.h').read_text():
        require(set(essential) == set(ESSENTIAL) or not (folder/'source/disassem').exists(),
                'missing ABI4 source identity: '+str(folder))
    return dict(manifest=receipt(manifest), checked_files=len(values), all_bytes_equal=True,
                manifest_mapping_sha256=aggregate(values), protocol_sha256=essential,
                protocol_mapping_sha256=aggregate(essential))


def command(path):
    value = read(path)
    require(isinstance(value.get('argv'), list) and value['argv'], 'missing command argv')
    return dict(artifact=receipt(path), argv=value['argv'], cwd=value.get('cwd'),
                timeout_seconds=value.get('timeout_seconds'),
                returncode=value.get('returncode', value.get('exit_code')),
                returncode_recorded='returncode' in value or 'exit_code' in value)


def mutation_names(path, dictionaries):
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(
                isinstance(target, ast.Name) and target.id in dictionaries for target in node.targets):
            names.update(ast.literal_eval(key) for key in node.value.keys)
    require(names, 'empty frozen mutation inventory: '+str(path))
    return names


def units(folder):
    results = read(folder/'result.json')
    groups = {}
    for name, value in results.items():
        log = folder/(name+'.log')
        require(log.is_file(), 'missing group log: '+str(log))
        passed = value.get('passed') is True
        cmd = command(folder/(name+'.log.command.json'))
        match = re.search(r'command exited (\d+):', value.get('error', ''))
        # The command sidecar records launch metadata only. Keep derived status
        # explicitly separate instead of inventing a numeric sidecar returncode.
        groups[name] = dict(passed=passed, log=receipt(log), command=cmd,
            driver_result_returncode=0 if passed else int(match[1]) if match else None,
            driver_result_returncode_basis='result.json passed flag / command-exited error',
            error=value.get('error'))
        if cmd['returncode_recorded']:
            require((cmd['returncode'] == 0) == passed, 'command/result disagreement')
    log = (folder/'unit.log').read_text()
    summary = re.findall(r'Unit tests: (\d+) passed, (\d+) failed', log)
    require(len(summary) == 1, 'missing unit summary: '+str(folder))
    require((int(summary[0][1]) == 0) == groups['unit']['passed'], 'unit summary/result disagreement')
    mutations = []
    for label, filename, pattern, dictionaries in MUTATIONS:
        driver = folder/'source/tests/unit'/filename if '/' in filename else folder/'source/tests/unit/mutex'/filename
        if not driver.is_file():
            continue
        expected = mutation_names(driver, dictionaries)
        for item in sorted(folder.glob('*.log')):
            observed = re.findall(pattern, item.read_text())
            if not observed and item.name != label+'-mutations.log':
                continue
            require(len(set(observed)) == len(observed) and set(observed) <= expected,
                    'unknown/duplicate mutation receipt: '+str(item))
            mutations.append(dict(family=label, driver=receipt(driver), log=receipt(item),
                expected_count=len(expected), observed_count=len(observed),
                complete=set(observed) == expected, observed=sorted(observed),
                missing=sorted(expected-set(observed))))
    warnings = []
    if (folder/'provider.log').exists():
        warnings = [line for line in (folder/'provider.log').read_text().splitlines() if 'warning:' in line.lower()]
    return dict(directory=relative(folder), kind='selected_unit_and_build_checks',
                result=receipt(folder/'result.json'), sources=sources(folder), groups=groups,
                unit_groups=dict(passed=int(summary[0][0]), failed=int(summary[0][1])),
                all_selected_commands_passed=all(row['passed'] for row in groups.values()),
                mutations=mutations, provider_warning_lines=warnings,
                full_suite=False)


def live(folder):
    manifest = sources(folder)
    binaries = []
    binary_manifest = folder/'binary-sha256.json'
    for original, expected in read(binary_manifest).items():
        suffix = original.split('/'+folder.name+'/', 1)
        frozen = folder/suffix[1] if len(suffix) == 2 else folder/'binaries'/Path(original).name
        require(frozen.is_file() and digest(frozen) == expected, 'binary identity differs: '+str(frozen))
        binaries.append(dict(original_path=original, artifact=receipt(frozen)))
    rows = []
    failure = read(folder/'failure.json') if (folder/'failure.json').exists() else None
    for row in read(folder/'functional.json'):
        path = folder/row['name']/'session.json'
        if not path.is_file():
            require(failure and row['status'] == 'NOT_RUN' and not row['drained'] and not row['jit_bodies'],
                    'functional session missing without recorded stop: '+str(path))
            rows.append(dict(status='NOT_RUN_AFTER_RETAINED_FAILURE', name=row['name'],
                             scenario=row['scenario'], planned_session_path=relative(path)))
            continue
        value = read(path); measured = value['measurement']; workers = measured['workers']
        require(value['functional'] and value['mutex_implementation'] == 'owned-v1', 'wrong functional scope')
        require(measured['data_ok'] and measured['complete'] and value['drained'], 'incorrect or undrained functional result')
        require(len(workers) == value['threads'] and all(w['error'] == 0 and w['completed'] == value['iterations'] for w in workers),
                'missing worker progress')
        require(measured['completed'] == value['iterations']*value['threads'], 'wrong total operations')
        require(all(w['observed_cpu'] == w['cpu'] for w in workers), 'worker CPU differs')
        require(value['jit_bodies'] == value['jit_after']-value['jit_before'] == row['jit_bodies'], 'JIT count differs')
        require(row['status'] == value['execution_status'] and row['drained'] == value['drained'], 'functional summary differs')
        require(value['retired'] == dict(frames=0, modules=0, state=2, writers=0), 'source retirement incomplete')
        kernel = path.parent/'kernel.log'; text = kernel.read_text()
        require(not FAULT.search(text), 'kernel error: '+str(kernel))
        require('kd_mutex tasks: active_tasks=0 ' in text and 'kd_exec invariant_failures=0' in text,
                'missing task/frame final drain')
        require(read(path.parent/'drain.counts.json')['active'] == 0, 'active workload on drain')
        acks = value.get('owned_full_ack')
        successful = value['execution_status'] == 'OK'
        if successful:
            require(value['jit_acceptance'] == 'PASS' and value['jit_bodies'] > 0 and not value.get('cleanup_error'), 'missing returned JIT acceptance')
            if value.get('owned_mutex_force_full'):
                require(acks and acks['started'] == acks['completed'] and acks['started'] > 0 and acks['unlocks'] >= 2,
                        'FULL owner ACKs incomplete')
                observed = re.findall(r'kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)', text)
                require(len(observed) == 1 and tuple(map(int, observed[0])) ==
                        (acks['started'], acks['completed'], acks['unlocks']), 'FULL receipt/kernel mismatch')
                require('reason=OWNED_CONTROL_NATIVE ' in text, 'missing checked FULL continuation')
            if value['scenario'] == 'early':
                require(value['owned_observations']['early_releases'] > 0, 'no delegated early outer release')
        else:
            require(failure and failure['status'] == value['execution_status'] == 'NO_JIT' and value['jit_bodies'] == 0,
                    'unclassified retained functional failure')
        for parameter, field in [('owned_mutex_early_release', 'owned_mutex_early_release'),
                                 ('owned_mutex_refill', 'owned_mutex_refill'),
                                 ('owned_mutex_native_first', 'owned_mutex_native_first')]:
            require(value['parameters'][parameter] == ('Y' if value[field] else 'N'), 'policy readback differs')
        rows.append(dict(session=receipt(path), kernel_log=receipt(kernel),
            status='PASS' if successful else 'RETAINED_NO_JIT_FAILURE', scenario=value['scenario'],
            threads=value['threads'], entry_abi=value['entry_abi'], completed=measured['completed'],
            worker_progress_verified=True, jit_bodies=value['jit_bodies'], full_ack=acks,
            owned_observations=value['owned_observations'], drained=True,
            cleanup_error=value.get('cleanup_error'),
            policy={name: value[name] for name in ('owned_mutex_cabi', 'owned_mutex_native_first',
                    'owned_mutex_native_first_spins', 'owned_mutex_early_release', 'owned_mutex_refill')},
            commands=[command(p) for p in sorted(path.parent.glob('*.command.json'))]))
    return dict(directory=relative(folder), sources=manifest, kind='actual_owned_functional_jit',
                sessions=rows, retained_failure=failure, performance_scored=False,
                binary_manifest=receipt(binary_manifest), binaries=binaries,
                build_and_setup_commands=[command(p) for p in sorted(folder.glob('*.command.json'))])


def wait_probe(folder):
    value = read(folder/'result.json'); identity = read(folder/'identity.json')
    require(value['passed'] and value['drained'], 'wait probe failed')
    require([row['spin_limit'] for row in value['results']] == [0, 1024, 4096], 'wait budgets differ')
    module = folder/'kdlock_km.ko'
    require(digest(module) == identity['module_sha256'], 'wait module differs')
    logs = []
    for row in value['results']:
        require(all(row[name] for name in ('pickup', 'queued_cooling', 'result_sleep', 'drained')) and row['jit_bodies'] == 0,
                'missing wait/cooling result')
        run = folder/f'spin-{row["spin_limit"]}'; text = (run/'kernel.log').read_text()
        require(not FAULT.search(text), 'wait kernel error')
        require('queued_cooling=1 result_sleep=1 pickup=1 drained=1 jit_bodies=0' in text and
                'kd_mutex tasks: active_tasks=0 ' in text, 'missing wait/drain kernel evidence')
        require(read(run/'retire.log')['frames'] == 0 if (run/'retire.log').read_text().startswith('{') else
                'retired' in (run/'retire.log').read_text().lower(), 'wait retirement unrecognized')
        load = read(run/'load.log.command.json')['argv']
        require(('owned_mutex_early_release=1' in load) == identity['owned_early_release'], 'guard load policy differs')
        logs.append(receipt(run/'kernel.log'))
    return dict(directory=relative(folder), kind='constructed_packet_wait_cooling_pickup',
                sources=sources(folder), result=receipt(folder/'result.json'), identity=receipt(folder/'identity.json'),
                module=receipt(module), early_release_guard=identity['owned_early_release'],
                results=value['results'], kernel_logs=logs,
                commands=[command(p) for p in sorted(folder.rglob('*.command.json')) if 'source' not in p.relative_to(folder).parts],
                actual_jit_bodies=0, passed=True, drained=True)



def task_probe(folder):
    identity = read(folder/'identity.json')
    require(identity.get('scope') == 'task_owner_ack_resource_probe', 'unknown resource probe')
    module = folder/'kdlock_km.ko'
    require(digest(module) == identity['module_sha256'], 'task module differs')
    text = (folder/'kernel.log').read_text()
    require(not FAULT.search(text), 'task probe kernel error')
    output = dict(directory=relative(folder), kind='shared_task_registry_and_owner_ack_constructed_probe',
        sources=sources(folder), identity=receipt(folder/'identity.json'), module=receipt(module),
        kernel_log=receipt(folder/'kernel.log'), cpus=identity['cpus'], actual_jit_bodies=0,
        commands=[command(p) for p in sorted(folder.rglob('*.command.json'))
                  if 'source' not in p.relative_to(folder).parts],
        scope_limit='Constructed continuation uses original Linux mutexes; not actual owned-object JIT/ACK acceptance.')
    result_path = folder/'result.json'
    if not result_path.exists():
        load = folder/'load.log'
        require(load.exists() and any(message in load.read_text() for message in
                ('Invalid argument', 'Invalid parameters')), 'unclassified task probe failure')
        output.update(status='RETAINED_MODULE_LOAD_FAILURE', result=None, load_log=receipt(load),
                      passed=False, drained=None,
                      failure_limit='Load failed before the successful-result receipt; no drain or numeric exit code is inferred.')
        return output
    value = read(result_path)
    require(value['passed'] and value['drained'] and value['jit_bodies'] == 0 and
            value['orders'] == ['B-A', 'A-B'] and value['acks'] == 4 and value['deferred_frees'] == 2,
            'task/ACK result incomplete')
    require(value['registry_stress_workers'] == 3 and value['registry_stress_iterations'] == 4096 and
            value['registry_stress_deferred_frees'] == 3, 'task stress result incomplete')
    require('orders=2 acks=4 deferred_frees=2 failures=0 jit_bodies=0' in text and
            'registry stress: workers=3 iterations=4096 deferred_frees=3 failures=0 jit_bodies=0' in text and
            'kd_mutex tasks: active_tasks=0 ' in text, 'task kernel receipt incomplete')
    output.update(status='PASS', result=receipt(result_path), observed=value, passed=True, drained=True)
    return output


def profile_load_failure(folder):
    """Retain failed instrumentation separately from subsequent resource probes."""
    failure = read(folder/'failure.json')
    require(failure['status'] == 'PREPARATION_FAILED' and
            'command exited 1:' in failure['error'] and 'kd_mutex_profile.ko' in failure['error'],
            'unclassified profiler preparation failure')
    cases = [path for path in folder.glob('c01-*') if path.is_dir() and
             (path/'load-profile.log').exists() and
             'Cannot allocate memory' in (path/'load-profile.log').read_text()]
    require(len(cases) == 1, 'expected one retained profiler allocation failure')
    case = cases[0]; session = read(case/'session.json')
    kernel = (case/'kernel.log').read_text()
    require(session['diagnostic'] and session['profile_lock'] and
            session['execution_status'] == 'PREPARATION_FAILED' and session['drained'],
            'profiler failure status or drain differs')
    require('percpu: allocation failed, size=264 align=32' in kernel and
            'alloc from reserved chunk failed' in kernel and
            '__alloc_reserved_percpu' in kernel and
            'kd_mutex_profile: Could not allocate 264 bytes percpu data' in kernel,
            'missing reserved per-CPU failure diagnosis')
    require(not FAULT.search(kernel), 'additional unclassified kernel fault in profiler failure')
    require(session['retired'] == dict(frames=0, modules=0, state=2, writers=0) and
            'kd_mutex tasks: active_tasks=0 ' in kernel and
            'kd_exec invariant_failures=0' in kernel and 'kd kernel module exit' in kernel,
            'profiler failure did not retain complete provider teardown')
    warmup = read(case/'warmup.json'); drain = read(case/'drain.counts.json')
    require(warmup['complete'] and warmup['data_ok'] and warmup['completed'] == 96000 and
            all(row['completed'] == 48000 and row['error'] == 0 for row in warmup['workers']) and
            drain['active'] == 0 and drain['values'] == warmup['after'],
            'profiler failed warmup/drain changed')
    require(not (case/'result.json').exists() and not (case/'timed.json').exists(),
            'unexpected scored result after profiler preparation failure')
    for name in ('unload-source.log', 'unload-kdlock.log', 'unload-allocator-guard.log'):
        require((case/name).exists() and not (case/name).read_text().strip(),
                'profiler failure teardown command contains an error')
    return dict(directory=relative(folder), case_directory=relative(case),
        kind='retained_diagnostic_profiler_load_failure', sources=sources(folder),
        status='RETAINED_PREPARATION_FAILURE', profiler_load_returncode=1,
        returncode_source='failure.json error records the failed insmod exit code',
        kernel_allocation_warning_retained=True, measured_profile_available=False,
        performance_scored=False, drained=True, warmup_completed=warmup['completed'],
        warmup_jit_bodies=session['owned_observations']['bodies'],
        artifacts=[receipt(path) for path in (folder/'failure.json', case/'session.json',
            case/'load-profile.log', case/'kernel.log', case/'warmup.json', case/'drain.counts.json')],
        commands=[command(path) for path in sorted(case.glob('*.command.json'))],
        scope_limit='The kernel emitted an allocation warning and stack trace while loading instrumentation after warmup. No measured owned profile completed; this failure does not count as a passing diagnostic or actual functional JIT acceptance. Subsequent cooling/task probes retain independent clean kernel logs.')


def elf_text(path):
    """Extract .text without executing ELF or relying on a saved objcopy claim."""
    data = path.read_bytes()
    require(data[:7] == b'\x7fELF\x02\x01\x01' and len(data) >= 64,
            'expected little-endian ELF64 object: '+str(path))
    require(struct.unpack_from('<HH', data, 16) == (1, 62), 'expected x86-64 relocatable object')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    require(size == 64 and count > names_index and offset + size*count <= len(data), 'invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + size*i) for i in range(count)]
    names_header = sections[names_index]
    names = data[names_header[4]:names_header[4]+names_header[5]]
    found = []
    for section in sections:
        require(section[0] < len(names), 'invalid ELF section name offset')
        end = names.find(b'\x00', section[0])
        require(end >= 0, 'unterminated ELF section name')
        if names[section[0]:end] == b'.text':
            require(section[1] == 1 and section[4]+section[5] <= len(data), 'invalid ELF .text')
            found.append(data[section[4]:section[4]+section[5]])
    require(len(found) == 1, 'missing/duplicate ELF .text')
    return found[0]


def final_continuity(tests, unit_rows, live_rows):
    """Audit the explicitly documented C5 -> C6 unwind-only change."""
    previous = tests/'mutex-native-first-candidate5-20261014'
    current = tests/'mutex-native-first-candidate6-20261014'
    comparison = tests/'mutex-native-first-entry-text-20261014'
    if not all(folder.exists() for folder in (previous, current, comparison)):
        return None
    before, after = read(previous/'sources.json'), read(current/'sources.json')
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    entry = 'kernel_module/owned_mutex/entry.S'
    fixture = 'tests/unit/mutex/test_owned_mutex_cabi.py'
    require(changed == [entry, fixture], 'C5/C6 change is no longer limited to unwind metadata/fixture macros')
    old_entry, new_entry = ((folder/'source'/entry).read_text() for folder in (previous, current))
    additions = (
        '\t/* These are capture copies, not spills needed by the returning SELF\n'
        '\t * path. The C ABI preserves their physical values and this stack frame. */\n'
        '\tUNWIND_HINT_SAVE\n',
        '\tUNWIND_HINT_RESTORE\n',
    )
    normalized = new_entry
    for added in additions:
        require(normalized.count(added) == 1, 'unrecognized unwind entry change')
        normalized = normalized.replace(added, '', 1)
    require(normalized == old_entry, 'entry contains a change beyond the two unwind hints/comment')
    old_fixture, new_fixture = ((folder/'source'/fixture).read_text() for folder in (previous, current))
    old = r"'#define UNWIND_HINT_FUNC\n'"
    new = r"'#define UNWIND_HINT_FUNC\n#define UNWIND_HINT_SAVE\n#define UNWIND_HINT_RESTORE\n'"
    require(new_fixture.count(new) == 1 and new_fixture.replace(new, old, 1) == old_fixture,
            'fixture contains a change beyond empty unwind macro definitions')
    code, objects, sections = [], [], []
    for label in ('candidate5', 'candidate6'):
        obj = comparison/(label+'.o'); section = comparison/(label+'.text')
        actual = elf_text(obj)
        require(actual == section.read_bytes(), 'ELF .text differs from archived extracted section')
        code.append(actual); objects.append(receipt(obj)); sections.append(receipt(section))
    expected_sha = 'f135553e463b5677ab046934bbf46b25f23b3c26baa3ab190b956224c003581c'
    require(code[0] == code[1] and len(code[0]) == 204 and hashlib.sha256(code[0]).hexdigest() == expected_sha,
            'entry machine code changed')
    require(read(comparison/'comparison.json') == dict(same_text=True, bytes=204,
            candidate5_sha256=expected_sha, candidate6_sha256=expected_sha), 'saved text comparison differs')
    warnings = []
    for folder in (previous, current):
        warnings.append([line for line in (folder/'provider.log').read_text().splitlines() if 'warning: objtool:' in line])
    require(len(warnings[0]) == 13 and len(warnings[1]) == 12 and set(warnings[1]) <= set(warnings[0]),
            'C6 objtool diagnostics changed unexpectedly')
    removed = sorted(set(warnings[0])-set(warnings[1]))
    require(len(removed) == 1 and 'kd_owned_mutex_outer_lock_cabi_v2+0x9a: return with modified stack frame' in removed[0],
            'unexpected removed objtool diagnostic')
    selected = next(row for row in unit_rows if row['directory'] == relative(current))
    require(selected['all_selected_commands_passed'] and any(row['family'] == 'cabi' and row['complete'] and
            row['observed_count'] == 8 for row in selected['mutations']), 'C6 ABI4 checks incomplete')
    inherited = [row['directory'] for row in live_rows if relative(previous) in row['exact_protocol_matching_unit_generations']]
    require(inherited, 'missing C5 actual live evidence')
    return dict(previous_unit=relative(previous), final_unit=relative(current), changed_source_files=changed,
        every_other_frozen_source_identical=True, source_changes_limited_to_unwind_metadata_and_fixture_macros=True,
        independent_elf_text_extraction=True, entry_text_bytes=204, entry_text_sha256=expected_sha,
        entry_objects=objects, entry_text_sections=sections, comparison=receipt(comparison/'comparison.json'),
        provider_logs=[receipt(folder/'provider.log') for folder in (previous, current)],
        objtool=dict(previous=13, final=12, new=[], removed=removed, remaining=warnings[1]),
        final_selected_checks_passed=True, final_cabi_mutations=8, c5_live_protocol_sources=inherited,
        scope='C5 live protocol evidence carries across a verified unwind-only entry change; C6 live checks were not repeated here. C6 compiled/JIT ABI4 checks were repeated. Existing 12 objtool diagnostics remain.')


def task_retry(raw, task_rows):
    first = next((row for row in task_rows if Path(row['directory']).name == 'mutex-native-first-task-ack-20261014'), None)
    retry = next((row for row in task_rows if Path(row['directory']).name == 'mutex-native-first-task-ack-retry-20261014'), None)
    if first is None or retry is None:
        return None
    require(not first['passed'] and retry['passed'] and first['module']['sha256'] == retry['module']['sha256'] and
            first['sources']['manifest_mapping_sha256'] == retry['sources']['manifest_mapping_sha256'] and
            first['cpus'] == retry['cpus'] == [0, 32, 33], 'task retry changed payload or requested CPUs')
    log = raw/'candidate5-task-console.log'
    require('command exited 1:' in log.read_text() and 'mutex_task_cpus=0,32,33' in log.read_text(), 'missing failed task driver exit')
    success = raw/'candidate5-task-retry-console.log'
    require('PASS: RCU task lifetime and real owner ACKs; two orders, four ACKs, no JIT bodies' in success.read_text(),
            'missing task retry driver pass')
    source = ROOT/first['directory']/'source/tests/kernel/mutex/mutex_task_selftest.c'
    require(re.search(r'!cpumask_test_cpu\(cpu, current->cpus_ptr\)\) \{\s+ret = -EINVAL;', source.read_text()),
            'frozen task probe affinity rejection differs')
    return dict(first=first['directory'], retry=retry['directory'], identical_module_and_sources=True,
        requested_cpus=[0, 32, 33], first_driver_exitcode=1, first_console=receipt(log), retry_console=receipt(success),
        affinity_check=receipt(source), retry_passed=True, retry_acks=4, retry_orders=['B-A', 'A-B'],
        reported_failure_cause='The operator reports an initial taskset -c 63 launcher, excluding requested CPUs 0,32,33; retry used full affinity.',
        cause_evidence_limit='The archived inner insmod command and frozen affinity check are consistent with this explanation; the outer launcher affinity is not captured in these command sidecars.')


def candidate_source_deltas(unit_rows):
    """Describe generation changes; do not turn earlier tests into reruns."""
    numbered = []
    for row in unit_rows:
        match = re.fullmatch(r'mutex-native-first-candidate(\d+)-20261014', Path(row['directory']).name)
        if match:
            numbered.append((int(match[1]), row))
    numbered.sort(key=lambda pair: pair[0])
    output = []
    for (previous_number, previous), (current_number, current) in zip(numbered, numbered[1:]):
        before = read(ROOT/previous['sources']['manifest']['path'])
        after = read(ROOT/current['sources']['manifest']['path'])
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        output.append(dict(previous_candidate=previous_number, current_candidate=current_number,
            previous_unit=previous['directory'], current_unit=current['directory'],
            changed_source_files={name: dict(previous=before.get(name), current=after.get(name)) for name in changed},
            changed_protocol_files=[name for name in changed if name in ESSENTIAL],
            unchanged_source_files=sum(before.get(name) == after.get(name) for name in before.keys() & after.keys()),
            current_selected_commands_passed=current['all_selected_commands_passed'],
            current_complete_mutation_families=[dict(family=row['family'], count=row['observed_count'],
                driver=row['driver'], log=row['log']) for row in current['mutations'] if row['complete']],
            equivalence_claim=False,
            scope='Source deltas and checks actually recorded for this generation; changed production must be assessed through its own evidence.'))
    return output


def cli_rejections(raw, unit_rows, live_rows):
    """Retain the known C7 argument typo separately from executed sessions."""
    selected = next((row for row in unit_rows if Path(row['directory']).name ==
                    'mutex-native-first-candidate7-20261014'), None)
    if selected is None:
        return []
    failed = raw/'candidate7-live-console.log'
    retry = raw/'candidate7-live-retry-console.log'
    require(failed.exists() and retry.exists(), 'missing C7 CLI failure/retry consoles')
    require('run_mutex.py: error: unrecognized arguments: --mutex-scenario nested' in failed.read_text(),
            'unrecognized C7 CLI failure')
    sessions = {Path(row['directory']).name: row for row in live_rows if '/mutex-native-first-c7-' in row['directory']}
    require(set(sessions) == {f'mutex-native-first-c7-{scenario}-20261014' for scenario in ('plain', 'nested', 'early')},
            'C7 successful functional sessions missing')
    for name, row in sessions.items():
        require(len(row['sessions']) == 1 and row['sessions'][0]['status'] == 'PASS', 'C7 functional failure')
        result = row['sessions'][0]
        console = failed if '-plain-' in name else retry
        require(f'completed={result["completed"]}; jit_bodies={result["jit_bodies"]}; drained=True' in console.read_text(),
                'C7 functional console/receipt differs')
    return [dict(status='RETAINED_CLI_PARSE_FAILURE', failed_console=receipt(failed), retry_console=receipt(retry),
        rejected_arguments=['--mutex-scenario', 'nested'], replacement_option='--scenario',
        numeric_returncode=None, numeric_returncode_recorded=False,
        successful_functional_directories=sorted(row['directory'] for row in sessions.values()),
        scope='The rejected invocation stopped at argument parsing before a test case loaded. The same console retains the preceding successful plain case; nested/early were executed by the corrected retry. Numeric launcher exit status is not present in these console files.')]


def wrapper_c9(extracted, covered, unit_rows):
    name = 'tests/mutex-native-first-wrapper-c9-20261014'
    if name not in covered:
        return None
    folder = extracted/name; saved = read(folder/'equivalence.json')
    unit = next(row for row in unit_rows if Path(row['directory']).name == 'mutex-native-first-candidate9-20261014')
    source = ROOT/unit['directory']/'source'
    suffix = b'\n.globl main\n.section .note.GNU-stack,"",@progbits\n'
    require(saved['passed'] and [row['case'] for row in saved['cases']] ==
            ['abi2-capture-first', 'abi2-preflight', 'abi4-cabi'], 'C9 wrapper cases differ')
    for name, expected in saved['headers'].items():
        require(digest(source/name) == expected, 'C9 wrapper header identity differs')
    output = []
    for row in saved['cases']:
        case = folder/row['case']; comparison = case/'wrapper-comparison'
        require(digest(source/'include/wrapper.S') == row['current_wrapper_sha256'] and
                (case/'wrapper.S').read_bytes() == (source/'include/wrapper.S').read_bytes() + suffix and
                digest(case/'wrapper.S') == row['captured_wrapper_sha256'], 'C9 wrapper capture differs')
        reference_source = (comparison/'reference.S').read_bytes()
        require(reference_source.endswith(suffix) and
                hashlib.sha256(reference_source[:-len(suffix)]).hexdigest() == row['reference_wrapper_sha256'],
                'C9 reference wrapper differs')
        generated = case/('jit.S' if row['abi'] == 4 else 'asm/jit.S')
        require(digest(generated) == row['generated_jit_sha256'], 'C9 generated body differs')
        current = case/'wrapper.o'; reference = comparison/'reference.o'
        require(digest(current) == row['current_object_sha256'] and
                digest(reference) == row['reference_object_sha256'] and
                current.read_bytes() == reference.read_bytes(), 'C9 wrapper objects differ')
        current_text = elf_text(current); reference_text = elf_text(reference)
        require(current_text == reference_text == (comparison/'current.text').read_bytes() ==
                (comparison/'reference.text').read_bytes(), 'C9 independently extracted wrapper text differs')
        require(len(current_text) == row['text_bytes'] == row['reference_text_bytes'] and
                hashlib.sha256(current_text).hexdigest() == row['current_text_sha256'] == row['reference_text_sha256'],
                'C9 wrapper text identity differs')
        for field in ('relocations', 'symbols'):
            require(row[field+'_equal'] and (comparison/('current.'+field)).read_bytes() ==
                    (comparison/('reference.'+field)).read_bytes(), 'C9 wrapper '+field+' differ')
        require(row['text_equal'] and ('callee_complete' in (comparison/'current.symbols').read_text()) ==
                (row['abi'] == 4), 'C9 ABI-specific completion symbol differs')
        output.append(dict(case=row['case'], abi=row['abi'], text_bytes=len(current_text),
            text_sha256=hashlib.sha256(current_text).hexdigest(), object_bytes_equal=True,
            independent_elf_text_extraction=True, saved_symbols_and_relocations_equal=True,
            current_object=receipt(current), reference_object=receipt(reference),
            generated_jit=receipt(generated), captured_wrapper=receipt(case/'wrapper.S'),
            reference_wrapper=receipt(comparison/'reference.S'),
            reference_compile_command=row['reference_compile_command']))
    text = (folder/'fixtures.log').read_text()
    for marker in ('capture-first: PASS actual compiled/JIT outer entry',
                   'preflight: PASS actual compiled/JIT outer entry',
                   'PASS actual ABI4 compiled/JIT entry:'):
        require(text.count(marker) == 1, 'missing/duplicate C9 compiled/JIT fixture pass')
    return dict(directory=relative(folder), receipt=receipt(folder/'equivalence.json'),
        fixtures_log=receipt(folder/'fixtures.log'), unit_generation=unit['directory'],
        cases=output, passed=True,
        scope='Three generated wrapper fixtures use identical generated bodies and current headers for each current/reference comparison. Whole object bytes and independently extracted text match; ABI2 references d8 wrapper source and ABI4 references C8 wrapper source. This does not establish whole-provider or benchmark equivalence.')


def launch_rejections_c9(raw, extracted, covered, unit_rows):
    unused_name = 'bench/mutex-native-first-c9-default64-20261014'
    retry_name = 'bench/mutex-native-first-c9-default64-retry-20261014'
    if unused_name not in covered:
        return None
    require(retry_name in covered, 'missing C9 launch retry archive')
    unused = extracted/unused_name; retry = extracted/retry_name
    first = raw/'candidate9-console.log'; second = raw/'candidate9-screen-console.log'
    complete = raw/'candidate9-screen-retry-console.log'
    require('AssertionError: CPU outside caller affinity' in first.read_text(), 'C9 affinity rejection differs')
    require('bench_runtime.Failure: new external output required' in second.read_text(), 'C9 output reuse rejection differs')
    require(not list(unused.glob('c01-*')) and not (unused/'records.json').exists() and
            not list(unused.rglob('load-*.command.json')), 'C9 rejected output contains loaded sessions')
    records = read(retry/'records.json')
    require(len(records) == 24 and all(row['drained'] and row['execution_status'] == 'OK' for row in records),
            'C9 corrected launch incomplete')
    require('[24/24]' in complete.read_text(), 'C9 corrected driver did not finish')
    frozen = sources(retry)
    unit = next(row for row in unit_rows if Path(row['directory']).name == 'mutex-native-first-candidate9-20261014')
    require(frozen['protocol_sha256'] == unit['sources']['protocol_sha256'], 'C9 retry protocol differs from unit generation')
    return dict(initial_unused_directory=relative(unused), retry_directory=relative(retry),
        failures=[dict(kind='CALLER_AFFINITY_REJECTED', console=receipt(first)),
                  dict(kind='EXISTING_OUTPUT_REJECTED', console=receipt(second))],
        no_sessions_loaded_in_rejected_directory=True, numeric_launcher_returncodes_recorded=False,
        retry_console=receipt(complete), retry_records=receipt(retry/'records.json'),
        retry_completed_sessions=24, retry_sources=frozen, matching_unit=unit['directory'],
        scope='Both invocations stopped during runner preparation before module loading. The first retained a newly created output directory; the second refused to reuse it. A fresh output path completed 24 sessions. Performance validity and acceptance are audited separately.')


def codegen_c10(extracted, covered, unit_rows):
    name = 'tests/mutex-native-first-c10-codegen-20261014'
    if name not in covered:
        return None
    folder = extracted/name; saved = read(folder/'codegen.json')
    require(saved['schema'] == 'kd_mutex_c10_codegen_v1' and
            saved['disposition'] == 'EMITTED_SIGNATURE_CHECKS_PASS' and
            len(saved['checks']) == 5 and all(saved['checks'].values()), 'C10 signature audit failed')
    unit = next(row for row in unit_rows if Path(row['directory']).name == 'mutex-native-first-candidate10-20261014')
    frozen = read(ROOT/unit['sources']['manifest']['path'])
    c8_path = extracted/'bench/mutex-native-first-c8-default64-20261014/binaries/kdlock_km.ko'
    c9_path = extracted/'bench/mutex-native-first-c9-default64-retry-20261014/binaries/kdlock_km.ko'
    supplemental_name = 'tests/mutex-native-first-final-checkout-20261014'
    supplemental = extracted/supplemental_name
    input_rows = []
    for label, item in saved['inputs'].items():
        assembly = []
        for symbol, function in item['functions'].items():
            path = folder/label/(symbol+'.asm')
            require(digest(path) == function['disassembly_sha256'], 'C10 saved disassembly differs')
            parsed = []
            start = int(function['address'], 16)
            for line in path.read_text().splitlines():
                match = re.match(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$', line)
                if match and start <= int(match[1], 16) < start + function['size']:
                    parsed.append(dict(address=hex(int(match[1], 16)), offset=hex(int(match[1], 16)-start),
                        mnemonic=match[2], operands=match[3], text=line.strip()))
            require(parsed == function['instructions'] and len(parsed) == function['instruction_count'],
                    'C10 recorded instructions differ from disassembly')
            assembly.append(receipt(path))
        if label == 'c8':
            candidates = [c8_path]
        elif label == 'c9':
            candidates = [c9_path]
        else:
            # The normal provider build differs from benchmark build copies.
            # A later supplemental archive may preserve this exact input.
            candidates = [path for path in folder.rglob('*.ko') if path.stat().st_size == item['bytes']]
            if supplemental_name in covered:
                candidates.append(supplemental/'normal-kdlock_km.ko')
        matching = [path for path in candidates if path.is_file() and digest(path) == item['sha256']]
        require(label == 'c10' or len(matching) == 1, 'archived codegen input ELF differs')
        require(len(matching) <= 1, 'ambiguous codegen input ELF')
        if matching and label in ('c8', 'c10'):
            text = elf_text(matching[0])
            stores = ({0x12bb3: '49894110', 0x12c98: '41894110', 0x12ca0: '41894114'}
                      if label == 'c8' else {0x114fb: '45896110', 0x114ff: '41895914',
                          0x11532: '4d898940140000', 0x11539: '41c7815014000001000000'})
            for address, encoded in stores.items():
                expected = bytes.fromhex(encoded)
                require(text[address:address+len(expected)] == expected, 'constructor store ELF opcode differs')
        if item['source_hashes'] is not None:
            require(all(frozen.get(path) == value['sha256'] for path, value in item['source_hashes'].items()),
                    'C10 codegen sources differ from frozen unit source')
        input_rows.append(dict(label=label, recorded_path=item['path'], recorded_bytes=item['bytes'],
            recorded_sha256=item['sha256'], exact_input_elf_archived=bool(matching),
            input_elf=receipt(matching[0]) if matching else None, disassemblies=assembly,
            reconstructed_input=bool(matching and label == 'c10' and matching[0].parent == supplemental),
            selected_store_opcodes_checked=bool(matching and label in ('c8', 'c10')),
            source_hashes=item['source_hashes']))
    def instruction(label, offset, mnemonic, operands):
        rows = saved['inputs'][label]['functions']['kd_owned_mutex_execute']['instructions']
        found = [row for row in rows if row['offset'] == hex(offset)]
        require(len(found) == 1 and found[0]['mnemonic'] == mnemonic and
                found[0]['operands'].split('#', 1)[0].strip() == operands,
                'manual constructor trace instruction differs')
        return found[0]
    baseline = [instruction('c8', 0x296, 'movabs', '$0x100000002,%rax'),
                instruction('c8', 0x2a3, 'mov', '%rax,0x10(%r9)'),
                instruction('c8', 0x356, 'mov', '%r9,0x1440(%r9)'),
                instruction('c8', 0x35d, 'movl', '$0x1,0x1450(%r9)'),
                instruction('c8', 0x371, 'movzbl', '0x48(%r11),%eax'),
                instruction('c8', 0x388, 'mov', '%eax,0x10(%r9)'),
                instruction('c8', 0x38c, 'mov', '0x4c(%r11),%eax'),
                instruction('c8', 0x390, 'mov', '%eax,0x14(%r9)')]
    candidate = [instruction('c10', 0x2f, 'movzbl', '0x48(%rdi),%r12d'),
                 instruction('c10', 0x68, 'xor', '%ebx,%ebx'),
                 instruction('c10', 0x71, 'cmp', '$0x4,%r12d'),
                 instruction('c10', 0x75, 'sete', '%bl'),
                 instruction('c10', 0x78, 'lea', '0x1(%rbx,%rbx,1),%ebx'),
                 instruction('c10', 0x7c, 'cmp', '%ebx,0x4c(%rax)'),
                 instruction('c10', 0x31b, 'mov', '%r12d,0x10(%r9)'),
                 instruction('c10', 0x31f, 'mov', '%ebx,0x14(%r9)'),
                 instruction('c10', 0x352, 'mov', '%r9,0x1440(%r9)'),
                 instruction('c10', 0x359, 'movl', '$0x1,0x1450(%r9)')]
    execute = saved['inputs']['c10']['functions']['kd_owned_mutex_execute']
    stores = [row for row in execute['instructions'] if row['mnemonic'].startswith('mov') and
              re.search(r',0x1[04]\(%r9\)$', row['operands'])]
    require([row['offset'] for row in stores] == ['0x31b', '0x31f'], 'C10 has additional constructor-pair writes through frame alias')
    require(not saved['inputs']['c10']['waiter_helper_symbols'] and
            saved['inputs']['c8']['waiter_helper_symbols'] == ['kd_owned_mutex_add_waiter'],
            'C10 waiter helper inlining signature differs')
    publish = saved['inputs']['c10']['functions']['kd_owned_mutex_publish']['instructions']
    require(not any('kd_owned_mutex_add_waiter' in row['operands'] for row in publish), 'C10 still calls waiter helper')
    nm_text = (folder/'c10/nm.txt').read_text()
    require('kd_owned_mutex_add_waiter' not in nm_text, 'C10 still exports a local waiter helper')
    helper = supplemental/'helpers/kdlock-native-first-c10-codegen.py'
    if supplemental_name in covered:
        require(digest(helper) == saved['script_sha256'], 'archived codegen helper differs')
    return dict(directory=relative(folder), saved_receipt=receipt(folder/'codegen.json'),
        five_signature_checks=saved['checks'], inputs=input_rows,
        exact_input_elves_archived=all(row['exact_input_elf_archived'] for row in input_rows),
        helper_recorded_sha256=saved['script_sha256'], helper_command=saved['command'],
        helper_artifact=receipt(helper) if supplemental_name in covered else None,
        manual_constructor_trace=dict(baseline=baseline, candidate=candidate,
            frame_alias='R9 is the per-CPU context and frames[0] base; context top/depth are at offsets 0x1440/0x1450.',
            input_alias='R12D caches the node ABI loaded from node+0x48; EBX computes 1 for ABI2 or 3 for ABI4 and validates node+0x4c before construction.',
            finding='C8 writes a fixed ABI2/MINIMAL pair, publishes top/depth, then overwrites the pair from the node. C10 writes the validated ABI/state pair once before top/depth publication.'),
        manual_publication_trace=dict(
            disassembly=receipt(folder/'c10/kd_owned_mutex_publish.asm'),
            finding='The default path links at 0x18505..0x18510 before testing WAITERS at 0x18516 and conditionally ORing it at 0x1856c. The guarded delegate path tests/ORs 9 at 0x18577..0x18583 before linking at 0x18594..0x185a3. Both return to the exact acquisition retry at 0x1851a.'),
        performance_claim=False,
        limits=['The supplemental C10 normal-build module is a reconstruction whose SHA matches the original codegen input exactly; it is not represented as the originally retained file. Earlier receipts leave this input explicitly pending until the supplemental archive exists.',
                'C10 combines constructor cleanup and waiter-helper inlining; throughput changes cannot be attributed individually.',
                'Static instructions and function size are not dynamic cycles, a full correctness test, or performance acceptance.'])


def final_checkout(extracted, covered, unit_rows):
    name = 'tests/mutex-native-first-final-checkout-20261014'
    if name not in covered:
        return None
    folder = extracted/name; first = read(folder/'result.json'); retry = read(folder/'retry-result.json')
    manifest = read(folder/'sources.json')
    for path, expected in manifest.items():
        value = PurePosixPath(path)
        require(not value.is_absolute() and '..' not in value.parts and
                digest(folder/'source'/path) == expected, 'final checkout source differs')
    unit = next(row for row in unit_rows if Path(row['directory']).name == 'mutex-native-first-candidate10-20261014')
    previous = read(ROOT/unit['sources']['manifest']['path'])
    shared_headers = {path: sha for path, sha in manifest.items() if path.startswith('include/') and path in previous}
    require(shared_headers and all(previous[path] == sha for path, sha in shared_headers.items()),
            'final checkout shared production headers changed')
    groups = []
    for label, count, result in (('runner', 75, first), ('acceptance', 15, first),
                                 ('collector-full-affinity', 14, retry)):
        log = folder/(label+'.log'); text = log.read_text()
        require(result[label]['passed'] and re.search(r'Ran '+str(count)+r' tests in ', text) and
                text.rstrip().endswith('OK'), 'final checkout test failed: '+label)
        groups.append(dict(name=label, tests=count, passed=True, log=receipt(log),
                           command=command(folder/(label+'.log.command.json'))))
    failed = (folder/'collector.log').read_text()
    require(not first['collector']['passed'] and 'command exited 1:' in first['collector']['error'] and
            'two available guest CPUs required' in failed and 'Ran 0 tests in ' in failed and
            'FAILED (errors=1)' in failed, 'final collector setup failure differs')
    require(retry['normal-provider']['passed'], 'normal provider reconstruction command failed')
    module = folder/'normal-kdlock_km.ko'; claimed = retry['codegen-input']
    require(claimed['byte_identity_verified'] and digest(module) == claimed['sha256'] ==
            claimed['expected_sha256'] == 'ade27d028a2d27b7238a1efa95107ec1100cf2a1d27fb7731f03089cb09d3b50',
            'reconstructed provider does not match original codegen input')
    comparison = folder/'post-work-equivalence'; saved = read(comparison/'equivalence.json')
    require(saved['passed'] and not saved['problems'] and saved['text_byte_identical'] and
            saved['relocations_identical'], 'isolated post-work comparison failed')
    for path, identity in saved['artifacts'].items():
        target = comparison/path
        require(target.stat().st_size == identity['bytes'] and digest(target) == identity['sha256'],
                'post-work comparison artifact differs')
    helper = folder/'helpers/kdlock-post-work-equivalence.py'
    require(digest(helper) == saved['helper_sha256'], 'post-work helper differs')
    outputs = []
    for label, row in saved['cases'].items():
        case = comparison/label
        text = elf_text(case/'post-work.o')
        require(digest(case/'post_work.h') == row['header_sha256'] and
                digest(case/'fixture.c') == row['fixture_sha256'] and
                digest(case/'post-work.o') == row['object_sha256'] and
                text == (case/'post-work.bin').read_bytes() and len(text) == row['text_bytes'] == 836 and
                hashlib.sha256(text).hexdigest() == row['text_sha256'], 'post-work identity differs')
        require(row['literal_rounds'] == ['64'] and row['multiply_count'] == row['add_count'] == 64 and
                row['exact64_alternating_pairs'] and row['constants_and_register_operands_match'] and
                row['pair_registers_match'] and row['single_text_function'] and not row['forbidden_calls_jumps_pause'],
                'post-work instruction observation differs')
        # Independently check the full leaf: mov rdi,rax; 64 exact pairs; ret.
        expected_text = bytes.fromhex('4889f8') + 64 * bytes.fromhex('4869c00d66190048055ff36e3c') + bytes.fromhex('c3')
        require(text == expected_text, 'post-work exact machine instructions differ')
        require(read(case/'compile.command.json')['argv'] == ['cc', *saved['compile_flags'], '-c', 'fixture.c', '-o', 'post-work.o'],
                'post-work compile flags differ')
        for cmd in case.glob('*.command.json'):
            require(read(cmd)['returncode'] == 0, 'post-work command failed')
        outputs.append(dict(case=label, object=receipt(case/'post-work.o'), header=receipt(case/'post_work.h'),
            text_bytes=836, multiply_add_pairs=64, exact_machine_instructions_checked=True))
    require((comparison/'current/post-work.o').read_bytes() == (comparison/'frozen/post-work.o').read_bytes() and
            (comparison/'current/relocations.stdout').read_bytes() == (comparison/'frozen/relocations.stdout').read_bytes(),
            'post-work object/relocations differ')
    require(digest(comparison/'current/post_work.h') == manifest['workload_modules/spin_cacheline/post_work.h'],
            'post-work current input differs from final checkout source')
    frozen_header = extracted/'bench/mutex-native-first-c10-default64-20261014/source/workload_modules/spin_cacheline/post_work.h'
    require(digest(comparison/'frozen/post_work.h') == digest(frozen_header), 'post-work frozen benchmark input differs')
    return dict(directory=relative(folder), selected_groups=groups,
        sources=dict(manifest=receipt(folder/'sources.json'), checked_files=len(manifest), all_bytes_equal=True,
            manifest_mapping_sha256=aggregate(manifest), shared_production_headers=len(shared_headers),
            shared_headers_match_c10=True,
            scope='This supplementary manifest captures runner/collector/benchmark inputs and shared headers; full protocol sources remain in the C10 unit archive.'),
        retained_collector_setup_failure=dict(log=receipt(folder/'collector.log'), command=command(folder/'collector.log.command.json'),
            executed_tests=0, driver_returncode=1, retry_passed=True,
            scope='The operator reports the initial launcher restricted to CPU63. The recorded setup error requires two available CPUs; a full-affinity retry passes 14 tests. This is not counted as a successful initial run.'),
        reconstructed_codegen_input=dict(module=receipt(module), original_recorded_sha256=claimed['expected_sha256'],
            byte_identity_verified=True, is_original_retained_file=False, reconstruction=claimed['note'],
            build_log=receipt(folder/'normal-provider.log'), build_command=command(folder/'normal-provider.log.command.json')),
        isolated_post_work_equivalence=dict(receipt=receipt(comparison/'equivalence.json'), helper=receipt(helper), cases=outputs,
            exact_object_text_and_relocations_equal=True, whole_workload_equivalence=False, performance_claim=False),
        helper_artifacts=[receipt(path) for path in sorted((folder/'helpers').glob('*.py'))],
        result=receipt(folder/'result.json'), retry_result=receipt(folder/'retry-result.json'),
        all_final_selected_checks_passed=True, full_suite=False)


def restored_runtime(raw, extracted, covered):
    name = 'tests/mutex-native-first-restored-20261014'
    if name not in covered:
        return None
    folder = extracted/name; saved = read(folder/'restoration.json')
    require(saved['accepted_source'] == 'ab2c3f4' and saved['mutex_implementation_source'] == 'd8d14a1' and
            saved['experimental_archive'] == '9a5305e7631247136ea89f1c8ac771afd7da3d8c' and
            saved['built'] and saved['idle'] and saved['loaded'] is False,
            'restored runtime receipt differs')
    require(re.fullmatch(r'[0-9a-f]{64}', saved['provider_sha256']), 'missing restored provider identity')
    clean = (folder/'clean.log').read_text(); build = (folder/'provider.log').read_text()
    require('kernel_module clean' in clean and 'CLEAN ' in clean and
            '/kernel_module/owned_mutex/core.o' in build and '/kernel_module/owned_mutex/osq.o' in build and
            'LD [M]  /root/host_fs/kdlock/kernel_module/kdlock_km.ko' in build and
            '/kernel_module/owned_mutex/entry.o' not in build and not re.search(r'fatal error:|make.*\*\*\*', build),
            'restored provider clean/build receipt differs')
    sync = raw/'accepted-source-sync.log'; console = raw/'accepted-source-build-console.log'
    require('verified all 869 approved hashes. No project files deleted.' in sync.read_text() and
            'Synchronization complete;' in sync.read_text() and
            console.read_text().strip() == 'PASS accepted source restored, normal provider rebuilt, VM idle',
            'restoration driver receipt incomplete')
    return dict(directory=relative(folder), receipt=receipt(folder/'restoration.json'),
        accepted_source=saved['accepted_source'], mutex_implementation_source=saved['mutex_implementation_source'],
        archived_experiment=saved['experimental_archive'], accepted_runtime_restored=True,
        clean_and_normal_build_passed=True, observed_idle=True, restored_module_loaded=False,
        provider_sha256_recorded=saved['provider_sha256'], provider_elf_archived=False,
        logs=[receipt(folder/'clean.log'), receipt(folder/'provider.log'), receipt(sync), receipt(console)],
        provider_warning_lines=[line for line in build.splitlines() if 'warning:' in line.lower()],
        new_tests_run=False, new_benchmarks_run=False, full_suite=False, performance_acceptance=False,
        scope='Separate post-study restoration receipt. The recorded source identities and provider SHA come from the restoration driver; this archive retains logs, not the rebuilt ELF. Synchronization verified its approved source hashes, the clean rebuild completed, and the VM was reported idle with the rebuilt module never loaded. Earlier experimental checks remain tied to their own archived sources.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=RAW)
    parser.add_argument('--output', type=Path, default=HERE/'validation.json')
    parser.add_argument('--final-unit', help='Explicit final unit directory name; selected checks only')
    args = parser.parse_args()
    raw = args.raw.resolve(); extracted = raw/'extracted'; tests = extracted/'tests'
    paths = sorted(set(raw.glob('candidate*-validation.tar.gz')) | set(raw.glob('waiters-stage1.tar.gz')) |
                   set(raw.glob('final-checkout-validation.tar.gz')) | set(raw.glob('restored-validation.tar.gz')))
    require(paths, 'no correctness archives')
    archives = [archive(path, extracted) for path in paths]
    covered = {name for row in archives for name in row['roots']}
    unit_rows, live_rows, wait_rows, task_rows, profile_failures = [], [], [], [], []
    for name in sorted(covered):
        if PurePosixPath(name).parts[0] not in ('tests', 'bench'):
            continue
        # Functional outputs can live under either evidence namespace. Only
        # roots verified against a complete archive enter the receipt.
        folder = extracted/name
        if not folder.is_dir():
            continue
        if (folder/'functional.json').exists():
            live_rows.append(live(folder))
        elif (folder/'identity.json').exists():
            if read(folder/'identity.json').get('scope') == 'task_owner_ack_resource_probe':
                task_rows.append(task_probe(folder))
            else:
                wait_rows.append(wait_probe(folder))
        elif (folder/'unit.log').exists():
            unit_rows.append(units(folder))
        elif (folder/'failure.json').exists() and 'kd_mutex_profile.ko' in (folder/'failure.json').read_text():
            profile_failures.append(profile_load_failure(folder))
    final = None
    if args.final_unit:
        final = next((row for row in unit_rows if Path(row['directory']).name == args.final_unit), None)
        require(final and final['all_selected_commands_passed'], 'final selected unit generation failed/missing')
    for row in live_rows + wait_rows + task_rows + profile_failures:
        matching = [unit['directory'] for unit in unit_rows if all(
            unit['sources']['protocol_sha256'].get(name) == sha for name, sha in row['sources']['protocol_sha256'].items())]
        row['exact_protocol_matching_unit_generations'] = matching
        require(matching, 'live protocol bytes match no frozen unit generation: '+row['directory'])
    continuity = final_continuity(tests, unit_rows, live_rows)
    task_relationship = task_retry(raw, task_rows)
    source_deltas = candidate_source_deltas(unit_rows)
    rejected_cli = cli_rejections(raw, unit_rows, live_rows)
    wrapper_equivalence = wrapper_c9(extracted, covered, unit_rows)
    rejected_launches = launch_rejections_c9(raw, extracted, covered, unit_rows)
    constructor_codegen = codegen_c10(extracted, covered, unit_rows)
    checkout = final_checkout(extracted, covered, unit_rows)
    restoration = restored_runtime(raw, extracted, covered)
    result = dict(schema=1, audit_passed=True,
        disposition='FINAL_VALIDATION_PENDING' if final is None else 'SELECTED_FINAL_UNIT_GENERATION_AUDITED',
        final_unit_generation=final['directory'] if final else None,
        scope='Offline byte and receipt audit of selected VM checks; no build or test executed by this program.',
        full_suite_pass=False, performance_acceptance=False,
        experiment=dict(implementation_commit='9a5305e7631247136ea89f1c8ac771afd7da3d8c',
            archive_tag='archive/perf/mutex-native-first-20261014',
            disposition='REJECTED_PERFORMANCE_EXPERIMENT', runtime_integrated=False,
            scope='Receipts describe archived experimental source generations. They do not claim the accepted runtime contains this implementation; final integration is report-only.'),
        reproduction_command=shlex.join([sys.executable, relative(Path(__file__)), *sys.argv[1:]]),
        auditor=receipt(Path(__file__)), archives=archives, unit_generations=unit_rows,
        functional_runs=live_rows, wait_probes=wait_rows, task_probes=task_rows,
        retained_profiler_failures=profile_failures,
        candidate5_candidate6_unwind_continuity=continuity, task_failure_retry=task_relationship,
        candidate_source_deltas=source_deltas, retained_cli_rejections=rejected_cli,
        candidate9_wrapper_equivalence=wrapper_equivalence, candidate9_launch_rejections=rejected_launches,
        candidate10_codegen=constructor_codegen,
        final_checkout_checks=checkout,
        accepted_runtime_restoration=restoration,
        summary=dict(archives=len(archives), unit_generations=len(unit_rows),
            failed_unit_generations=sum(not row['all_selected_commands_passed'] for row in unit_rows),
            actual_jit_sessions=sum(s['status']=='PASS' for row in live_rows for s in row['sessions']),
            retained_no_jit_sessions=sum(s['status']=='RETAINED_NO_JIT_FAILURE' for row in live_rows for s in row['sessions']),
            not_run_after_failure=sum(s['status']=='NOT_RUN_AFTER_RETAINED_FAILURE' for row in live_rows for s in row['sessions']),
            guarded_cooling_probes=len(wait_rows),
            task_registry_ack_passes=sum(row['passed'] for row in task_rows),
            retained_task_load_failures=sum(not row['passed'] for row in task_rows),
            retained_profiler_load_failures=len(profile_failures),
            wrapper_equivalence_cases=len(wrapper_equivalence['cases']) if wrapper_equivalence else 0,
            retained_preload_launch_rejections=len(rejected_launches['failures']) if rejected_launches else 0,
            reviewed_constructor_codegen=bool(constructor_codegen),
            final_checkout_test_cases=sum(row['tests'] for row in checkout['selected_groups']) if checkout else 0,
            retained_collector_setup_failures=1 if checkout else 0,
            accepted_runtime_restored=bool(restoration),
            retained_cli_parse_failures=len(rejected_cli)),
        limits=[
            'Later candidate/final evidence is pending unless explicitly selected; earlier passes do not certify later bytes.',
            'Command sidecars retain argv/start/timeout, generally not numeric returncodes. Unit result.json supplies separately labelled driver outcomes.',
            'A complete mutation family is tied to its exact frozen driver and log, including partial/failed unit generations; no inherited rerun is claimed.',
            'Constructed cooling probes execute no JIT. Actual JIT and forced FULL/ACK acceptance are separate functional receipts.',
            'Archive/extraction/source equality proves internal consistency, not independent authentication of execution location.',
        ])
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(disposition=result['disposition'], **result['summary']), sort_keys=True))


if __name__ == '__main__':
    main()
