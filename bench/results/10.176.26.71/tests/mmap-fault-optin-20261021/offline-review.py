#!/usr/bin/env python3
"""Inert source-host review: archives, Git inputs, ELF modes and exact receipts.

Imports only the hash-pinned maintained archive checker. No retained workload,
runner, build output or test is executed. Writes this review's JSON receipt.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tarfile
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RAW = ROOT/'bench/results/10.176.26.71/raw/tests/mmap-fault-optin-20261021/archives'
HELPER = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
spec = importlib.util.spec_from_file_location('inert_archive_review', HELPER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
a = m.Audit(SimpleNamespace(repo=ROOT, raw=RAW, report=HERE))
groups, links = a.load_archives()
sources, binaries = a.manifests()


def data(name):
    if name in a.contents:
        return a.contents[name]
    with tarfile.open(RAW/a.members[name]['archive']) as archive:
        return archive.extractfile(a.prefix+name).read()


def jsonl(name):
    return [json.loads(line) for line in data(name).splitlines()]


def elf_mode(name):
    raw = data(name)
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    a.check(header[0][:6] == b'\x7fELF\x02\x01' and header[1:3] == (1, 62), 'payload_elf64_x86', name)
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, header[6]+i*header[11]) for i in range(header[12])]
    def section(index):
        s = sections[index]
        return raw[s[4]:s[4]+s[5]]
    def string(buf, offset):
        return buf[offset:buf.index(b'\0', offset)].decode()
    names = [string(section(header[13]), s[0]) for s in sections]
    metadata = section(names.index('.modinfo')).split(b'\0')
    symindex = next(i for i, s in enumerate(sections) if s[1] == 2)
    table, strings = section(symindex), section(sections[symindex][6])
    undefined = set()
    for offset in range(0, len(table), sections[symindex][9]):
        symbol = struct.unpack_from('<IBBHQQ', table, offset)
        if symbol[0] and symbol[3] == 0:
            undefined.add(string(strings, symbol[0]))
    mode = next(x.split(b'=', 1)[1].decode() for x in metadata if x.startswith(b'mmap_provider='))
    return mode, undefined


retired = dict(state=2, modules=0, writers=0, frames=0)
versions = ['581ff9c', '7077fcf', '6afa68f', '21451da', '21451da']
cases, attempts = [], []
for index, version in enumerate(versions, 1):
    name = 'live-' + str(index)
    prefix = name + '/'
    result = a.jread(prefix+'result.json')
    source = a.jread(prefix+'source-sha256.json')
    manifest = a.jread(prefix+'committed-source.json')
    revision = a.revision(version)
    a.check(result['source_commit'] == manifest['commit'] == revision, 'attempt_source_revision', name)
    a.check(a.files[prefix+'committed-source.json'] == result['source_manifest_sha256'], 'commit_manifest_receipt', name)
    a.check(len(source) == result['source_files'], 'source_count', name)
    for path, digest in source.items():
        a.check(manifest['files'][path] == digest == m.sha(a.git_bytes(revision, path)), 'source_git_bytes', name+'/'+path)
    a.check(a.files[prefix+'source/tests/kernel/mmap_fault/run.py'] == result['script_sha256'], 'runner_identity', name)
    a.check(result['accepted'] is False and not result['kernel_modified'] and not result['production_protocol_changed'], 'scope_limits', name)
    identity = result['kernel_identity']
    a.check(identity['ok'] and identity['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            result['boot_id'] == 'b65f0205-c8f9-4385-8b13-039cbce243a6', 'same_kernel_identity', name)
    if prefix+'kernel.log' in a.files:
        log = data(prefix+'kernel.log').decode()
        faults = re.findall(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|unable to handle|general protection fault|Oops:|\[ERROR\]|\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]', log, re.I)
        a.check(not faults, 'retained_kernel_fault_scan', (name,faults))
        if index > 3:
            a.check('unknown parameter' not in log and 'percpu: allocation failed' not in log, 'successful_module_preparation', name)
    if prefix+'prepared-source-sha256.json' in a.files:
        original = prefix+'source/'
        prepared = a.jread(prefix+'prepared-source-sha256.json')
        changed = a.reconstruct(original, data(original+'bench/spin_cacheline/provider/observation.patch'))
        for path, digest in prepared.items():
            if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
                content = data(original+'bench/spin_cacheline/provider/'+Path(path).name)
            elif path in changed:
                content = changed[path]
            else:
                content = data(original+path)
            a.check(m.sha(content) == digest, 'prepared_reconstructed_bytes', name+'/'+path)
        a.check(set(changed) <= set(prepared), 'all_patch_targets_retained', name)
    if index < 4:
        a.check(result['state'] == 'FAILED' and not result['passed'] and not result['cases'], 'failed_attempt_not_pass', name)
        if index > 1:
            cleanup = a.jread(prefix+'cleanup.json')
            a.check(cleanup['idle'] and cleanup['retired'] == retired, 'failed_attempt_normal_cleanup', name)
            a.check('percpu: allocation failed' in data(prefix+'kernel.log').decode(), 'allocation_failure_preserved', name)
        else:
            a.check("No rule to make target '../../daemon/daemon.c'" in data(prefix+'basic.log').decode(), 'missing_dependency_preserved')
    else:
        a.check(result['state'] == 'COMPLETE' and result['passed'] and result['drained'] and
                result['final_idle'] and result['source_unchanged'], 'successful_run_drain', name)
        a.check(result['binaries'] == a.jread(prefix+'binary-sha256.json') and result['basic_programs'] == 2, 'success_build_receipts', name)
        mode, imports = elf_mode(prefix+'source/workload_modules/mmap_fault/kd_mmap_fault.ko')
        expected = 'kdlock' if index == 4 else 'tclock'
        a.check(mode == expected == result['provider'] == data(prefix+'payload-mode.txt').decode().strip(), 'payload_mode_binding', name)
        listed = {line.split()[-1] for line in data(prefix+'payload-imports.txt').decode().splitlines() if line.strip()}
        a.check(imports == listed, 'actual_elf_imports_match_listing', name)
        a.check(('kd_down_read' in imports) == (index == 4) and ('komb_read_lock' in imports) == (index == 5) and
                not any(n.startswith('komb_') if index == 4 else n.startswith('kd_') for n in imports), 'single_provider_imports', name)
        if index == 4:
            a.check(result['retired'] == retired == a.jread(prefix+'retire.json') and result['jit_counts_observed'] and
                    result['jit_bodies'] == result['jit_completions'] == 0, 'kd_exact_retirement_zero_jit')
            params = a.jread(prefix+'provider-parameters.json')
            a.check(params['bench_quiet'] == params['bench_complete_probe'] == 'Y' and params['jit_timing'] == 'N', 'kd_observation_enabled')
        else:
            a.check(result['tclock_quiescent'] and result['retired'] is None and
                    not result['jit_counts_observed'] and result['jit_bodies'] is result['jit_completions'] is None, 'tc_quiescence_no_invented_jit')
            a.check(result['native_kd_prerequisite']['sha256'] == a.files['live-4/result.json'], 'tc_prerequisite_receipt')
        a.check([c['backend'] for c in result['cases']] == ([0, 1] if index == 4 else [2]), 'case_order', name)
        for case in result['cases']:
            backend = case['backend']
            rows = jsonl(prefix+f'client-{backend}.jsonl')
            a.check(rows[-1] == dict(event='complete', passed=True, backend=backend, checks=100 if backend == 2 else 96), 'client_complete_oracle', backend)
            probes = [r for r in rows if r['event'] == 'probe']
            expected = [(0,1,1,1,1,0,0,0,0,0),(0,2,2,2,2,1,0,0,1,0),
                        (-11,1,1,1,1,0,1,0,0,0),(0,1,1,1,1,0,0,1,0,0),(-116,1,2,2,1,1,0,0,0,1)]
            fields = ('result','attempts','acquisitions','releases','callbacks','retries','nowait','completed','revalidated','stale')
            a.check(probes == case['probes'] and [p['action'] for p in probes] == list(range(5)), 'probe_sequence', backend)
            for p, values in zip(probes, expected):
                a.check(tuple(p[k] for k in fields) == values and p['pause_timeout'] == p['final_held'] == 0, 'exact_fault_ownership', (backend,p['action']))
            denied = [r for r in rows if r['event'] == 'rejected_mode']
            a.check(denied == [case['rejected_mode']] == [dict(event='rejected_mode',action=0,result=-116,
                attempts=0,acquisitions=1,releases=1,callbacks=0,retries=0,nowait=0,completed=0,
                revalidated=0,stale=1,pause_timeout=0,final_held=0)], 'read_permission_rejection', backend)
            joined = dict(event='joined',backend=backend,faults=408,epoch=1000+(backend!=2),
                reads=408+(backend!=2),read_ends=408+(backend!=2),writes=1012+(backend!=2),
                write_ends=1012+(backend!=2),scopes=6,scope_ends=6,downgrades=int(backend!=2),vmas=0,errors=0)
            a.check([r for r in rows if r['event'] == 'joined'] == [case['joined']] == [joined], 'joined_exact_pairs', backend)
            created = [r for r in rows if r['event'] == 'create']
            a.check(created == case['created'] and [r['requested'] for r in created] == [backend]*len(created) and
                    [r['selected'] for r in created] == [backend,0,backend]+([0] if backend==2 else []) and
                    [r['fallback'] for r in created] == [0,int(backend!=0),0]+([1] if backend==2 else []), 'explicit_fallback', backend)
            a.check(case['health'] == f'files=0 destroyed={3 if backend==0 else 6 if backend==1 else 4} release_errors=0', 'file_storage_retired', backend)
            cases.append(dict(run=name,backend=backend,checks=case['checks'],joined=joined,health=case['health']))
    if index > 1:
        a.check('Unit tests: 2 passed, 0 failed' in data(prefix+'basic.log').decode(), 'two_basic_programs', name)
    attempts.append(dict(run=name,source_commit=revision,state=result['state'],passed=result['passed']))

health = a.jread('final-health.json')
a.check(health['idle'] and not health['per_session_kernel_faults'] and health['accepted'] is False, 'final_health')
a.check(health['verified_hashes'] == sum(r['entries'] for r in sources)+len(binaries), 'health_hash_count')
a.check(health['source_sha256'] == a.files['capture-health.py'], 'health_script_identity')
hosts=[]
reference=a.jread('control/host-before-1.json')
for name in sorted(p for p in a.files if p.startswith('control/host-') and p.endswith('.json')):
    host=a.jread(name)
    a.check(host['pins_verified'] and host['snapshot_listed'] and len(host['qemu'])==1 and
            host['qemu'][0]['pid']==257489 and host['qemu'][0]['args']==reference['qemu'][0]['args'] and
            host['numa']==reference['numa'] and host['cpufreq']==reference['cpufreq'], 'same_host_configuration', name)
    hosts.append(dict(receipt=name,captured_utc=host['captured_utc'],qemu_threads=len(host['qemu'][0]['tasks'])))
receipt=dict(consistent=not a.issues,issues=a.issues,checks=sum(a.counts.values()),check_counts=dict(a.counts),
    groups=groups,members=len(a.members),files=len(a.files),symlinks=len(links),sources=sources,
    binary_entries=len(binaries),attempts=attempts,cases=cases,hosts=hosts,
    archive_manifest_sha256=m.hashfile(RAW/'archives.json'),file_hash_map_sha256=m.canonical(a.files),
    script_sha256=m.hashfile(Path(__file__)),helper_sha256=m.hashfile(HELPER),accepted=False,
    timing='NOT_RUN; no variance or performance acceptance established')
(HERE/'offline-review.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(consistent=receipt['consistent'],checks=receipt['checks'],issues=a.issues,
                     members=receipt['members'],files=receipt['files'],binary_entries=len(binaries))))
raise SystemExit(bool(a.issues))
