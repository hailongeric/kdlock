#!/usr/bin/env python3
"""Recompute correctness receipts from frozen owned-mutex archives, offline.

This reads data only: no compilation, workload, module operation or live source
import. It does not score performance or claim a full test-suite pass. Optional
--refill requires the later refill unit/FULL receipts and the scored source
freeze. --legacy-smoke requires the current-provider legacy plain compatibility
run at 4/16 workers. JSON is written to stdout unless --output is supplied.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[6]
DEFAULT_RAW = ROOT / 'bench/results/10.176.26.71/raw/bench/mutex-owned-v1-20261013'
RETIRED = dict(state=2, modules=0, frames=0, writers=0)
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|'
                   r'hard LOCKUP|unable to handle|general protection fault|'
                   r'Oops:|\[ERROR\]|invariant_failures=[1-9]', re.I)
BUILD_ERROR = re.compile(r'(^|\n).*?(?:fatal error:|\berror:|undefined reference|\*\*\*.*Error)', re.I)
CORE_MUTATIONS = {'force-self-handoff', 'omit-pickup', 'retain-last-flags',
                  'omit-wake-reference', 'bypass-borrowed-unlock',
                  'strand-publication-race', 'combine-ordinary-under-outer'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return stream_digest(stream)


def stream_digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(path.read_text())


def relative(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def file_receipt(path):
    require(path.is_file(), 'missing artifact: ' + str(path))
    return dict(path=relative(path), bytes=path.stat().st_size, sha256=digest(path))


def safe_relative(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts, 'unsafe archive path: ' + name)
    return Path(*path.parts)


def provider_source(name):
    return name.startswith(('include/', 'kernel_module/')) and (
        name.endswith(('.c', '.h', '.inc', '.S')) or name.endswith('/Makefile'))


def source_manifest(folder):
    path = folder / 'sources.json'
    if not path.exists():
        path = folder / 'source-sha256.json'
    manifest = read(path)
    require(manifest and all(re.fullmatch('[0-9a-f]{64}', sha)
                             for sha in manifest.values()), 'invalid source manifest: ' + str(path))
    return path, manifest


def frozen_sources(folder, reference=None):
    path, manifest = source_manifest(folder)
    matched_path = folder / 'source-matched-manifest.json'
    matched = read(matched_path) if matched_path.exists() else None
    if matched:
        require(matched['original_manifest_sha256'] == digest(path),
                'supplemental source manifest identity differs')
        require(set(matched['copied']) | set(matched['missing']) == set(manifest) and
                not set(matched['copied']) & set(matched['missing']), 'supplemental coverage differs')
    verified, missing = [], []
    for name, sha in manifest.items():
        rel = safe_relative(name)
        candidates = [folder / 'source' / rel]
        if candidates[0].exists():
            require(candidates[0].is_file() and digest(candidates[0]) == sha,
                    'archived source bytes differ: ' + str(candidates[0]))
        if matched and name in matched['copied']:
            require(matched['copied'][name]['sha256'] == sha, 'supplemental hash differs: ' + name)
            candidates.append(folder / 'source-matched' / rel)
            require(candidates[-1].is_file() and digest(candidates[-1]) == sha,
                    'supplemental source bytes differ: ' + name)
        if reference:
            candidates.append(reference / 'source' / rel)
        local = next((p for p in candidates if p.is_file() and digest(p) == sha), None)
        if local:
            verified.append(name)
        else:
            missing.append(name)
    # Every provider source identity must be backed by actual archived bytes.
    require(not any(provider_source(n) for n in missing), 'unverifiable provider source: ' + str(missing))
    result = dict(manifest=file_receipt(path), recorded_files=len(manifest),
                  verified_files=len(verified), missing_bytes=missing,
                  provider_files=sum(provider_source(n) for n in manifest))
    if matched:
        result['supplemental_preservation'] = file_receipt(matched_path)
    if reference:
        _, ref = source_manifest(reference)
        result['compared_to'] = relative(reference)
        result['provider_differences'] = [n for n in manifest if provider_source(n)
                                           and manifest[n] != ref.get(n)]
        result['provider_matches_reference'] = not result['provider_differences']
    return result


def build_receipt(folder, name='build.log', w1=True):
    path = folder / name
    text = path.read_text()
    command = read(folder / (name + '.command.json'))
    argv = command['argv'] if isinstance(command, dict) else command
    require(not BUILD_ERROR.search(text) and 'Leaving directory' in text,
            'build failed or incomplete: ' + str(path))
    require(not w1 or 'W=1' in argv, 'W=1 missing: ' + str(path))
    warnings = [line for line in text.splitlines() if 'warning:' in line]
    categories = Counter('objtool' if 'objtool:' in line else
                         'frame-size' if '-Wframe-larger-than=' in line else
                         'missing-prototype' if '-Wmissing-prototypes' in line else 'other'
                         for line in warnings)
    return dict(log=file_receipt(path), command=file_receipt(folder/(name+'.command.json')),
                argv=argv, warning_count=len(warnings), warning_categories=dict(categories),
                warning_lines=warnings, compilation_observed=bool(re.search(r'\bCC \[M\]', text)),
                module_link_observed='kdlock_km.ko' in text,
                limit='Incremental logs do not establish a clean rebuild; warnings are retained, not a warning-free claim.')


def counters(text, prefix):
    lines = re.findall(re.escape(prefix) + r' ([^\n]+)', text)
    require(len(lines) == 1, 'missing/duplicate kernel receipt: ' + prefix)
    pairs = re.findall(r'(\w+)=(\d+)', lines[0])
    require(len(pairs) == len(dict(pairs)), 'duplicate kernel counter: ' + prefix)
    return {k: int(v) for k, v in pairs}


def kernel_receipt(path):
    text = path.read_text()
    require(not FAULT.search(text), 'kernel fault: ' + str(path))
    require('kd_source retire: result=0 state=2 modules=0 frames=0 writers=0' in text and
            'kd kernel module exit' in text, 'missing retirement/unload receipt: ' + str(path))
    mutex = counters(text, 'kd_mutex stats:')
    require(mutex['active_waiters'] == mutex['reserved_nodes'] == mutex['frame_failure'] == 0 and
            mutex['origin_acquires'] == mutex['origin_releases'], 'mutex lifetime imbalance')
    tasks = counters(text, 'kd_mutex tasks:')
    native = counters(text, 'kd_native stats:')
    require(tasks['active_tasks'] == 0 and native['started'] == native['completed'], 'task/ACK imbalance')
    require('kd_exec invariant_failures=0' in text, 'missing execution invariant receipt')
    return dict(log=file_receipt(path), mutex=mutex, tasks=tasks, native=native,
                owned=counters(text, 'kd_owned_mutex:'))


def unit_receipt(folder, reference, refill=False):
    if refill:
        runner = (folder/'runner.log').read_text()
        require(re.search(r'Ran 80 tests\b',runner) and runner.rstrip().endswith('OK'),
                'refill runner80 receipt differs')
        queue_logs = [p for p in folder.glob('*.log') if p.name not in ('runner.log','build.log')
                      and 'PASS production optional FIFO refill:' in p.read_text(errors='replace')]
        require(len(queue_logs) == 1, 'missing/duplicate refill queue fixture log')
        queue = queue_logs[0]; text = queue.read_text()
        mutants = re.findall(r'PASS rejected mutation: ([\w-]+)', text)
        require('PASS production owned FIFO:' in text and len(mutants) == len(set(mutants)) == 16,
                'refill queue fixture lacks sixteen rejected mutations')
        result = dict(scope='Refill-specific subset: production FIFO/refill fixture with sixteen mutations, runner80, W=1. The earlier six-group selection was not repeated.',
            runner_tests=80, runner=file_receipt(folder/'runner.log'),
            queue=file_receipt(queue), rejected_queue_mutations=mutants,
            build=build_receipt(folder), sources=frozen_sources(folder,reference))
        result['commands'] = [file_receipt(p) for p in sorted(folder.glob('*.command.json'))]
        return result
    unit = (folder/'unit.log').read_text()
    require('Unit tests: 6 passed, 0 failed' in unit, 'selected six unit groups incomplete')
    require(set(re.findall(r'owned mutex fixture rejects ([\w-]+)', unit)) == CORE_MUTATIONS,
            'core mutation coverage differs')
    for marker in ('[PASS] test_control_call', '[PASS] test_daemon_policy',
                   'PASS production task cache:', 'PASS actual compiled/JIT outer entry:',
                   'after-outer production functions: 3447 checks, 0 failures'):
        require(marker in unit, 'missing selected unit receipt: ' + marker)
    runner = (folder/'runner.log').read_text()
    count = 79
    require(re.search(rf'Ran {count} tests\b', runner) and runner.rstrip().endswith('OK'),
            'runner test receipt differs')
    result = dict(scope='Two basic groups plus core, task cache, actual outer ABI/JIT, and native-after-outer; not the full suite.',
                  groups=6, core_rejected_mutations=sorted(CORE_MUTATIONS), runner_tests=count,
                  unit=file_receipt(folder/'unit.log'), runner=file_receipt(folder/'runner.log'),
                  build=build_receipt(folder), sources=frozen_sources(folder, reference))
    for name in ('unit.log.command.json', 'runner.log.command.json'):
        result[name] = file_receipt(folder/name)
    return result


def probe_receipt(folder, reference, kind):
    identity, result = read(folder/'identity.json'), read(folder/'result.json')
    require(result['passed'] is True and result['drained'] is True and identity['jit_bodies'] == 0,
            'resource probe failed or incorrectly classified')
    require(digest(folder/'kdlock_km.ko') == identity['module_sha256'], 'probe module hash differs')
    kernels = []
    if kind == 'task':
        require(result['acks'] == 4 and result['orders'] == ['B-A','A-B'] and
                result['registry_stress_iterations'] == 4096 and result['jit_bodies'] == 0,
                'task owner/ACK scope differs')
        paths = [folder]
    else:
        require({r['spin_limit'] for r in result['results']} == {0,1024,4096}, 'probe budgets incomplete')
        for row in result['results']:
            require(row['drained'] and row['result_sleep'] and row['jit_bodies'] == 0, 'probe did not drain/sleep')
            if kind == 'owned':
                require(row['queued_cooling'] and row['pickup'], 'owned cooling/pickup absent')
            else:
                require(row['gate_sleep'] and row['deferred_progress'] and row['errors'] == 0 and
                        row['admission_cooling_checks'] == 2, 'legacy wait coverage incomplete')
        paths = [folder/f'spin-{n}' for n in (0,1024,4096)]
    for sub in paths:
        require(read(sub/'retire.log') == RETIRED, 'probe source not retired')
        require(not (sub/'load.log').read_text().strip() and not (sub/'unload.log').read_text().strip(),
                'probe load/unload failure')
        kernels.append(kernel_receipt(sub/'kernel.log'))
    return dict(kind=kind, scope='Live resource/lifetime probe; zero returned JIT bodies.',
                result=result, result_artifact=file_receipt(folder/'result.json'),
                identity=file_receipt(folder/'identity.json'), module=file_receipt(folder/'kdlock_km.ko'),
                kernels=kernels, sources=frozen_sources(folder, reference), build=build_receipt(folder))


def frozen_binaries(folder):
    path = folder/'binary-sha256.json'
    manifest = read(path)
    for name, sha in manifest.items():
        local = folder/'variants'/name.split('/variants/',1)[1] if '/variants/' in name else folder/'binaries'/Path(name).name
        require(digest(local) == sha, 'frozen binary differs: ' + str(local))
    return dict(manifest=file_receipt(path), files=len(manifest), hashes=manifest)


def functional_receipt(folder, reference, scenario, refill=False, legacy=False):
    plan, summary = read(folder/'plan.json'), read(folder/'functional.json')
    require({s['threads'] for s in plan} == {4,16} and len(plan) == len(summary) == 2,
            'FULL grid must contain exactly 4 and 16 workers')
    env = read(folder/'environment.json')
    require(env['kernel_identity']['ok'] and env['kernel_identity']['running_build_id'] ==
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus'] == list(range(64)) and
            {'nokaslr','nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'], 'FULL environment identity differs')
    # Fixed-iteration correctness runs do not collect timed peaks; their runner
    # captures no collector topology. Do not invent CPU63 affinity evidence.
    require(env['collector_topology'] is None or
            env['collector_topology']['role_cpus'] == [63], 'unexpected collector topology')
    post_work = folder/'source/workload_modules/spin_cacheline/post_work.h'
    require(re.search(r'^#define SC_POST_WORK_ROUNDS 64\s*$', post_work.read_text(), re.M),
            'FULL frozen post-work source differs')
    sessions = []
    for spec in plan:
        sub = folder/spec['name']; record = read(sub/'session.json'); m = read(sub/'measure.json')
        require(all(record[k] == value for k,value in spec.items()), 'plan/session mismatch')
        require(record['measurement'] == m and record['scenario'] == scenario and
                record['post_work_rounds'] == 64, 'functional scenario/source work differs')
        if legacy:
            require(scenario == 'plain' and record['mutex_implementation'] == 'legacy' and
                    record['arm'] == 'kdlock' and record['caller_abi'] == 'clobber' and
                    record['mutex_acceptance'] == 'jit-required' and
                    not record.get('owned_mutex_force_full',False) and
                    not record.get('owned_mutex_refill',False) and
                    spec['iterations'] == 500000 and spec['repeat'] == 0 and
                    spec['duration_ms'] == 0, 'legacy smoke identity differs')
        else:
            require(record['owned_mutex_force_full'] and record['mutex_implementation'] == 'owned-v1' and
                    record.get('owned_mutex_refill',False) == refill and
                    record['owned_queue_policy'] == ('bounded_fifo_refill' if refill else 'finite_fifo'),
                    'FULL policy differs')
        require(record['drained'] and record['execution_status'] == 'OK' and record['retired'] == RETIRED,
                'FULL session did not retire')
        require(m['complete'] and m['data_ok'] and m['threads'] == spec['threads'] and
                m['iterations'] == spec['iterations'] and m['cachelines'] == 1, 'incorrect FULL work')
        workers = m['workers']
        require(len(workers) == spec['threads'] and [w['cpu'] for w in workers] == spec['cpus'] and
                all(w['completed'] == spec['iterations'] and w['error'] == 0 and w['cpu_ns'] > 0 and
                    w['observed_cpu'] == w['cpu'] for w in workers), 'missing worker progress/placement')
        require(m['completed'] == sum(w['completed'] for w in workers) == spec['threads']*spec['iterations'] and
                m['worker_cpu_ns'] == sum(w['cpu_ns'] for w in workers) and
                m['finished_ns'] == max(w['finished_ns'] for w in workers) and
                m['wall_ns'] == m['finished_ns']-m['started_ns'] > 0, 'worker aggregate differs')
        require(len(m['before']) == len(m['after']) == 16 and all(
            a-b == (m['completed'] if i == 0 else 0) for i,(b,a) in enumerate(zip(m['before'],m['after']))),
            'business data mismatch')
        for name in ('measure.counts.json','drain.counts.json'):
            require(read(sub/name) == dict(active=0, values=m['after']), 'workers/data not drained')
        require(record['jit_after']-record['jit_before'] == record['jit_bodies'] > 0 and
                record['jit_bodies'] <= m['completed'] and record['jit_acceptance'] == 'PASS' and
                record['execution_class'] == 'JIT', 'missing returned-body JIT')
        params = record['parameters']
        if legacy:
            require(params['mutex_native_route'] == 'N' and
                    params['mutex_entry_ratio_limit'] == str(record['mutex_entry_ratio_limit']) == '256' and
                    params['mutex_spin_limit'] == str(record['mutex_spin_limit']) and
                    params['owned_mutex_native_after_control'] == '0' and
                    params.get('owned_mutex_refill','N') == 'N' and 'mutex_jit' not in params and
                    params['bench_quiet'] == 'Y' and params['jit_timing'] == 'N' and
                    int(params['bench_lock_addr']) == record['layout']['lock_addr'],
                    'legacy smoke provider parameters differ')
        else:
            require(params['owned_mutex_self_route'] == 'N' and
                    params['owned_mutex_entry_ratio_limit'] == '256' and
                    params['owned_mutex_native_after_control'] == '1' and
                    (params.get('owned_mutex_refill','N') == 'Y') == refill,
                    'loaded FULL provider controls differ')
        warmup = read(sub/'warmup.json')
        require(warmup['complete'] and warmup['data_ok'] and
                warmup['completed'] == spec['threads'] * 48000 and
                all(w['completed'] == 48000 and w['error'] == 0 for w in warmup['workers']) and
                warmup['after'] == m['before'] and
                read(sub/'warmup.counts.json') == dict(active=0,values=m['before']),
                'FULL warmup differs')
        for name in ('load-kdlock.log','unload-kdlock.log','load-source.log','unload-source.log'):
            require(not (sub/name).read_text().strip(), 'module operation failed: '+str(sub/name))
        pub = record['published_before']
        require(pub == record['published_after'] and pub['entry']['lock_kind'] == (2 if legacy else 3) and
                pub['entry']['entry_abi'] == 2 and pub['entry']['status'] == 0,
                'publication changed or wrong owned ABI')
        images = sub/'workspace/daemon'/hex(pub['entry']['entry'])/str(pub['entry']['tgid'])/'asm'
        for name, sha in pub['images'].items():
            require(digest(images/name) == sha, 'JIT image hash differs')
        kernel = kernel_receipt(sub/'kernel.log')
        if legacy:
            require(not any(kernel['owned'].values()) and kernel['mutex']['jit_success'] > 0,
                    'legacy smoke did not execute legacy JIT or used owned execution')
        else:
            require(record['owned_full_ack'] == kernel['native'] and kernel['native']['started'] > 0 and
                    kernel['native']['unlocks'] >= 2 and record['owned_observations'] == kernel['owned'],
                    'FULL owner/ACK receipt differs')
            require((sub/'kernel.log').read_text().count('reason=OWNED_CONTROL_NATIVE') == 1,
                    'FULL injection did not occur exactly once at an owned control boundary')
        require(scenario != 'early' or kernel['owned']['early_releases'] > 0, 'no early release observed')
        require(record['layout'] == read(sub/'layout.json') and record['layout']['lock_bytes'] == 32,
                'owned object layout differs')
        line = next((s for s in summary if s['name'] == spec['name']), None)
        require(line and line['status'] == 'OK' and line['drained'] and line['jit_bodies'] == record['jit_bodies'],
                'functional summary differs')
        sessions.append(dict(name=spec['name'], workers=spec['threads'], completed=m['completed'],
            jit_bodies=record['jit_bodies'], kernel=kernel, session=file_receipt(sub/'session.json'),
            measurement=file_receipt(sub/'measure.json'), drain=file_receipt(sub/'drain.counts.json')))
    result = dict(scenario=scenario, refill=refill, sessions=sessions,
                sources=frozen_sources(folder,reference), binaries=frozen_binaries(folder),
                collector_topology=env['collector_topology'],
                plan=file_receipt(folder/'plan.json'), environment=file_receipt(folder/'environment.json'))
    if legacy:
        guard_path = folder/'source/workload_modules/mutex_cacheline/module.c'
        client_path = folder/'source/bench/spin_cacheline/client.c'
        ioctl_path = folder/'source/workload_modules/spin_cacheline/runner.inc'
        guard, client, ioctl = (p.read_text() for p in (guard_path,client_path,ioctl_path))
        for marker in ('atomic_long_read(&sc_lock.owner)', '!list_empty(&sc_lock.wait_list)',
                       'osq_is_locked(&sc_lock.osq)'):
            require(marker in guard, 'legacy idle guard absent: '+marker)
        require('case SC_WORKERS_DRAIN:' in ioctl and 'i = sc_workers_drain();' in ioctl and
                'error = ioctl(fd, SC_WORKERS_DRAIN);' in client and
                'SC_WORKERS_DRAIN (registrations retained)' in client,
                'explicit worker-drain path absent')
        require(not result['sources']['provider_differences'], 'legacy smoke/scored refill provider differs')
        result.update(scope='Current-provider legacy compatibility smoke only; no throughput acceptance.',
            legacy_idle_evidence=dict(mechanism='Successful SC_WORKERS_DRAIN precedes complete client JSON; frozen workload requires zero owner word, empty native wait_list and unlocked OSQ. Kernel counters separately prove legacy queue/task/frame drain.',
                sources=[file_receipt(p) for p in (guard_path,client_path,ioctl_path)]),
            build=build_receipt(folder,'build-provider.log',w1=False),
            workload_build=build_receipt(folder,'build-kdlock.log',w1=False))
    return result


def archive_receipt(path, extracted=None):
    regular = links = bytes_total = 0
    link_records = []
    with tarfile.open(path) as archive:
        for member in archive:
            rel = safe_relative(member.name)
            if member.isfile():
                regular += 1; bytes_total += member.size
                with archive.extractfile(member) as stream:
                    sha = stream_digest(stream)
                if extracted is not None:
                    local = extracted/rel
                    require(local.is_file() and not local.is_symlink() and local.stat().st_size == member.size and
                            digest(local) == sha, 'archive/extraction differs: '+member.name)
            elif member.issym():
                links += 1
                link_records.append(dict(name=member.name, target=member.linkname))
            else:
                require(member.isdir(), 'unexpected tar member type: '+member.name)
    return dict(archive=file_receipt(path), regular_files=regular, regular_bytes=bytes_total,
                symbolic_links=links, link_identities_sha256=hashlib.sha256(
                    json.dumps(link_records,sort_keys=True).encode()).hexdigest(),
                extracted_regular_bytes_verified=extracted is not None,
                link_policy='Links remain in the canonical archive; no target is followed or required on this host.')


def failures(raw):
    parent = raw.parents[1]/'tests'
    result = []
    analyses = {
        'pre-recovery': 'Initial static per-CPU allocation failure and later combine-under-held-outer deadlock. Recovery required; these runs are not passes.',
        'full-failure': 'Earlier FULL diagnostic used an unsupported synthetic continuation checkpoint. Its timeout/recovery is not valid FULL success evidence.',
    }
    for name, interpretation in analyses.items():
        folder = parent/f'mutex-owned-v1-{name}-20261013'
        sums = (folder/'SHA256SUMS').read_text().splitlines()
        for line in sums:
            sha, filename = line.split(maxsplit=1)
            require(digest(folder/Path(filename.strip().lstrip('*')).name) == sha, 'failure archive checksum differs')
        item = archive_receipt(folder/'evidence.tar.gz')
        item.update(analysis=interpretation, checksum=file_receipt(folder/'SHA256SUMS'),
                    serial=file_receipt(folder/'qemu-serial.log'), state=file_receipt(folder/'failure-state.txt'))
        result.append(item)
    failed = raw/'tests/mutex-owned-v1-final-task-20261013/load.log'
    require('Invalid parameters' in failed.read_text(), 'missing retained affinity EINVAL')
    result.append(dict(log=file_receipt(failed),
        analysis='First final task probe had invalid insmod/affinity parameters; final-task-r2 is the successful receipt.'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=DEFAULT_RAW)
    parser.add_argument('--refill', action='store_true')
    parser.add_argument('--legacy-smoke', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); raw = args.raw.resolve()
    finite = raw/'bench/mutex-owned-v1-fullgrid64-20261013'
    tests = raw/'tests'
    archives = []
    archive_records = [raw/f'stage{stage}-archive.json' for stage in (1,2)]
    if args.refill or args.legacy_smoke:
        extra = sorted(p for p in raw.glob('*-archive.json') if p not in archive_records)
        require(extra, 'refill archive receipt missing')
        archive_records.extend(extra)
    for record_path in archive_records:
        expected = read(record_path)
        path = raw/Path(expected['path']).name
        require(digest(path) == expected['sha256'] and path.stat().st_size == expected['bytes'], 'stage archive identity differs')
        item = archive_receipt(path,raw); item['original_receipt'] = file_receipt(record_path)
        archives.append(item)
    report = dict(schema=1, scope='Selected correctness and provenance receipts; not a full-suite or throughput acceptance claim.',
        raw=relative(raw), archives=archives,
        selected_units=unit_receipt(tests/'mutex-owned-v1-final-20261013',finite),
        probes=[probe_receipt(tests/name,finite,kind) for name,kind in (
            ('mutex-owned-v1-cooling-20261013','owned'),
            ('mutex-owned-v1-final-task-r2-20261013','task'),
            ('mutex-owned-v1-final-legacy-wait-20261013','legacy'))],
        full=[functional_receipt(tests/f'mutex-owned-v1-final-full-{s}-20261013',finite,s)
              for s in ('nested','early')], retained_failures=failures(raw))
    for receipt in [report['selected_units'], *report['full'], *report['probes'][1:]]:
        require(not receipt['sources']['provider_differences'], 'final test/scored finite provider differs')
    report['probes'][0]['source_limit'] = (
        'Cooling was run before the ordinary nested-unlock correction. Its exact source and differing '
        'core.c hash are retained; it is not a fresh final/refill-core cooling run.')
    r4 = tests/'mutex-owned-v1-r4-20261013'
    if r4.exists():
        entry = (r4/'jit-entry.log').read_text(); continuation=(r4/'continuation.log').read_text()
        mutants = re.findall(r'entry/hostcall mutation detected: ([\w-]+)',entry)
        require('production JIT entry scope: 4359 checks, 0 failures' in entry and len(set(mutants)) == 30 and
                'after-outer production functions: 3447 checks, 0 failures' in continuation,
                'earlier JIT/continuation coverage differs')
        report['earlier_r4'] = dict(jit_checks=4359, rejected_mutations=mutants,
            continuation_checks=3447, logs=[file_receipt(r4/n) for n in ('jit-entry.log','continuation.log')],
            limit='Earlier-source log-only receipt; this directory has no source manifest. Do not attribute it to final/refill source.')
    if args.refill:
        scored = raw/'bench/mutex-owned-v1-refill64-20261013'
        require(scored.is_dir(), 'refill scored source freeze missing')
        refill = dict(selected_units=unit_receipt(tests/'mutex-owned-v1-refill-20261013',scored,True),
            full=[functional_receipt(tests/f'mutex-owned-v1-refill-full-{s}-20261013',scored,s,True)
                  for s in ('nested','early')], scored_sources=frozen_sources(scored),
            scored_binaries=frozen_binaries(scored))
        for receipt in [refill['selected_units'],*refill['full']]:
            require(not receipt['sources']['provider_differences'], 'refill test/scored provider source differs')
        report['refill'] = refill
    else:
        report['refill'] = dict(status='not requested; no refill correctness claim')
    if args.legacy_smoke:
        require((raw/'stage6-archive.json').is_file(), 'legacy smoke stage6 archive receipt missing')
        report['legacy_smoke'] = functional_receipt(
            tests/'mutex-owned-v1-legacy-smoke-20261013',
            raw/'bench/mutex-owned-v1-refill64-20261013','plain',legacy=True)
    else:
        report['legacy_smoke'] = dict(status='not requested; no current-provider legacy JIT claim')
    report['audit'] = 'PASS'
    text = json.dumps(report,indent=2,sort_keys=True)+'\n'
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
