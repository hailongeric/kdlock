#!/usr/bin/env python3
"""Fresh, serialized public mutex measurements against frozen OUTER controls."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
THREADS = [*range(1, 9), *range(12, 61, 4)]
GROUPS = ('c01', 'c08', 'rcuht', 'seek-set', 'seek-end', 'pipebytes', 'pipecap')
ARMS = ('baseline-kd', 'public-kd', 'native', 'tclock')
# Seven separated losses plus the three original incomparable class groups.
# Filter the original order so every selected repeat keeps its arm rotation.
REPLAY_POINTS = frozenset({
    ('c08', 2), ('c08', 3), ('c08', 4), ('c08', 5), ('rcuht', 2),
    ('pipebytes', 3), ('pipebytes', 4), ('pipebytes', 5), ('pipecap', 4), ('pipecap', 5),
})
REPLAY_INPUTS_SHA256 = 'df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73'
REPLAY_HARNESS_SHA256 = '8081cbed66833c59e0c58f0aa62d9f6ff87e8c28438ac7b1252584881879bf20'
REPLAY_ENVIRONMENT_SHA256 = {
    'host-state.json': '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a',
    'environment.json': '7c19cf8989a5cf56d78edec014f991354ec0ba929f8bd5d1f495fd5ae942bbf5',
    'topology.json': 'a1375dd2e696fdc379fe2d3bddbd77247638d6a82946aa9ff14da45384d41816',
}
BASELINE = Path('/root/kdlock-evidence/10.176.26.71/bench/'
                'mutex32-native-tclock-20261020/current')


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def clock_point():
    """Bracket the guest measurement clock without assuming host clock sync."""
    before = time.time_ns()
    monotonic = time.monotonic_ns()
    after = time.time_ns()
    return dict(realtime_before_ns=before, monotonic_ns=monotonic,
                realtime_after_ns=after, realtime_ordered=after >= before)


def session_clock(out, spec, phase):
    # These reads/writes surround the entire retained session, outside its
    # worker interval. The raw client timestamps remain authoritative. Host
    # alignment still needs separately retained clock calibration and bounds.
    with (out/'session-clocks.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(name=spec['name'], phase=phase,
                                     clock=clock_point()), sort_keys=True)+'\n')


def execution_order(groups=GROUPS, threads=THREADS, repeats=3):
    """Rotate four arms at each point; preserve the explicit matched rounds."""
    return [(group, count, repeat, arm)
            for gi, group in enumerate(groups)
            for ti, count in enumerate(threads)
            for repeat in range(repeats)
            for arm in (ARMS[(gi + ti + repeat) % 4:] +
                        ARMS[:(gi + ti + repeat) % 4])]


def replay_order():
    return [row for row in execution_order() if row[:2] in REPLAY_POINTS]


def bundle_key(group, arm, candidate=None):
    # A provider experiment changes only public KD. Native/TCLock must retain
    # the original current bundle and identity, despite sharing its old view.
    version = ('candidate-public' if candidate is not None and arm == 'public-kd'
               else 'baseline' if arm == 'baseline-kd' else 'current')
    return version + '/' + group


def candidate_output(manifest_path, out):
    base, out = manifest_path.resolve().parent, out.resolve()
    if out.is_relative_to(base) or base.is_relative_to(out):
        raise ValueError('measurement output overlaps frozen candidate inputs')


def retained_harness(prepared):
    """Bind historical absolute names to their retained bytes, never today's checkout."""
    prepared = prepared.resolve()
    if sha(prepared/'harness-inputs.json') != REPLAY_HARNESS_SHA256:
        raise ValueError('retained harness manifest differs from the reviewed original')
    original = load(prepared/'harness-inputs.json')
    checkout = Path('/root/host_fs/kdlock')
    retained = {}
    for filename, digest in original.items():
        path = Path(filename)
        if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(checkout):
            raise ValueError('unexpected original collector path: ' + filename)
        copy = prepared/'harness'/path.relative_to(checkout)
        if copy.is_symlink() or not copy.resolve().is_relative_to((prepared/'harness').resolve()):
            raise ValueError('collector path escapes retained tree: ' + filename)
        retained[str(copy.resolve())] = digest
    verify(retained)
    return retained


def verify_collector_modules(collector_root, manifest, loaded=()):
    """Reject accidental imports from the later checkout or unbound retained code."""
    collector_root = collector_root.resolve()
    bound = {Path(filename).resolve() for filename in manifest}
    names = {}
    for path in bound:
        if path.suffix == '.py':
            names.setdefault(path.stem, set()).add(path)
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        expected = names.get(name.rsplit('.', 1)[-1])
        if expected and (not filename or Path(filename).resolve() not in expected):
            raise ValueError('collector module has unexpected origin: ' + name)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(ROOT) and path != Path(__file__).resolve():
            raise ValueError('replay imported current collector code: ' + str(path))
        if path.is_relative_to(collector_root) and path not in bound:
            raise ValueError('unbound retained collector module: ' + str(path))
    # The two spec-loaded runners are intentionally not in sys.modules.
    for module, relative in loaded:
        path = Path(module.__file__).resolve()
        if path != collector_root/relative or path not in bound:
            raise ValueError('explicit collector has unexpected origin: ' + str(path))


def replay_inputs(prepared, out):
    """Prevent copied metadata from redirecting views into another original run."""
    prepared, out = prepared.resolve(), out.resolve()
    if out.exists() or out.is_relative_to(prepared) or prepared.is_relative_to(out):
        raise ValueError('replay needs a new output independent of prepared inputs')
    if sha(prepared/'frozen-inputs.json') != REPLAY_INPUTS_SHA256:
        raise ValueError('replay inputs differ from the reviewed original comparison')
    frozen = load(prepared/'frozen-inputs.json')
    if set(frozen) != {v+'/'+g for v in ('baseline', 'current') for g in GROUPS}:
        raise ValueError('replay bundle set differs')
    for key, inputs in frozen.items():
        bundle = Path(inputs['bundle']).resolve()
        if bundle != prepared/key:
            raise ValueError('replay bundle is outside selected prepared root: ' + key)
        for filename in inputs['files']:
            path = Path(filename)
            if (not path.is_absolute() or '..' in path.parts or
                    not path.resolve().is_relative_to(bundle)):
                raise ValueError('replay input escapes its original bundle: ' + filename)
    return frozen


def same_environment(original_host, host, original_env, environment, original_topology, topology):
    """Compare configuration exactly and retain changing resident-page counts."""
    for key in ('cpufreq', 'numa', 'recovery_snapshot'):
        if host[key] != original_host[key]:
            raise ValueError('replay host configuration differs: ' + key)
    if len(host['qemu']) != 1 or len(original_host['qemu']) != 1:
        raise ValueError('replay requires the same single QEMU')
    original, current = original_host['qemu'][0], host['qemu'][0]
    for key in ('pid', 'args'):
        if original[key] != current[key]:
            raise ValueError('replay QEMU identity/configuration differs: ' + key)
    def pins(qemu):
        return sorted((t['comm'], t['affinity']) for t in qemu['tasks'])
    if pins(original) != pins(current):
        raise ValueError('replay QEMU thread placement differs')
    def memory(qemu):
        rows = []
        for line in qemu['numa_maps'].splitlines():
            fields = line.split()
            if len(fields) < 2 or not fields[1].startswith('bind:'):
                continue
            values = dict(field.split('=', 1) for field in fields[2:] if '=' in field)
            rows.append(dict(address=fields[0], policy=fields[1],
                             page_kb=int(values['kernelpagesize_kB']),
                             resident_pages={k: int(v) for k, v in values.items()
                                             if re.fullmatch(r'N[0-9]+', k)}))
        if not rows:
            raise ValueError('missing actual host NUMA memory placement')
        return rows
    before, after = memory(original), memory(current)
    configuration = lambda rows: [(r['address'], r['policy'], r['page_kb']) for r in rows]
    if configuration(before) != configuration(after):
        raise ValueError('replay host memory binding differs')
    for key in ('boot_id', 'cmdline', 'preemption', 'packages', 'python',
                'snapshot_tag', 'collector_topology'):
        if original_env[key] != environment[key]:
            raise ValueError('replay guest environment differs: ' + key)
    if original_topology != topology:
        raise ValueError('replay guest topology differs')
    return dict(configuration_matches=True, original_memory=before, replay_memory=after,
                scope='Same QEMU process/configuration, pins, frequency policy, memory bindings, '
                      'guest boot, dependencies and topology. Resident pages are recorded, not fixed.')


def binary_paths(bundle, synthetic):
    """Resolve retained copies, never a later overwritten checkout binary."""
    result = {}
    if synthetic:
        for original, digest in load(bundle/'binary-sha256.json').items():
            old = Path(original)
            if 'variants' in old.parts:
                tail = old.parts[old.parts.index('variants'):]
                if (len(tail) != 3 or tail[1] not in ('kdlock', 'native', 'tclock')
                        or tail[2] != 'mutex_cacheline.ko'):
                    raise ValueError('unexpected variant binary: ' + original)
                path = bundle.joinpath(*tail)
            elif old.is_relative_to('/root/host_fs/kdlock'):
                if old.name not in ('client', 'daemon', 'kdlock_km.ko',
                                     'tc_allocator_guard.ko', 'tclock_mutex_backend_km.ko'):
                    raise ValueError('unexpected synthetic binary name: ' + original)
                path = bundle/'binaries'/old.name
            else:
                raise ValueError('unexpected synthetic binary: ' + original)
            if str(path) in result and result[str(path)] != digest:
                raise ValueError('contradictory frozen binary: ' + str(path))
            result[str(path)] = digest
    else:
        for relative, item in load(bundle/'binaries.json').items():
            path = Path(relative)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('invalid frozen API binary path')
            if not str(item['path']).endswith('/build/' + relative):
                raise ValueError('API binary path disagrees with manifest key')
            result[str(bundle/'build'/path)] = item['sha256']
    return result


def bundle_inputs(bundle, synthetic):
    files = binary_paths(bundle, synthetic)
    sources = load(bundle/'source-sha256.json')
    for relative, digest in sources.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('invalid frozen source path')
        files[str(bundle/'source'/path)] = digest
    for name in ('plan.json', 'source-sha256.json', 'binary-sha256.json',
                 'binaries.json', 'environment.json', 'build-ready.json'):
        if (bundle/name).is_file():
            files[str(bundle/name)] = sha(bundle/name)
    return dict(files=files, source_identity=identity(sources))


def verify(files):
    for name, digest in files.items():
        if sha(Path(name)) != digest:
            raise ValueError('frozen input changed: ' + name)


def executable_copy(path):
    """Enable execution only on the new evidence copy of a verified program."""
    from elftools.elf.elffile import ELFFile
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_X86_64' or elf['e_type'] not in ('ET_EXEC', 'ET_DYN'):
            raise ValueError('expected a copied x86-64 executable: ' + str(path))
    before = path.stat().st_mode & 0o777
    path.chmod(before | 0o100)
    return dict(path=str(path), mode_before=oct(before), mode_after=oct(before | 0o100),
                sha256=sha(path))


def prepare_command(group, output):
    common = ['--output', str(output), '--build-only', '--mutex-api', 'public',
              '--threads', *map(str, THREADS), '--repeats', '3',
              '--backends', 'native', 'tclock', 'kdlock',
              '--duration-ms', '2000', '--collector-cpu', '63']
    if group in ('c01', 'c08', 'rcuht'):
        command = [sys.executable, str(ROOT/'bench/tclock_compare/run_mutex.py'),
                   '--cpus', '0-59', '--peak-window-ms', '300',
                   '--peak-settle-ms', '300', '--sample-ms', '10',
                   '--iterations', '100000', '--numa', 'on',
                   '--kd-batch-size', '1024', '--kd-provider-ubsan', 'off',
                   '--spin-prefetch', '2', '--spin-entry-ratio-limit', '2']
        command += (['--workload', 'rcuht'] if group == 'rcuht' else
                    ['--cachelines', str(int(group[1:]))])
    else:
        kind, query = (('seek', group[5:]) if group.startswith('seek-')
                       else (group, 'query'))
        command = [sys.executable, str(ROOT/'bench/real_api/run.py'),
                   '--cpus', ','.join(map(str, range(60))),
                   '--kinds', kind, '--queries', query, '--entries', '16',
                   '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
                   '--helper-waves', '4', '--helper-workers', '8']
    return command + common


def runners(collector_root=ROOT, harness=None):
    collector_root = collector_root.resolve()
    sys.dont_write_bytecode = True
    if harness is not None:
        verify_collector_modules(collector_root, harness)
    sys.path.insert(0, str(collector_root/'bench/tclock_compare'))
    spec = importlib.util.spec_from_file_location('mutex_comparison_synthetic',
                                                collector_root/'bench/tclock_compare/run.py')
    synthetic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic)
    import session as syn_session
    import bench_session
    sys.path.insert(0, str(collector_root/'bench/real_api'))
    spec = importlib.util.spec_from_file_location('mutex_comparison_api',
                                                collector_root/'bench/real_api/run.py')
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    if harness is not None:
        verify_collector_modules(collector_root, harness, (
            (synthetic, 'bench/tclock_compare/run.py'),
            (api, 'bench/real_api/run.py'),
        ))
    return synthetic, syn_session, bench_session, api


def prepare(out, baseline, syn):
    syn.idle()
    out.mkdir(parents=True, exist_ok=False)
    (out/'current').mkdir()
    commands = []
    for group in GROUPS:
        command = prepare_command(group, out/'current'/group)
        receipt = dict(group=group, argv=command, state='STARTING', started_utc=utc())
        commands.append(receipt)
        save(out/'prepare-commands.json', commands)
        with (out/f'prepare-{group}.log').open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       cwd=ROOT, start_new_session=True)
            receipt.update(pid=process.pid, state='RUNNING', timeout_seconds=420)
            save(out/'prepare-commands.json', commands)
            try:
                status = process.wait(timeout=420)
                receipt.update(status=status, state='FINISHED', finished_utc=utc())
            except BaseException as error:
                receipt.update(state='UNCERTAIN', error=repr(error))
                # No signal/timeout proves build children exited. Preserve the
                # process and exact PID for inspection; do not start another.
                raise
            finally:
                save(out/'prepare-commands.json', commands)
        if status:
            raise RuntimeError('preparation failed: ' + group)
        print('Prepared ' + group, flush=True)
    frozen = {}
    # Copy only the verified retained inputs, not historical sessions. New
    # archives then contain the baseline bytes instead of depending on links
    # to a previous evidence tree. All original manifests remain unchanged.
    baseline_copies, executable_modes = {}, []
    for group in GROUPS:
        original = baseline/group
        target = out/'baseline'/group
        inputs = bundle_inputs(original, group in ('c01', 'c08', 'rcuht'))
        verify(inputs['files'])
        for filename in inputs['files']:
            source = Path(filename)
            dest = target/source.relative_to(original)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        for name in ('source-sha256.json', 'binary-sha256.json', 'binaries.json',
                     'plan.json', 'environment.json'):
            if (original/name).is_file():
                shutil.copy2(original/name, target/name)
        binary_folder = target/('binaries' if group in ('c01', 'c08', 'rcuht') else 'build')
        executable_modes += [executable_copy(binary_folder/name) for name in ('client', 'daemon')]
        if not all(os.access(binary_folder/name, os.X_OK) for name in ('client', 'daemon')):
            raise ValueError('retained baseline executables lost their modes')
        baseline_copies[group] = dict(original=str(original), files=inputs['files'])
        workload = (target/'variants/kdlock/mutex_cacheline.ko'
                    if group in ('c01', 'c08', 'rcuht') else
                    target/'build'/('kdlock-'+('seek' if group.startswith('seek-') else group))/'real_api.ko')
        imports = syn.command(['nm', '-u', workload], out/f'baseline-{group}-imports.txt')
        if (not {'kd_mutex_outer_contended_clobber_v1',
                 'kd_mutex_direct_unlock_clobber_v1'} <= set(imports.split())
                or 'kd_mutex_direct_lock_clobber_v1' in imports.split()):
            raise ValueError('retained baseline is not the expected OUTER caller')
    save(out/'baseline-copy-provenance.json', baseline_copies)
    for group in GROUPS:
        binary_folder = out/'current'/group/('binaries' if group in ('c01', 'c08', 'rcuht') else 'build')
        executable_modes += [executable_copy(binary_folder/name) for name in ('client', 'daemon')]
    save(out/'copied-executable-modes.json', executable_modes)
    for version, parent in (('baseline', out/'baseline'), ('current', out/'current')):
        for group in GROUPS:
            bundle = parent/group
            inputs = bundle_inputs(bundle, group in ('c01', 'c08', 'rcuht'))
            verify(inputs['files'])
            frozen[version+'/'+group] = dict(bundle=str(bundle), **inputs)
    save(out/'frozen-inputs.json', frozen)
    # Preserve the exact collection harness as well as every measured input.
    harness = {str(path): sha(path) for path in Path(__file__).parent.glob('*.py')}
    harness.update({str(ROOT/relative): digest for relative, digest in
                    syn.source_state().items()})
    for relative in ('bench/real_api/run.py', 'bench/real_api/evidence.py'):
        harness[str(ROOT/relative)] = sha(ROOT/relative)
    for filename in harness:
        source = Path(filename)
        target = out/'harness'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    save(out/'harness-inputs.json', harness)
    syn.idle()
    save(out/'prepared.json', dict(passed=True, prepared_utc=utc(), sessions_run=0,
                                  baseline=str(baseline)))


def synthetic_session(syn, syn_session, bench_session, view, spec):
    # A session caches backend paths at construction and uses them through
    # cleanup. Rebind the two client identities together, restoring only after
    # the session returns; an unsafe failure always stops the whole collection.
    bindings = [(syn_session, 'PROVIDER', view/'binaries/kdlock_km.ko'),
                (bench_session, 'PROVIDER', view/'binaries/kdlock_km.ko'),
                (syn_session, 'HERE', view/'binaries'),
                (bench_session, 'HERE', view/'binaries'),
                (syn_session, 'TC_MUTEX_MODULE', view/'binaries/tclock_mutex_backend_km.ko'),
                (syn_session, 'GUARD_MODULE', view/'binaries/tc_allocator_guard.ko')]
    previous = [(module, name, getattr(module, name)) for module, name, _ in bindings]
    try:
        for module, name, value in bindings:
            setattr(module, name, value)
        session = syn.BackendSession(view, spec, workload_module=
                                     view/'variants'/spec['arm']/'mutex_cacheline.ko')
        session.translation_source = view/'source'
        session.daemon_binary = view/'binaries/daemon'
        syn.execute_session(session, keep_going_no_jit=True)
        return session
    finally:
        for module, name, value in previous:
            setattr(module, name, value)


def specification(template, group, count, repeat, arm, inputs, topology):
    result = dict(template)
    backend = 'kdlock' if arm in ('baseline-kd', 'public-kd') else arm
    result.update(name=f'{group}-t{count:02d}-r{repeat}-{arm}',
                  threads=count, cpus=list(range(count)), repeat=repeat,
                  arm=backend, comparison_arm=arm, comparison_workload=group,
                  source_identity=inputs['source_identity'],
                  cpu_nodes=[topology[cpu] for cpu in range(count)],
                  collector_cpu=63, collector_shared=False,
                  caller_shell=('mutex_outer_cookie' if arm == 'baseline-kd' else
                                'mutex_public_direct' if arm == 'public-kd' else 'c'),
                  cookie_storage=('outer_acquisition_local' if arm == 'baseline-kd' else
                                  'provider_acquisition_ledger' if arm == 'public-kd'
                                  else 'not_applicable'))
    # Older API receipts predate shell identities. This explicit retained
    # baseline has compiled OUTER callers; no unknown historical run is inferred.
    if result['duration_ms'] != 2000:
        raise ValueError('comparison needs the recorded two-second timing')
    return result


def measure(prepared, out, syn, syn_session, bench_session, api, budget, smoke, host_state,
            replay=False, candidate=None):
    if candidate is not None and not replay:
        raise ValueError('isolated provider candidates require the original replay gates')
    if candidate is not None:
        candidate_output(Path(candidate['manifest_path']), out)
    if not load(prepared/'prepared.json')['passed'] or out.exists():
        raise ValueError('new, completely prepared comparison required')
    out.mkdir()
    host = load(host_state)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(host['captured_utc'])).total_seconds()
    if (not host.get('pins_verified') or not host.get('snapshot_listed')
            or host.get('recovery_snapshot') != os.environ['KDLOCK_SNAPSHOT_TAG']
            or not 0 <= age <= 300):
        raise ValueError('fresh verified host placement/snapshot receipt required')
    save(out/'host-state.json', host)
    cmdline = Path('/proc/cmdline').read_text().strip()
    preemption = Path('/sys/kernel/debug/sched/preempt').read_text().strip()
    packages = {name: importlib.metadata.version(name)
                for name in ('miasm', 'future', 'pyparsing', 'pyelftools')}
    if (not {'nokaslr', 'nopvspin'} <= set(cmdline.split())
            or '(voluntary)' not in preemption
            or Path('/sys/devices/system/cpu/online').read_text().strip() != '0-63'
            or packages != dict(miasm='0.1.5', future='1.0.0',
                                pyparsing='2.4.7', pyelftools='0.27')):
        raise ValueError('live boot/dependency policy differs')
    save(out/'environment.json', dict(captured_utc=utc(), cmdline=cmdline,
        preemption=preemption, packages=packages, python=sys.executable,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
        collector_topology=syn.collector_topology(63), argv=sys.argv))
    frozen = load(prepared/'frozen-inputs.json')
    if candidate is not None:
        # The original fourteen bundles remain independently bound and checked.
        # Dedicated derived views never modify or relabel a control bundle.
        if set(frozen) & set(candidate['bundles']):
            raise ValueError('candidate would replace an original bundle')
        frozen.update(candidate['bundles'])
    collector_root = prepared/'harness' if replay else ROOT
    harness = retained_harness(prepared) if replay else load(prepared/'harness-inputs.json')
    verify(harness)
    if replay:
        verify_collector_modules(collector_root, harness)
        save(out/'replay-provenance.json', dict(
            prepared=str(prepared), measured_revision='d21a1e3',
            original_harness_manifest=load(prepared/'harness-inputs.json'),
            retained_collector_files=harness,
            frozen_inputs_manifest_sha256=sha(prepared/'frozen-inputs.json'),
            harness_manifest_sha256=sha(prepared/'harness-inputs.json'),
            original_matrix_status=load(prepared/'matrix/status.json'),
            scheduler_sha256=sha(Path(__file__)),
            selection='seven separated regressions plus three incomparable points',
            candidate_manifest_sha256=candidate['manifest_sha256'] if candidate else None,
            scope=('Original inputs with a separately verified public-only provider candidate'
                   if candidate else 'Original provider/caller/client/daemon/translator and collector bytes; new focused scheduler')))
        shutil.copyfile(Path(__file__), out/'replay-scheduler.py')
        shutil.copyfile(prepared/'frozen-inputs.json', out/'frozen-inputs.json')
        if candidate is not None:
            shutil.copyfile(candidate['manifest_path'], out/'candidate.json')
    syn.command([sys.executable, collector_root/'bench/spin_cacheline/kernel_identity.py',
                 '--kernel-source', '/root/linux-6.1.159-kdclobber2',
                 '--kernel-baseline',
                 '/root/kdlock-kernel-baselines/mutex-clobber2-20260919'],
                out/'kernel-identity.json', timeout=120)
    topology = syn.runtime.capture_topology(list(range(60)))
    # Use the same annotation helper as the maintained synthetic runner.
    probe = [dict(cpus=list(range(60)))]
    syn.runtime.annotate_topology(probe, topology)
    nodes = probe[0]['cpu_nodes']
    save(out/'topology.json', topology)
    if replay:
        for filename, digest in REPLAY_ENVIRONMENT_SHA256.items():
            if sha(prepared/'matrix'/filename) != digest:
                raise ValueError('original environment evidence changed: ' + filename)
        comparison = same_environment(load(prepared/'matrix/host-state.json'), host,
            load(prepared/'matrix/environment.json'), load(out/'environment.json'),
            load(prepared/'matrix/topology.json'), topology)
        save(out/'environment-comparison.json', comparison)
        order = replay_order()
    elif smoke:
        order = execution_order(('c01', 'pipebytes'), (1, 8), 1)
    else:
        order = execution_order()
    save(out/'execution-order.json', order)
    views, templates = {}, {}
    for key, inputs in frozen.items():
        bundle = Path(inputs['bundle'])
        version, group = key.split('/')
        view = out/'measurements'/version/group
        view.mkdir(parents=True, exist_ok=False)
        for folder in ('source', 'build', 'binaries', 'variants'):
            if (bundle/folder).is_dir():
                (view/folder).symlink_to(bundle/folder, target_is_directory=True)
        views[key] = view
        templates[key] = {row['arm']: row for row in load(bundle/'plan.json')}
    planned = []
    for index, (group, count, repeat, arm) in enumerate(order):
        key = bundle_key(group, arm, candidate)
        backend = 'kdlock' if arm.endswith('-kd') else arm
        spec = specification(templates[key][backend], group, count, repeat,
                             arm, frozen[key], nodes)
        spec.update(sequence=index, evidence_path=str(views[key]/spec['name']),
                    kernel_identity=sha(out/'kernel-identity.json'),
                    topology_identity=sha(out/'topology.json'))
        if candidate is not None and arm == 'public-kd':
            spec.update(provider_candidate=candidate['manifest_sha256'],
                        provider_sha256=candidate['provider_sha256'],
                        provider_revision='d21-plus-selected-003d71c-entry-patch')
        planned.append(spec)
    save(out/'plan.json', planned)
    deadline = time.monotonic() + budget
    state = dict(state='RUNNING', started_utc=utc(), planned=len(order),
                 completed=0, sessions=[])
    save(out/'status.json', state)
    records = []
    try:
        for index, (group, count, repeat, arm) in enumerate(order):
            syn.idle()
            if Path('/sys/module/real_api').exists():
                raise RuntimeError('real API module did not drain')
            if (out/'STOP').exists() or time.monotonic() + 180 > deadline:
                state.update(state='STOPPED', boundary='drained')
                break
            key = bundle_key(group, arm, candidate)
            inputs, view = frozen[key], views[key]
            verify(harness)
            if replay:
                verify_collector_modules(collector_root, harness)
            verify(inputs['files'])
            spec = planned[index]
            state['current'] = dict(workload=group, threads=count, repeat=repeat, arm=arm)
            save(out/'status.json', state)
            print(f'[{index+1}/{len(order)}] {spec["name"]}', flush=True)
            session_clock(out, spec, 'before_session')
            try:
                if group in ('c01', 'c08', 'rcuht'):
                    session = synthetic_session(syn, syn_session, bench_session, view, spec)
                else:
                    session = api.SyscallSession(view, spec)
                    session.execute()
            finally:
                session_clock(out, spec, 'after_session')
            record = session.record
            if not record['drained'] or record['execution_status'] not in ('OK', 'NO_JIT'):
                raise RuntimeError('session did not finish safely')
            records.append(record)
            save(out/'records.json', records)
            state['completed'] = index + 1
            state['sessions'].append(dict(name=record['name'],
                status=record['execution_status'], drained=record['drained'],
                path=str(session.path)))
            save(out/'status.json', state)
        else:
            state.update(state='COMPLETE', finished_utc=utc())
        syn.idle()
        if Path('/sys/module/real_api').exists():
            raise RuntimeError('real API module remains at final boundary')
        if candidate is not None:
            for inputs in frozen.values():
                verify(inputs['files'])
            verify(harness)
    except BaseException as error:
        state.update(state='FAILED', error=repr(error), failed_utc=utc())
        raise
    finally:
        save(out/'records.json', [
            load(Path(spec['evidence_path'])/'session.json')
            if (Path(spec['evidence_path'])/'session.json').exists()
            else dict(spec, execution_status='NOT_RUN', drained=False)
            for spec in planned])
        save(out/'status.json', state)
    return 0 if state['state'] == 'COMPLETE' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'smoke', 'measure', 'replay'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--prepared', type=Path,
                        help='original frozen comparison directory for focused replay')
    parser.add_argument('--candidate-manifest', type=Path,
                        help='explicit public-only provider experiment, with original replay controls')
    parser.add_argument('--candidate-manifest-sha256')
    parser.add_argument('--budget-seconds', type=int, default=14400)
    parser.add_argument('--host-state', type=Path,
                        help='host placement/snapshot JSON captured within five minutes')
    args = parser.parse_args()
    if (ROOT != Path('/root/host_fs/kdlock') or os.geteuid() != 0
            or os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1'
            or not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise RuntimeError('confirmed recovery VM required')
    if args.budget_seconds < 180:
        raise ValueError('budget must leave one bounded session')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    out = args.output.resolve()
    if out == ROOT or out.is_relative_to(ROOT):
        raise ValueError('output must be outside source checkout')
    replay = args.action == 'replay'
    candidate = None
    if bool(args.candidate_manifest) != bool(args.candidate_manifest_sha256):
        raise ValueError('candidate path and exact manifest hash are required together')
    if args.candidate_manifest and not replay:
        raise ValueError('candidate selection is only supported by focused replay')
    if replay:
        if args.prepared is None:
            raise ValueError('--prepared is required for replay')
        prepared = args.prepared.resolve(strict=True)
        replay_inputs(prepared, out)
        if (Path(sys.executable) != Path('/root/kdlock-translation-venv-20261019/bin/python3') or
                shutil.which('python3') != sys.executable):
            raise ValueError('replay driver and daemon must use the original pinned Python')
        status = load(prepared/'matrix/status.json')
        if status['state'] != 'COMPLETE' or status['completed'] != 1764:
            raise ValueError('replay requires the completed original 1764-session comparison')
        harness = retained_harness(prepared)
        collector_root = prepared/'harness'
        if args.candidate_manifest:
            candidate_output(args.candidate_manifest, out)
            spec = importlib.util.spec_from_file_location(
                'entry_candidate_inputs', ROOT/'bench/mutex_api_compare/entry_candidate.py')
            validator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(validator)
            candidate = validator.candidate_inputs(
                sys.modules[__name__], prepared, args.candidate_manifest.resolve(),
                args.candidate_manifest_sha256)
    else:
        if args.prepared is not None:
            raise ValueError('--prepared is only valid for replay')
        prepared, collector_root = out, ROOT
    syn, syn_session, bench_session, api = runners(collector_root, harness if replay else None)
    if args.action == 'prepare':
        prepare(out, args.baseline.resolve(), syn)
        return 0
    smoke = args.action == 'smoke'
    if args.host_state is None:
        raise ValueError('--host-state is required before live measurement')
    return measure(prepared, out if replay else out/('smoke' if smoke else 'matrix'),
                   syn, syn_session, bench_session, api, args.budget_seconds,
                   smoke, args.host_state, replay=replay, candidate=candidate)


if __name__ == '__main__':
    raise SystemExit(main())
