#!/usr/bin/env python3
"""Offline exact-grid nano verification. No guest calls or archived-code imports.

Inputs are completed maintained archive directories and copied sibling control
directories. The only executed project code is the explicitly trusted checkout's
oracle.py/peak.py, after byte identity against BOTH selected commits is checked.
"""
import argparse
import ast
import csv
import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
MODERN_CONTROLLERS = {
    '66c68c17457c0ae60d09ff1f3d89b5fff16a500c': 'reader-recovery',
    'e0f9696cf7ba6268bbbfa5131a9ee881f6553809': 'reader-recovery',
    '1b6f256b13e8743aa1fd7bdc958cc82ae7726463': '1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731',
    'f7a84065e84474380faa37eeadfdf534abd72a68': '1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731',
}
THREADS = [*range(1, 9), *range(12, 61, 4)]
PROFILES = {
    'mutex-throughput': ('mutex', 1, 100), 'mutex-locality': ('mutex', 16, 100),
    'rwsem-throughput-read': ('rwsem', 1, 1), 'rwsem-throughput-mixed': ('rwsem', 1, 20),
    'rwsem-locality-read': ('rwsem', 16, 1), 'rwsem-locality-mixed': ('rwsem', 16, 20),
    'rwlock-throughput-read': ('rwlock', 1, 1), 'rwlock-throughput-mixed': ('rwlock', 1, 20),
    'rwlock-locality-read': ('rwlock', 16, 1), 'rwlock-locality-mixed': ('rwlock', 16, 20),
}
POLICY = dict(total_cap=1024, numa_boundary=1024, deferred_handoff=8, scan_budget=64)
RETIRED = dict(state=2, modules=0, frames=0, writers=0)
BUILD = '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'
SUFFIXES = {'.c', '.h', '.inc', '.S', '.def', '.py', '.patch', '.json'}
MATCH = ('workload', 'cachelines', 'write_percent', 'threads', 'repeat', 'cpus', 'cpu_nodes',
         'collector_cpu', 'iterations', 'duration_ms', 'peak_window_ms', 'peak_settle_ms',
         'sample_ms', 'functional', 'post_work_rounds', 'warmup_iterations_per_worker',
         'mix_policy', 'helper_waves', 'helper_cpus', 'helper_cpu_nodes', 'lock_kind',
         'entry_abi', 'call_shell', 'nano_working_set_bytes', 'nano_layout', 'mutex_api',
         'caller_abi', 'delegate', 'rwsem_writer_shell', 'require_jit', 'spin_entry_ratio_limit',
         'numa_policy', 'provider_ubsan', 'provider_mutex_policy', 'delegation_batch_limit')


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'duplicate JSON key: '+key)
        result[key] = value
    return result


def parse(data):
    def nonfinite(value):
        raise ValueError('nonfinite JSON: '+value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)


def local_json(path):
    need(path.is_file() and not path.is_symlink(), 'missing/nonregular receipt: '+str(path))
    return parse(path.read_bytes())


def safe(name):
    p = PurePosixPath(name)
    need(isinstance(name, str) and name and not p.is_absolute() and
         '..' not in p.parts and str(p) == name, 'unsafe/noncanonical relative path: '+str(name))
    return name


def elf_modinfo(data):
    need(data[:6] == b'\x7fELF\x02\x01' and len(data) >= 64, 'expected ELF64LE')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    need(size == 64 and count and names_index < count and offset + count*size <= len(data),
         'invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset+i*size) for i in range(count)]
    strings = sections[names_index]
    names = data[strings[4]:strings[4]+strings[5]]
    found = [s for s in sections if names[s[0]:].split(b'\0', 1)[0] == b'.modinfo']
    need(len(found) == 1, 'missing/duplicate ELF modinfo')
    section = found[0]
    result = {}
    for entry in data[section[4]:section[4]+section[5]].split(b'\0'):
        if not entry:
            continue
        key, sep, value = entry.decode().partition('=')
        need(sep, 'invalid modinfo')
        result.setdefault(key, []).append(value)
    return result


class Archive:
    """One sequential scan; hashes all bytes, caches only analysis receipts.

    Archived source stays data. Regular JSON/logs are copied by bytes into a
    private flat temporary cache; no archive pathname is extracted or followed.
    """
    def __init__(self, directory, cache):
        self.directory, self.cache = directory, cache
        self.meta = local_json(directory/'archives.json')
        need(self.meta.get('completed') is True and self.meta.get('guest_idle') is True,
             'archive is not completed/idle: '+str(directory))
        need(file_sha(directory/'input-inventory.json') == self.meta['input_inventory_sha256'],
             'archive inventory hash differs')
        inventory = local_json(directory/'input-inventory.json')
        self.hashes, self.saved, self.modinfo, seen = {}, {}, {}, set()
        prefix = safe(self.meta['archive_prefix'])+'/'
        groups = self.meta['groups']
        need(groups and len({g['file'] for g in groups}) == len(groups), 'duplicate/empty archive groups')
        for group in groups:
            filename = safe(group['file'])
            need('/' not in filename, 'archive group must be a basename')
            path = directory/filename
            need(path.is_file() and not path.is_symlink() and path.stat().st_size == group['bytes'] and
                 file_sha(path) == group['sha256'], 'archive digest/size differs: '+str(path))
            with tarfile.open(path, 'r|gz') as tar:
                for item in tar:
                    need(item.name.startswith(prefix), 'archive prefix differs: '+item.name)
                    name = safe(item.name[len(prefix):])
                    need(name in inventory and name not in seen, 'extra/duplicate archive path: '+name)
                    seen.add(name)
                    expected = inventory[name]
                    need(item.mode == stat.S_IMODE(expected['mode']) and
                         (item.uid, item.gid) == (expected['uid'], expected['gid']), 'archive attributes: '+name)
                    if stat.S_ISDIR(expected['mode']):
                        need(item.isdir(), 'directory type: '+name)
                        continue
                    if stat.S_ISLNK(expected['mode']):
                        need(item.issym() and item.linkname == expected['link'], 'symlink type/target: '+name)
                        continue
                    need(stat.S_ISREG(expected['mode']) and item.isfile() and item.size == expected['bytes'],
                         'regular file type/size: '+name)
                    keep = ('/source/' not in '/'+name and
                            (name.endswith('.json') or name.endswith('/kernel.log') or name.endswith('.cmd')))
                    module = name.endswith('.ko')
                    need(not (keep or module) or item.size <= 256*1024*1024, 'oversized analysis input: '+name)
                    target = cache/str(len(self.saved)) if keep else None
                    out = target.open('wb') if target else None
                    h, data, count = hashlib.sha256(), bytearray(), 0
                    stream = tar.extractfile(item)
                    try:
                        for chunk in iter(lambda: stream.read(1 << 20), b''):
                            count += len(chunk); h.update(chunk)
                            if out: out.write(chunk)
                            if module: data.extend(chunk)
                    finally:
                        if out: out.close()
                    need(count == item.size, 'truncated archive file: '+name)
                    self.hashes[name] = h.hexdigest()
                    if target: self.saved[name] = target
                    if module: self.modinfo[name] = elf_modinfo(data)
        need(seen == set(inventory), 'archive inventory coverage differs')
        self.provenance = dict(directory=str(directory), archive_receipt_sha256=file_sha(directory/'archives.json'),
            inventory_sha256=self.meta['input_inventory_sha256'], paths=len(seen), regular_files=len(self.hashes),
            groups=[{k:g[k] for k in ('file','bytes','sha256')} for g in groups])
        health = self.json(self.meta['health_path'])
        need(self.hashes[self.meta['health_path']] == self.meta['health_sha256'] and
             health.get('idle') is True and health.get('boot_id') == self.meta['boot_id'], 'final archive health')
        for field in ('new_faults_in_retained_dmesg', 'per_session_kernel_faults'):
            need(not health.get(field, []), 'health reports faults: '+field)

    def json(self, name):
        need(name in self.saved, 'missing regular retained JSON: '+name)
        return parse(self.saved[name].read_bytes())

    def text(self, name):
        need(name in self.saved, 'missing regular retained text: '+name)
        return self.saved[name].read_text()

    def relative(self, absolute):
        prefix = self.meta['guest_base'].rstrip('/')+'/'
        need(absolute.startswith(prefix), 'path outside captured guest tree: '+absolute)
        return safe(absolute[len(prefix):])


class Git:
    def __init__(self, root):
        self.root = root

    def output(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args])

    def blob(self, commit, path):
        return self.output('show', commit+':'+path)

    def source_hashes(self, commit):
        source = ast.parse(self.blob(commit, 'bench/rwlock_compare/run.py'))
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'sources')
        loop = next(n for n in ast.walk(function) if isinstance(n, ast.For) and
                    isinstance(n.target, ast.Name) and n.target.id == 'directory')
        directories = ast.literal_eval(loop.iter)
        need(type(directories) is tuple and all(type(x) is str for x in directories), 'source recipe shape changed')
        names = self.output('ls-tree', '-r', '--name-only', commit, '--', *directories).decode().splitlines()
        selected = [n for n in names if not any(x.startswith('.') or x in ('__pycache__', 'results')
                    for x in PurePosixPath(n).parts) and not n.endswith('.mod.c') and
                    (PurePosixPath(n).suffix in SUFFIXES or PurePosixPath(n).name in
                     ('Makefile','requirements.txt','guest.config'))]
        result = {}
        proc = subprocess.Popen(['git','-C',str(self.root),'cat-file','--batch'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            for name in selected:
                proc.stdin.write((commit+':'+name+'\n').encode()); proc.stdin.flush()
                header = proc.stdout.readline().decode().split()
                need(len(header) == 3 and header[1] == 'blob', 'not a Git blob: '+name)
                size = int(header[2]); data = proc.stdout.read(size)
                need(len(data) == size and proc.stdout.read(1) == b'\n', 'truncated Git response')
                result[name] = sha(data)
        finally:
            proc.stdin.close()
            need(proc.wait(timeout=30) == 0, 'Git batch failed')
        return result


def trusted_oracles(git, baseline, candidate):
    hashes = {}
    for relative in ('bench/spin_cacheline/peak.py', 'bench/rwlock_compare/oracle.py'):
        expected = git.blob(baseline, relative)
        need(expected == git.blob(candidate, relative) == (git.root/relative).read_bytes(),
             'trusted oracle differs between source versions/checkout: '+relative)
        hashes[relative] = sha(expected)
    for name, relative in (('peak','bench/spin_cacheline/peak.py'), ('nano_offline_oracle','bench/rwlock_compare/oracle.py')):
        spec = importlib.util.spec_from_file_location(name, git.root/relative)
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module
        spec.loader.exec_module(module)
        need(file_sha(git.root/relative) == hashes[relative], 'trusted oracle changed during import')
    # Capture the exact maintained fault predicate without importing runtime/device modules.
    code = ast.parse(git.blob(candidate, 'bench/spin_cacheline/bench_runtime.py'))
    value = next(n.value for n in code.body if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == 'FAULT' for t in n.targets))
    pattern = ast.literal_eval(value.args[0])
    need(pattern == ast.literal_eval(next(n.value for n in
         ast.parse(git.blob(baseline, 'bench/spin_cacheline/bench_runtime.py')).body
         if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FAULT'
                                              for t in n.targets)).args[0]), 'fault predicates differ')
    return module, re.compile(pattern, re.I), hashes


def options(argv, name):
    need(argv.count(name) == 1, 'missing/duplicate command option: '+name)
    start = argv.index(name)+1; end = start
    while end < len(argv) and not argv[end].startswith('--'): end += 1
    return argv[start:end]


def number(value):
    return {'Y':1,'N':0}.get(value, int(value, 0) if value not in ('Y','N') else 0)











































































def source_auth(archive, manifest, expected, extra_review, label):
    need(set(expected) <= set(manifest), label+': tracked source files missing from capture')
    for path, digest in expected.items():
        need(manifest[path] == digest, label+': tracked Git blob differs: '+path)
    extras = set(manifest)-set(expected)
    reviewed = extra_review.get(label, {})
    need(extras == set(reviewed), label+': stale extra-source set lacks exact review: '+repr(sorted(extras)))
    for name in sorted(extras):
        row = reviewed[name]
        need(row.get('sha256') == manifest[name] and row.get('reviewed') is True and
             row.get('classification') == 'not-built-or-imported' and row.get('reason') and row.get('proofs'),
             'extra source lacks explicit reachability review: '+name)
        for proof in row['proofs']:
            need(archive.hashes.get(safe(proof['path'])) == proof['sha256'], 'extra-source proof hash: '+name)
    return dict(tracked_blobs=len(expected), reviewed_extras=reviewed,
                identity_scope='tracked Git blob authentication plus explicit extra-file review; no blanket checkout identity')


def campaign(label, archive, control_dir, host_after_path, commit, git, oracle, fault, extra_review, arms=None):
    controls, host_before, control_sha = load_control(control_dir, archive, commit)
    owner = archive.json('owner.json')
    arms = list(arms) if arms is not None else (['kdlock'] if label == 'baseline' else ['native','tclock','kdlock'])
    need(arms in (['kdlock'], ['native','tclock','kdlock']), 'unsupported archive arm list')
    need(owner['boot_id'] == controls['boot_id'] and owner['provider_mutex_policy'] == POLICY,
         'launcher identity/policy differs')
    need(owner['source_sha256'] == sha(git.blob(commit, 'bench/nano/best_case.py')), 'launcher bytes not selected commit')
    blocks = owner['blocks']
    need([b['profile'] for b in blocks] == list(PROFILES), 'ten exact ordered profile blocks required')
    need(all(b['returncode'] == 0 and b['completion_unconfirmed'] is False and b['started'] <= b['finished']
             for b in blocks), 'profile incomplete/failed')
    need(all(a['finished'] <= b['started'] for a,b in zip(blocks,blocks[1:])), 'overlapping profile blocks')
    need(controls['started'] <= blocks[0]['started'] <= blocks[-1]['finished'] <= controls['finished'],
         'outer/profile intervals differ')
    before_id, before_time, before_extra = host_identity(host_before)
    after = local_json(host_after_path); after_id, after_time, after_extra = host_identity(after)
    if commit in MODERN_CONTROLLERS:
        need(file_sha(host_after_path) == file_sha(control_dir/'host-after.json'), 'selected current endpoint differs')
    need(before_id == after_id, 'host endpoint fixed configuration differs')
    need(0 <= controls['started']-before_time <= 300 and 0 <= after_time-controls['finished'] <= 300,
         'host endpoints are not fresh around campaign')
    expected_source = git.source_hashes(commit)
    frozen = archive.json('source-sha256.json')
    source = source_auth(archive, frozen, expected_source, extra_review, label)
    rows, identity, bundle_sha = {}, None, None
    need(archive.json('commands.json') == [[b['profile'],b['argv']] for b in blocks], 'command plan/owner mismatch')
    for block in blocks:
        profile = block['profile']; family, lines, percent = PROFILES[profile]
        argv = block['argv']
        for name, values in {'--backends':arms, '--threads':list(map(str, THREADS)), '--cpus':list(map(str,range(60))),
            '--lock-kind':[family], '--cachelines':[str(lines)], '--write-percent':[str(percent)],
            '--repeats':['1'], '--duration-ms':['2000'], '--post-work-rounds':['256'], '--delegate':['on'],
            '--collector-cpu':['63'], '--mutex-batch-limit':['1024'], '--mutex-numa-boundary':['1024'],
            '--kernel-source':[BUILD], '--kernel-baseline':[BUNDLE], '--workloads':['cacheline'],
            '--output':[archive.meta['guest_base']+'/'+profile]}.items():
            need(options(argv,name) == values, profile+': command differs '+name)
        need(not any(x in argv for x in ('--functional','--require-parity','--require-jit')), 'changed scoring mode')
        if '--kernel-variant' in argv: need(options(argv,'--kernel-variant') == ['kdlock1'], 'kernel variant differs')
        local_sources = archive.json(profile+'/source-sha256.json')
        need(local_sources == frozen, 'source changes between profile snapshots')
        for name, digest in frozen.items():
            need(archive.hashes.get(profile+'/source/'+safe(name)) == digest, 'retained source bytes: '+name)
        env = archive.json(profile+'/environment.json'); kid = env['kernel_identity']
        need(kid.get('ok') is True and kid.get('schema') == 2 and kid.get('config') is True and
             kid.get('runtime_policy_verified') is True and kid.get('running_build_id') and
             kid['source'] == BUILD and kid['baseline'] == BUNDLE, 'kernel identity not fully verified')
        need(env['boot_policy']['boot_id'] == owner['boot_id'] and
             env['uname'][2] == '7.0.0-38-kdlock1', 'profile boot/release differs')
        need(env['packages'] == dict(miasm='0.1.5',future='1.0.0',pyparsing='2.4.7',pyelftools='0.27') and
             env['python'] == '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3' and
             env['snapshot_tag'] == 'kdlock-builddisk-clean-20261031', 'translation environment differs')
        if identity is None: identity = kid
        need(identity == kid, 'kernel identity changes within campaign')
        manifest_path = profile+'/kernel-baseline/manifest.json'
        manifest = archive.json(manifest_path)
        need(manifest['schema'] == 2 and manifest['running']['release'] == '7.0.0-38-kdlock1' and
             manifest['running']['build_id'] == kid['running_build_id'], 'captured kernel bundle differs')
        for name,digest in manifest['bundle_files'].items():
            need(archive.hashes.get(profile+'/kernel-baseline/'+safe(name)) == digest, 'kernel bundle hash: '+name)
        if bundle_sha is None: bundle_sha = archive.hashes[manifest_path]
        need(bundle_sha == archive.hashes[manifest_path], 'bundle changes within campaign')
        topology = env['topology']; nodes = dict(zip(topology['role_cpus'],topology['role_nodes']))
        need(topology['online_cpus'] == list(range(64)) and all(nodes.get(n) == n//32 for n in range(60)) and
             nodes.get(63) == 1, 'guest 32/32 topology differs')
        binary_map = archive.json(profile+'/binary-sha256.json')
        for absolute,digest in binary_map.items():
            relative = archive.relative(absolute)
            need(archive.hashes.get(relative) == digest, 'binary digest differs: '+absolute)
            if relative.endswith('.ko'):
                vermagic = archive.modinfo[relative].get('vermagic', [])
                need(len(vermagic) == 1 and vermagic[0].startswith('7.0.0-38-kdlock1 '), 'module vermagic differs')
        providers = [archive.relative(p) for p in binary_map if p.endswith('/kdlock_km.ko')]
        need(len(providers) == 1, 'one provider ELF required')
        for field,value in dict(spin_numa='1',spin_batch='1024',mutex_batch='1024',
                                mutex_numa_boundary='1024',mutex_batch_diag='0').items():
            need(archive.modinfo[providers[0]].get(field) == [value], 'compiled provider policy: '+field)
        build = archive.json(profile+'/build-kdlock.log.command.json')['argv']
        need({'KDLOCK_SELFTEST=0','KDLOCK_NUMA=1','KDLOCK_SPIN_BATCH=1024','KDLOCK_MUTEX_BATCH=1024',
              'KDLOCK_MUTEX_NUMA_BOUNDARY=1024','KDLOCK_MUTEX_DIAGNOSTICS=0','UBSAN_SANITIZE=n',
              'KDIR='+BUILD} <= set(build), 'provider build policy differs')
        plan = archive.json(profile+'/plan.json')
        need(len(plan) == 21*len(arms) and len({s['name'] for s in plan}) == len(plan), 'profile plan coverage')
        guest_profile = archive.meta['guest_base']+'/'+profile
        expected_binaries = {guest_profile+'/build/guard/tc_allocator_guard.ko',
                             guest_profile+'/build/provider/kernel_module/kdlock_km.ko',
                             guest_profile+'/source/daemon/daemon'}
        expected_binaries.update(guest_profile+'/build/'+safe(s['variant'])+'/rwlock_bench.ko' for s in plan)
        if 'tclock' in arms:
            tc_binary = guest_profile+'/build/tclock/tclock_'+family+'_backend_km.ko'
            expected_binaries.add(tc_binary)
            need(archive.modinfo[archive.relative(tc_binary)].get(family+'_numa') == ['1'], 'TCLock NUMA build differs')
        need(set(binary_map) == expected_binaries, 'provider/daemon/guard/workload binary set differs')
        for variant in {s['variant'] for s in plan}:
            sample = next(s for s in plan if s['variant'] == variant)
            args = archive.json(profile+'/build-'+variant+'.log.command.json')['argv']
            expected_flags = {'KDIR='+BUILD,'RB_BACKEND='+sample['arm'],'RB_WORKLOAD=cacheline',
                'RB_LINES='+str(lines),'RB_LOCK_KIND='+family,'RB_POST_WORK_ROUNDS=256',
                'RB_RWSEM_DELEGATE='+str(int(family == 'rwsem' and sample['delegate'])),
                'RB_MUTEX_DELEGATE='+str(int(family == 'mutex' and sample['delegate'])),
                'KDLOCK_INCLUDE='+guest_profile+'/source/include',
                'TCLOCK_INCLUDE='+guest_profile+'/source/tclock_backend/include',
                'RB_SHARED='+guest_profile+'/source/workload_modules/spin_cacheline'}
            need(args[:3] == ['make','-C',guest_profile+'/build/'+variant], 'workload build folder differs')
            need(all(args.count(flag) == 1 for flag in expected_flags), 'workload compile flags differ')
        actual_session_names = {p for p in archive.hashes if p.startswith(profile+'/') and
                                len(PurePosixPath(p).parts) == 3 and p.endswith('/session.json')}
        need(actual_session_names == {profile+'/'+safe(s['name'])+'/session.json' for s in plan}, 'unplanned/missing session')
        for spec in plan:
            sdir = profile+'/'+safe(spec['name']); session_path = sdir+'/session.json'; s = archive.json(session_path)
            need(all(s.get(k) == v for k,v in spec.items()), sdir+': session/plan mismatch')
            need(all(type(s.get(k)) is int for k in ('cachelines','write_percent','threads','repeat',
                 'collector_cpu','iterations','duration_ms','peak_window_ms','peak_settle_ms','sample_ms',
                 'post_work_rounds','warmup_iterations_per_worker','helper_waves')), 'noninteger coordinate')
            arm,n = s['arm'],s['threads']; key = (family,lines,percent,n,arm)
            need(arm in arms and n in THREADS and key not in rows, 'unexpected/duplicate coordinate')
            need(s['lock_kind'] == family and s['cachelines'] == lines and s['write_percent'] == percent and
                 s['cpus'] == list(range(n)) and s['cpu_nodes'] == [i//32 for i in range(n)] and
                 s['repeat'] == 0 and s['duration_ms'] == 2000 and s['post_work_rounds'] == 256 and
                 s['collector_cpu'] == 63 and s['functional'] is False and s['workload'] == 'cacheline' and
                 s['helper_waves'] == 0 and s['helper_cpus'] == [] and not s['require_jit'] and
                 s['mix_policy'] == 'evenly_spaced_worker_phase17' and s['call_shell'] == 'bulk_ioctl' and
                 s['nano_layout'] == f'{lines}_aligned_counters' and s['nano_working_set_bytes'] == 64*lines and
                 s['peak_window_ms'] == s['peak_settle_ms'] == 300 and s['sample_ms'] == 10 and
                 s['warmup_iterations_per_worker'] == 48000 and s['provider_ubsan'] == 'off', 'coordinate/shell differs')
            need(s['caller_abi'] == ('clobber' if arm == 'kdlock' else 'c'), 'caller ABI differs')
            if arm == 'kdlock':
                need(s['entry_abi'] == (3 if family == 'rwlock' else 2) and s['delegate'] is True and
                     s['provider_mutex_policy'] == POLICY and s['delegation_batch_limit'] == 1024, 'KD policy/ABI')
            need(s['execution_status'] == 'OK' and s['drained'] is True, sdir+': incomplete/undrained')
            workload_binary = guest_profile+'/build/'+s['variant']+'/rwlock_bench.ko'
            need(archive.json(sdir+'/load-source.log.command.json')['argv'] == ['insmod',workload_binary],
                 'session did not load its exact hashed workload ELF')
            need(archive.json(sdir+'/load-allocator-guard.log.command.json')['argv'] ==
                 ['insmod',guest_profile+'/build/guard/tc_allocator_guard.ko'], 'allocator guard binary differs')
            if arm == 'kdlock':
                loaded = archive.json(sdir+'/load-kdlock.log.command.json')['argv']
                need(loaded == ['insmod',guest_profile+'/build/provider/kernel_module/kdlock_km.ko',
                    'bench_quiet=1','bench_complete_probe=1','jit_timing=0','hotlock_stats=1',
                    'target_process=rb_worker','spin_prefetch=2','spin_entry_ratio_limit=2','spin_delegate=1'],
                     'provider load binary/observations differ')
            elif arm == 'tclock':
                need(archive.json(sdir+'/load-tclock.log.command.json')['argv'] ==
                     ['insmod',guest_profile+'/build/tclock/tclock_'+family+'_backend_km.ko','komb_batch_size=1024'],
                     'TCLock loaded binary/batch differs')
            initial = archive.json(sdir+'/initial.counts.json')
            need(initial == s['layout'] and initial['values'] == [0]*16, 'initial layout/counts differ')
            previous = initial
            for phase in ('warmup','measure'):
                ps = archive.json(sdir+'/'+phase+'.spec.json'); raw = archive.json(sdir+'/'+phase+'.json')
                expected = dict(spec)
                if phase == 'warmup': expected.update(iterations=48000,duration_ms=0)
                need(all(ps.get(k) == v for k,v in expected.items()), phase+': raw spec differs')
                need(raw.get('data_ok') is True and raw.get('complete') is True and raw['before'] == previous,
                     phase+': chain/data completion differs')
                peak = oracle.validate(raw, ps)
                after_counts = archive.json(sdir+'/'+phase+'.counts.json')
                need(after_counts == raw['after'], phase+': explicit counts differ')
                previous = raw['after']
                if phase == 'measure':
                    derived = dict(raw, peak=peak)
                    need(s['measurement'] == derived, 'stored measurement/peak differs from raw oracle')
                    measurement = raw
            need(archive.json(sdir+'/drain.counts.json') == previous, 'final drain counts changed')
            need(not fault.search(archive.text(sdir+'/kernel.log')), 'retained kernel fault: '+sdir)
            need(archive.json(sdir+'/unload-source.log.command.json')['argv'] == ['rmmod','rwlock_bench'],
                 'ordinary source unload absent')
            m = measurement; bodies, completed = s['jit_bodies'],s['jit_completions']
            need(all(type(s.get(k)) is int for k in ('jit_before','jit_after','jit_bodies','jit_complete_before',
                 'jit_complete_after','jit_completions')), 'noninteger JIT counters')
            evidence = oracle.jit_evidence(s['jit_before'],s['jit_after'],m['writes'],backend=arm,
                delegate=s['delegate'],operation='writer',completed=s['jit_complete_after']-s['jit_complete_before'])
            need(all(s.get(k) == v for k,v in evidence.items()), 'JIT measured accounting differs')
            if arm == 'kdlock':
                need(s['retired'] == RETIRED and s['published_before'] == s['published_after'], 'KD retirement/publication')
                pub = s['published_before']; entry = pub['entry']
                need(pub['source'] == dict(state=0,modules=1,frames=0,writers=0) and
                     entry['status'] == 0 and entry['pid'] == 0 and entry['code'] and
                     entry['entry'] == initial['entry'] and entry['entry_abi'] == s['entry_abi'] and
                     entry['lock_kind'] == (1 if family == 'rwlock' else 2), 'KD exact publication identity')
                for name,digest in pub['images'].items():
                    path = f"{sdir}/workspace/daemon/{hex(entry['entry'])}/{entry['tgid']}/asm/{safe(name)}"
                    need(archive.hashes.get(path) == digest, 'published image bytes differ')
                params = s['parameters']
                for name,value in dict(bench_lock_addr=initial['gate_addr'],bench_quiet=1,bench_complete_probe=1,
                    jit_timing=0,hotlock_stats=1,spin_prefetch=2,spin_delegate=1,spin_entry_ratio_limit=2).items():
                    need(number(params[name]) == value, 'KD observation parameter differs: '+name)
                need(params['target_process'] == 'rb_worker' and params.get('api_bind','N') == 'N', 'KD target/API mode')
                if commit in MODERN_CONTROLLERS:
                    need(number(params['origin_instruction_force_suffix']) == 0, 'origin suffix forcing enabled')
                for name,value in params.items():
                    if ('fail' in name or 'fault' in name) and name not in ('invariant_failures',):
                        need(number(value) == 0, 'fault injection enabled: '+name)
                need(s['address_guard_exits'] in (None,0), 'address guard exited')
                need(archive.json(sdir+'/unload-kdlock.log.command.json')['argv'] == ['rmmod','kdlock_km'],
                     'ordinary provider unload absent')
            else:
                need(bodies == completed == 0 and not s.get('retired'), 'non-KD body/retirement invented')
            if arm == 'tclock':
                for name in ('parameters','tclock_before','tclock_after','tclock_drained'):
                    state = s[name]
                    need(state['quiescent'] == 1 and state['target_lock'] == initial['lock_addr'] and
                         state['komb_batch_size'] == 1024, 'TCLock binding/quiescence')
                need(s['tclock_delegation_status'] == 'UNMEASURED', 'TCLock evidence classification differs')
                need(archive.json(sdir+'/unload-tclock.log.command.json')['argv'] ==
                     ['rmmod','tclock_'+family+'_backend_km'], 'ordinary TCLock unload absent')
            execution = ('RETURNED_JIT' if completed else 'PARTIAL_JIT' if bodies else 'NO_JIT') if arm == 'kdlock' else 'NATIVE'
            rows[key] = dict(profile=profile,lock_kind=family,workload=f'c{lines:02d}',cachelines=lines,
                write_percent=percent,threads=n,arm=arm,repeat=0,execution_class=execution,
                score_eligible=execution != 'PARTIAL_JIT',jit_entries=bodies,jit_completions=completed,
                jit_entry_share=s['jit_writer_share'],jit_completion_share=s['jit_complete_share'],
                completed=m['completed'],reads=m['reads'],writes=m['writes'],wall_ns=m['wall_ns'],
                whole_ops_s=m['completed']*1e9/m['wall_ns'],peak_ops_s=s['measurement']['peak']['throughput_ops_s'],
                whole_numerator=m['completed'],whole_denominator_ns=m['wall_ns'],
                peak_numerator=s['measurement']['peak']['completed'],peak_denominator_ns=s['measurement']['peak']['elapsed_ns'],
                session= session_path,session_sha256=archive.hashes[session_path],
                raw_measure_sha256=archive.hashes[sdir+'/measure.json'],raw_warmup_sha256=archive.hashes[sdir+'/warmup.json'],
                provider_sha256=archive.hashes[providers[0]],
                workload_binary_sha256=archive.hashes[archive.relative(workload_binary)],
                daemon_sha256=archive.hashes[profile+'/source/daemon/daemon'],
                source_commit=commit,published=s.get('published_before') if arm == 'kdlock' else None,
                api_bind=s.get('parameters',{}).get('api_bind','ABSENT'),
                matched_fields={k:s.get(k) for k in MATCH},validated=True,performance_accepted=False)
    expected_keys = {(f,l,w,n,a) for f,l,w in PROFILES.values() for n in THREADS for a in arms}
    need(set(rows) == expected_keys, 'full campaign coordinate set differs')
    return dict(label=label,commit=commit,boot_id=owner['boot_id'],rows=rows,source=source,
        kernel_identity=identity,kernel_bundle_sha256=bundle_sha,host_fixed_identity=before_id,
        host_endpoints=dict(before_sha256=file_sha(control_dir/'host-before.json'),after_sha256=file_sha(host_after_path),
                            before_auxiliary_workers=before_extra,after_auxiliary_workers=after_extra),
        controller_sha256=control_sha,started=controls['started'],finished=controls['finished'],
        offline_prerequisites=controls.get('offline_prerequisites'), archive=archive.provenance)


# Fresh cohort controls are deliberately separate from historical receipt schemas.
from fresh_controls import load_control, host_identity
