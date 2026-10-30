#!/usr/bin/env python3
"""Offline f7 original-body API comparison; never starts guest work."""
import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tarfile
from types import SimpleNamespace

COMMIT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
RECIPE = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
REMOTE = '/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-api-f7a84065-20261030'
FIXED = {
    'controller.py': '35495b774fd74872cd204140ef76fe4cdcc34b2235cbac051d05999c9101bf6c',
    'source-state.json': '52448d33d2ed7c781b0bea4cd1ac4ab80b59107a42622a4fc8a0fd9d857fd520',
    'source-sha256.json': 'f093746333abdc7e3ca647852b43b611d6a0a494e7922b9c285125dd46c00db3',
    'generation-record.json': '4618cd0df915928562e94569662a3771483a86cdc26f4762f276190d8ee88567',
    'host-reference.json': '95199f8417b1eb8a0e7a406fa1143dec17090aa0973c6db3d0ae828e401ed588',
}
EXPECTED_BOOT = '2e0ea0fa-ff34-4416-9175-b4b0ede3f63b'
EXPECTED_BUILD_ID = 'a17d565ee157601e030d1b3c77c13e63fa62c994'
FUNCTIONAL_RESULT_SHA = 'e763bedada5dc3c88428ed96e46732edc537b618e30a6bde5d470dd5874f5f97'
RUNNER_SHA = 'fd83caf3d7f6062bb87645a5ce118c7ec2600b61f78a44a6a0780caf0d96e73e'
CLIENT_SHA = '287c277614603437961a15b6c9dc343ddf82ccb70126b29bc5d083039c062c45'
WORKERS = tuple(range(1, 9)) + tuple(range(12, 61, 4))
CASES = {'setfd': ('toggle', 1, 1), 'pipebytes': ('query', 16, 2), 'pipecap': ('query', 16, 3)}
RETIRE = dict(state=2, modules=0, frames=0, writers=0)
PARAMETERS = dict(api_bind='Y', bench_quiet='Y', bench_complete_probe='N',
                  bench_lock_addr='0', jit_timing='N', hotlock_stats='N',
                  target_process='sc_worker', origin_instruction_force_suffix='N',
                  jit_fail_pending_lock='0', jit_hl_fault_after_known_call='0',
                  mutex_task_fail_once='0', spin_jit_fail_after_nested_lock='0')
COMPARE_PARAMETERS = tuple(PARAMETERS) + ('spin_delegate', 'spin_entry_ratio_limit', 'spin_prefetch')
PHASES = ('basic', 'objects', 'functional', 'measure')
ARCHIVE_HELPER = '/tmp/kdlock-nano-f7a84065-analysis-prep-20261030/nano_core.py'
ARCHIVE_HELPER_SHA = '1bbd6e010c27c42f5293a3df09660342e453d49663d9452e3c1d02269116c3a7'
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def expected_plan(functional=False):
    return [dict(name=f'{kind}-{arm}-n{n:02d}-r00', kind=kind, arm=arm,
                 cpus=list(range(n)), workers=n, round=0, collector_cpu=63,
                 duration_ms=2000, query=CASES[kind][0], entries=CASES[kind][1],
                 site=CASES[kind][2], instrumentation='completion' if functional else 'none')
            for kind in CASES for n in ((16,) if functional else WORKERS)
            for arm in ('native', 'kd')]


def pure_functions(raw, names):
    """Reuse only named pure validators; never import a guest runner module."""
    tree = ast.parse(raw)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    require({node.name for node in selected} == set(names), 'pure validation functions missing')
    namespace = dict(rt=SimpleNamespace(require=require), require=require,
                     WORKERS=WORKERS, CASES=CASES, RETIRE=RETIRE)
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<retained-pure-validators>', 'exec'), namespace)
    return namespace


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--campaign', type=Path)
    source.add_argument('--archives', type=Path)
    ap.add_argument('--archive-helper', type=Path, default=Path(ARCHIVE_HELPER))
    ap.add_argument('--owner-hashes', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    source_root, out = (args.campaign or args.archives).resolve(), args.output.resolve()
    require(source_root.is_dir() and not out.exists() and not out.is_relative_to(source_root), 'existing input/new external output required')
    out.mkdir(parents=True, exist_ok=False)
    root = args.campaign.resolve() if args.campaign else Path('/offline-api-campaign')
    identity_issues, completion_issues, inputs = [], [], {}
    archive, selected_bytes = None, {}
    if args.archives:
        helper = args.archive_helper.resolve()
        require(hashlib.sha256(helper.read_bytes()).hexdigest() == ARCHIVE_HELPER_SHA, 'reviewed archive helper differs')
        inputs[str(helper)] = ARCHIVE_HELPER_SHA
        spec = importlib.util.spec_from_file_location('api_offline_archive_data', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cache = out/'archive-cache'; cache.mkdir()
        archive = module.Archive(source_root, cache)
        require(archive.meta['guest_base'] == REMOTE, 'archive belongs to a different campaign')
        # Only these two source files need bytes; all other source/ELF/image
        # identity checks use the already-computed complete member hash map.
        wanted = {'functional/source/bench/kernel_api/run.py', 'measure-control/controller.py'}
        prefix = archive.meta['archive_prefix']+'/'
        for group in archive.meta['groups']:
            with tarfile.open(source_root/group['file'], 'r|gz') as stream:
                for item in stream:
                    name = item.name.removeprefix(prefix)
                    if name in wanted:
                        require(item.isfile(), 'validator source is not regular')
                        data = stream.extractfile(item).read()
                        require(hashlib.sha256(data).hexdigest() == archive.hashes[name], 'validator bytes differ')
                        selected_bytes[name] = data
        for name in ('archives.json', 'input-inventory.json'):
            inputs[str(source_root/name)] = hashlib.sha256((source_root/name).read_bytes()).hexdigest()
        (out/'archive-provenance.json').write_text(json.dumps(archive.provenance,indent=2)+'\n')
        (out/'member-sha256.json').write_text(json.dumps(archive.hashes,indent=2,sort_keys=True)+'\n')

    def check(value, message, issues=identity_issues):
        if not value:
            issues.append(message)
        return bool(value)

    def exists(path):
        return str(path.relative_to(root)) in archive.hashes if archive and path.is_relative_to(root) else path.exists()

    def raw(path, issues=identity_issues, expected=None, content=False):
        try:
            if archive and path.is_relative_to(root):
                name = str(path.relative_to(root))
                require(name in archive.hashes, 'missing archive member')
                digest = archive.hashes[name]
                inputs[str(path)] = digest
                if expected is not None: check(digest == expected, 'hash differs: '+name, issues)
                if not content: return b''
                if name in selected_bytes: return selected_bytes[name]
                require(name in archive.saved, 'requested content not cached: '+name)
                return archive.saved[name].read_bytes()
            require(path.is_file() and not path.is_symlink(), 'missing or symbolic file')
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            inputs[str(path)] = digest
            if expected is not None:
                check(digest == expected, 'hash differs: '+str(path), issues)
            return data
        except (OSError, ValueError) as error:
            issues.append(str(path)+': '+str(error))
            return None

    def load(path, issues=identity_issues, expected=None, default=None):
        data = raw(path, issues, expected, content=True)
        if data is None:
            return {} if default is None else default
        try:
            return json.loads(data)
        except (ValueError, UnicodeError) as error:
            issues.append(str(path)+': '+str(error))
            return {} if default is None else default

    def mapped(name):
        p = Path(name)
        require('..' not in p.parts, 'noncanonical recorded path')
        if p.is_relative_to(REMOTE):
            return root/p.relative_to(REMOTE)
        if p.is_relative_to('/root/host_fs/kdlock'):
            return root/'functional/source'/p.relative_to('/root/host_fs/kdlock')
        raise ValueError('unmapped recorded input: '+name)

    def guarded(label, fn, issues=identity_issues):
        try:
            return fn()
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as error:
            issues.append(label+': '+repr(error))
            return None

    owner_hashes = load(args.owner_hashes)
    check(isinstance(owner_hashes, dict) and set(owner_hashes) == set(PHASES), 'four exact owner hashes required')
    owners, results, full_sources = {}, {}, {}
    for phase in PHASES:
        control = root/(phase+'-control')
        expected = owner_hashes.get(phase) if isinstance(owner_hashes, dict) else None
        check(bool(re.fullmatch('[0-9a-f]{64}', expected or '')), phase+': invalid owner hash')
        owner = load(control/'owner.json', expected=expected)
        owners[phase] = owner
        result = load(root/phase/'result.json', expected=owner.get('result_sha256'))
        results[phase] = result
        check(owner.get('source_commit') == COMMIT and owner.get('kernel_project_commit') == RECIPE and
              owner.get('generation_record_sha256') == FIXED['generation-record.json'], phase+': source generation differs')
        check(owner.get('phase') == phase and owner.get('output') == REMOTE+'/'+phase and
              owner.get('release') == '7.0.0-38-kdscope1', phase+': owner identity differs')
        check(owner.get('state') == 'COMPLETE' and owner.get('completed') is True and
              owner.get('final_idle') is True and owner.get('completion_checks_passed') is True and
              owner.get('drain_unknown') is False and owner.get('child_returncode') == 0,
              phase+': controller incomplete or drain unproven', completion_issues)
        copied = owner.get('inputs', {})
        for name, digest in copied.items():
            raw(control/name, expected=digest)
        for name, digest in FIXED.items():
            check(copied.get(name) == digest, phase+': fixed input differs: '+name)
        full_sources[phase] = load(control/'source-sha256.json', expected=FIXED['source-sha256.json'])
        state = load(control/'source-state.json', expected=FIXED['source-state.json'])
        check(state.get('git_head') == COMMIT and not state.get('git_status') and
              state.get('files') == len(full_sources[phase]), phase+': clean source state differs')
        check(owner.get('generation', {}).get('record_sha256') == FIXED['generation-record.json'], phase+': generation record not bound')
        for name, digest in owner.get('prerequisites', {}).items():
            guarded('prerequisite '+name, lambda n=name, h=digest: raw(mapped(n), expected=h))
    boot = owners['functional'].get('boot_id')
    check(bool(boot) and all(o.get('boot_id') == boot and r.get('boot_id') == boot
          for o, r in zip(owners.values(), results.values())), 'phase boot IDs differ')
    runner_raw = raw(root/'functional/source/bench/kernel_api/run.py', expected=RUNNER_SHA, content=True)
    raw(root/'functional/source/bench/real_api/client.c', expected=CLIENT_SHA)
    validators = None
    if runner_raw is not None and hashlib.sha256(runner_raw).hexdigest() == RUNNER_SHA:
        validators = guarded('runner validators', lambda: pure_functions(runner_raw, ('plan', 'validate_phase', 'validate_functional')))
        if validators:
            check(validators['plan']() == expected_plan() and validators['plan'](True) == expected_plan(True), 'frozen plan differs')
    controller_raw = raw(root/'measure-control/controller.py', expected=FIXED['controller.py'], content=True)
    if controller_raw is not None and hashlib.sha256(controller_raw).hexdigest() == FIXED['controller.py']:
        controls = guarded('controller validators', lambda: pure_functions(controller_raw, ('verify_basic', 'verify_phase')))
        if controls:
            for phase in PHASES:
                guarded(phase+' phase validation', lambda p=phase: controls['verify_phase'](results[p], p, boot), completion_issues)
    functional, measured = results['functional'], results['measure']
    check(boot == EXPECTED_BOOT, 'actual Native-A boot differs')
    check(inputs.get(str(root/'functional/result.json')) == FUNCTIONAL_RESULT_SHA, 'reviewed functional result differs')
    if validators:
        guarded('functional returned-body accounting', lambda: validators['validate_functional'](functional), identity_issues)
    check(functional.get('kernel_identity') == measured.get('kernel_identity') and bool(measured.get('kernel_identity')), 'functional/measure kernel identities differ')
    kernel = measured.get('kernel_identity', {})
    check(kernel.get('schema') == 2 and kernel.get('ok') is True and kernel.get('runtime_policy_verified') is True and
          kernel.get('variant') == 'kdscope1-native' and kernel.get('mmap_mode') == 'off' and
          kernel.get('running_build_id') == EXPECTED_BUILD_ID and
          kernel.get('runtime_policy', {}).get('preempt') == 'lazy', 'verified Native-MM kernel identity missing')
    binaries, environments, topologies = {}, {}, {}
    kernel_manifest_hashes = []
    for phase in ('functional', 'measure'):
        result = results[phase]
        check(result.get('schema') == 1 and result.get('action') == phase and result.get('single_round') is True, phase+': schema/action/round differs')
        check(result.get('passed') is True and result.get('drained') is True and result.get('final_idle') is True, phase+': runner incomplete', completion_issues)
        check(result.get('host', {}).get('strict_host_gate') == 'PASS' and result['host'].get('task_set_unchanged') is True and
              result['host'].get('exploratory') is False, phase+': initial strict host qualification missing')
        sources = load(root/phase/'source-sha256.json')
        check(bool(sources) and sources == result.get('source_sha256') and
              all(full_sources[phase].get(name) == digest for name, digest in sources.items()), phase+': captured source generation differs')
        for name, digest in sources.items():
            raw(root/phase/'source'/name, expected=digest)
        for name, digest in result.get('files', {}).items():
            guarded('recorded file '+name, lambda n=name, h=digest: raw(mapped(n), expected=h))
        binaries[phase] = load(root/phase/'binaries.json')
        check(set(binaries[phase]) == {'provider', 'daemon', 'client', 'guard'}, phase+': immutable binary set differs')
        for name, item in binaries[phase].items():
            check(result.get('files', {}).get(item.get('path')) == item.get('sha256'), phase+': unbound binary '+name)
            guarded('binary '+name, lambda v=item: raw(mapped(v['path']), expected=v['sha256']))
        check(owners[phase].get('provider_evidence', {}).get('binaries_sha256') == inputs.get(str(root/phase/'binaries.json')), phase+': owner binary receipt differs')
        environments[phase] = load(root/phase/'environment.json')
        topologies[phase] = load(root/phase/'topology.json')
        env = environments[phase]
        check(env.get('boot_id') == boot and env.get('cmdline') == kernel.get('runtime_policy', {}).get('cmdline') and
              env.get('preemption') == kernel.get('runtime_policy', {}).get('preempt_control'), phase+': recorded runtime policy differs')
        raw(root/phase/'host-reference.json', expected=FIXED['host-reference.json'])
        raw(root/phase/'host-before.json', expected=owners[phase].get('inputs', {}).get('host-before.json'))
        manifest = load(root/phase/'kernel-baseline/manifest.json')
        kernel_manifest_hashes.append(inputs.get(str(root/phase/'kernel-baseline/manifest.json')))
        for name, digest in manifest.get('bundle_files', {}).items():
            raw(root/phase/'kernel-baseline'/name, expected=digest)
    check(bool(kernel_manifest_hashes[0]) and kernel_manifest_hashes[0] == kernel_manifest_hashes[1], 'functional/measure original kernel bundles differ')
    expected_entries = functional.get('sessions', [{}])[0].get('binding', {}).get('entries') if functional.get('sessions') else None
    check(isinstance(expected_entries, list) and len(expected_entries) == 3 and
          all(r.get('binding',{}).get('entries') == expected_entries for r in functional.get('sessions',[])), 'functional original-body addresses differ')
    check(functional.get('source_sha256') == measured.get('source_sha256'), 'functional/measure source subsets differ')
    check(binaries['functional'] == binaries['measure'] and bool(binaries['measure']), 'functional and timing did not reuse the same binaries')
    check(topologies['functional'] == topologies['measure'] and bool(topologies['measure']), 'guest worker topology differs')
    topo = topologies['measure']
    check(topo.get('online_cpus') == list(range(64)) and topo.get('role_nodes') == [0]*32+[1]*28, '64-vCPU two-node worker topology differs')
    plan = expected_plan()
    check(load(root/'measure/plan.json', default=[]) == plan, 'retained 126-point plan differs')
    check(load(root/'functional/plan.json', default=[]) == expected_plan(True), 'retained functional plan differs')
    embedded = measured.get('sessions', [])
    if not isinstance(embedded, list):
        identity_issues.append('aggregate sessions not a list'); embedded = []
    expected_names = {s['name'] for s in plan}
    unexpected = [r for r in embedded if not isinstance(r, dict) or r.get('name') not in expected_names]
    disk_sessions = ([root/name for name in archive.hashes if re.fullmatch(r'measure/[^/]+/session\.json',name)] if archive else list((root/'measure').glob('*/session.json')))
    unexpected_paths = [str(p) for p in disk_sessions if p.parent.name not in expected_names]
    check(not unexpected and not unexpected_paths, 'unexpected or additional measured sessions')
    def audit_point(spec):
        issues = []
        path = root/'measure'/spec['name']
        entries = [r for r in embedded if isinstance(r, dict) and r.get('name') == spec['name']]
        session = load(path/'session.json', issues) if exists(path/'session.json') else {}
        if not session and not entries:
            issues.append('ABSENT: no captured session')
        elif not session:
            issues.append('aggregate session has no raw session receipt'); session = entries[0]
        check(len(entries) == 1, 'aggregate membership absent or duplicated', issues)
        if len(entries) == 1:
            check(session == entries[0], 'aggregate and raw session differ', issues)
        check(all(session.get(k) == v for k, v in spec.items()), 'point plan/settings differ', issues)
        check(session.get('passed') is True and session.get('drained') is True and session.get('execution_status') == 'COMPLETE' and
              session.get('retired') == RETIRE, 'session failed or exact retirement missing', issues)
        check(session.get('api_bind') == 'Y', 'binding disabled', issues)
        binding = session.get('binding', {})
        expected_binding_kind = 1 if spec['kind'] == 'setfd' else 2
        check(binding.get('version') == 1 and binding.get('backend') == int(spec['arm']=='kd') and
              binding.get('kind') == expected_binding_kind and bool(binding.get('object')) and bool(binding.get('lock')) and
              bool(binding.get('provider')) == (spec['arm']=='kd'), 'object/backend/lock binding differs', issues)
        ready = load(path/'ready.json', issues)
        check(ready.get('ready') is True and ready.get('pid') == session.get('client_pid') and
              ready.get('binding') == binding, 'raw initial object binding differs', issues)
        client = binaries['measure'].get('client', {}).get('path')
        command = [client, spec['kind'], spec['query'], str(spec['entries']), '64', ','.join(map(str,spec['cpus'])), '63', '2000', '48000', '1000', spec['arm']]
        check(session.get('client_command') == command, 'actual syscall client argv differs', issues)
        provider_command = load(path/'load-provider.log.command.json', issues)
        check(provider_command.get('argv') == ['insmod', binaries['measure'].get('provider',{}).get('path'),
              'api_bind=1','bench_quiet=1','bench_complete_probe=0','jit_timing=0','hotlock_stats=0','target_process=sc_worker'],
              'actual provider setup differs', issues)
        params = session.get('parameters', {})
        check(all(params.get(k) == v for k,v in PARAMETERS.items()), 'timed observation/fault parameters differ', issues)
        check(all(k in params for k in COMPARE_PARAMETERS), 'paired static parameter missing', issues)
        check(session.get('jit_execution') == 'not-observed-in-scored-session', 'timed JIT classification differs', issues)
        publication = session.get('publication', {})
        registry, entry_addresses = publication.get('registry', []), binding.get('entries', [])
        check(entry_addresses == expected_entries, 'original-body entry addresses differ from functional proof', issues)
        check(len(entry_addresses)==len(set(entry_addresses))==3 and all(entry_addresses) and len(registry)==3 and
              {r.get('entry') for r in registry}==set(entry_addresses) and all(r.get('status')==0 and r.get('code') and r.get('pid')==0 and
              r.get('entry_abi')==(1 if r.get('entry')==entry_addresses[0] else 2) and
              r.get('lock_kind')==(1 if r.get('entry')==entry_addresses[0] else 2) for r in registry), 'three original-body publications differ', issues)
        check(len(publication.get('images', {}))==3, 'three immutable image receipts missing', issues)
        for name, digest in publication.get('images', {}).items(): raw(path/name, issues, digest)
        warms = session.get('warmups', [])
        check(1 <= len(warms) <= 4, 'bounded warmup set missing', issues)
        for i,warm in enumerate(warms):
            data = load(path/('warmup-'+str(i)+'.json'), issues)
            if validators: guarded('warmup interval', lambda v=data: validators['validate_phase'](v,spec,False), issues)
            check(data.get('completed') == warm.get('completed') and warm.get('before') == warm.get('after'), 'unscored warmup observation/accounting differs', issues)
        before_check = load(path/'check.json', issues)
        after_check = load(path/'check-after.json', issues)
        check(before_check.get('check') is True and after_check.get('check') is True, 'syscall oracle missing/failed', issues)
        measurement = load(path/'measure.json', issues)
        check(measurement == session.get('measurement'), 'raw measured reply differs', issues)
        score = guarded('joined two-second interval', lambda: validators['validate_phase'](measurement,spec,True), issues) if validators else None
        if not validators: issues.append('hash-bound pure validator unavailable')
        observed = session.get('whole_throughput_ops_s')
        check(type(observed) in (int,float) and math.isfinite(observed) and observed>0 and score is not None and
              math.isclose(observed,score,rel_tol=1e-12,abs_tol=1e-6), 'whole-throughput recomputation differs', issues)
        point = {**spec, 'status':'VALID' if not issues else 'ABSENT' if not session else 'INVALID', 'issues':issues,
                 'raw_whole_ops_s':observed, 'recomputed_whole_ops_s':score,
                 'completed':measurement.get('completed'), 'wall_ns':measurement.get('wall_ns'),
                 'captured_session':session}
        return point
    points=[]
    for spec in plan:
        try:
            points.append(audit_point(spec))
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
            # Preserve the planned coordinate when an individual receipt has
            # malformed fields; never let it erase later absent coordinates.
            points.append({**spec,'status':'INVALID','issues':['malformed point: '+repr(error)],
                           'raw_whole_ops_s':None,'recomputed_whole_ops_s':None,
                           'completed':None,'wall_ns':None,'captured_session':{}})
    pairs=[]
    for kind in CASES:
        for n in WORKERS:
            native, kd = [next(p for p in points if p['kind']==kind and p['workers']==n and p['arm']==arm) for arm in ('native','kd')]
            issues=[]
            check(native['status']=='VALID' and kd['status']=='VALID', 'both raw points must validate', issues)
            ns,ks=native['captured_session'],kd['captured_session']
            check({k:ns.get('parameters',{}).get(k) for k in COMPARE_PARAMETERS}=={k:ks.get('parameters',{}).get(k) for k in COMPARE_PARAMETERS}, 'paired parameters differ', issues)
            check(ns.get('binding',{}).get('entries')==ks.get('binding',{}).get('entries'), 'paired original-body entries differ', issues)
            a,b=native['recomputed_whole_ops_s'],kd['recomputed_whole_ops_s']
            delta=100*(b/a-1) if a is not None and b is not None and a>0 else None
            eligible=not identity_issues and not issues
            pairs.append(dict(kind=kind,workers=n,native_status=native['status'],kd_status=kd['status'],native_ops_s=a,kd_ops_s=b,
                              raw_delta_pct=delta,comparison_identity_valid=eligible,matched_delta_pct=delta if eligible else None,
                              direction=('loss' if delta<0 else 'gain' if delta>0 else 'equal') if eligible and delta is not None else 'UNQUALIFIED',issues=issues))
    summary=dict(schema=1,source_commit=COMMIT,kernel_project_commit=RECIPE,boot_id=boot,kernel_identity=kernel,
                 expected_points=126,captured_sessions=len(embedded),valid_points=sum(p['status']=='VALID' for p in points),
                 absent_points=sum(p['status']=='ABSENT' for p in points),invalid_points=sum(p['status']=='INVALID' for p in points),
                 pairs=63,identity_valid=not identity_issues,identity_issues=identity_issues,completion_issues=completion_issues,
                 campaign_complete=not completion_issues and not identity_issues and len(embedded)==126 and all(p['status']=='VALID' for p in points),
                 direction_counts={v:sum(p['direction']==v for p in pairs) for v in ('gain','loss','equal','UNQUALIFIED')},
                 functional_jit=[{k:r.get(k) for k in ('name','kind','arm','functional_jit','retired')} for r in functional.get('sessions',[])],
                 unexpected_records=unexpected,unexpected_session_paths=unexpected_paths,performance_accepted=False,
                 host_endpoint='NOT_ASSESSED_BY_THIS_ANALYZER',rounds_per_point=1,duration_ms=2000,
                 score='completed operations / actual joined wall interval',timed_jit='not observed; separate functional proof only')
    def write_json(name,value): (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    write_json('points.json',points); write_json('summary.json',summary)
    def csv_rows(name,rows,fields):
        with (out/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
            for row in rows: writer.writerow({k:json.dumps(row.get(k)) if isinstance(row.get(k),(dict,list)) else row.get(k) for k in fields})
    csv_rows('points.csv',points,['name','kind','arm','workers','round','duration_ms','instrumentation','status','raw_whole_ops_s','recomputed_whole_ops_s','completed','wall_ns','issues'])
    csv_rows('pairs.csv',pairs,list(pairs[0]))
    lines=['# Original-body syscall comparison','',f'Source `{COMMIT}`; kernel recipe `{RECIPE}`; boot `{boot}`.',
           '',f"Retained {len(embedded)}/126 aggregate sessions; {summary['valid_points']} valid, {summary['invalid_points']} invalid and {summary['absent_points']} absent planned points.",
           f"Identity checks: {'passed' if summary['identity_valid'] else 'failed'}. Campaign completion: {summary['campaign_complete']}. Performance accepted: **false**.",
           '', 'Native and KD are paired at each case/worker count. Values use whole joined two-second intervals; one measured round per coordinate.',
           'Raw deltas remain descriptive when identity or point validation fails. Every negative value and failed/missing coordinate is retained.',
           'JIT returned-body proof belongs to the separate six-session functional run. Timed sessions do not observe JIT execution.',
           'Setfd counts F_SETFD plus F_GETFD per operation; each pipe operation is one syscall. No TCLock or extracted-body result is included.',
           'Host endpoint assessment, outstanding nano losses and final mmap1 acceptance remain separate.',
           '', '| Case | Workers | Native ops/s | KD ops/s | KD delta | Status |','| --- | ---: | ---: | ---: | ---: | --- |']
    for p in pairs:
        number=lambda v:'—' if v is None else f'{v:,.3f}'
        lines.append(f"| {p['kind']} | {p['workers']} | {number(p['native_ops_s'])} | {number(p['kd_ops_s'])} | {number(p['matched_delta_pct'])}% | {p['direction']} |")
    lines += ['', 'All issues and exact functional counters are retained in `summary.json`; per-point failures and raw rates are in `points.csv` and `pairs.csv`.','']
    (out/'README.md').write_text('\n'.join(lines))
    inputs[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write_json('read-files-sha256.json',inputs)
    write_json('output-sha256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    print(json.dumps({'report':str(out),'identity_valid':summary['identity_valid'],'campaign_complete':summary['campaign_complete'],'performance_accepted':False}))


if __name__ == '__main__':
    main()
