#!/usr/bin/env python3
"""Audit frozen correctness evidence offline; never build or execute tests.

Writes validation.json and artifacts.json. Archive bytes, extracted files,
source manifests, exact frozen mutation sets, functional progress and lifetime
receipts are checked independently of performance scoring. Additional stages
are discovered; --unit PHASE=directory --reference PHASE=directory append later
unit generations without attributing old checks to new source. Explicit
--functional-reference PREFIX=directory maps nonuniform FULL directory names;
--failed-unit PHASE=directory retains the known final fixture compilation error.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/mutex-owned-hybrid-20261014'
# Reuse only data-reading helpers from the earlier report. Its main() is never
# invoked; no live provider, test driver or frozen Python source is imported.
HELPER = HERE.parent/'20261013/validate.py'
spec = importlib.util.spec_from_file_location('owned_receipt_helpers', HELPER)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
require, read, receipt = h.require, h.read, h.file_receipt


def assignments(source, names):
    """Read dictionary keys from frozen driver syntax, without executing it."""
    result = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets):
            result.update(ast.literal_eval(key) for key in node.value.keys)
    require(result, 'missing frozen mutation declarations: '+str(names))
    return result


def sources(folder, reference=None):
    result = h.frozen_sources(folder, reference)
    require(not result['missing_bytes'], 'incomplete frozen sources: '+str(folder))
    if reference:
        require(not result['provider_differences'], 'tested provider differs from reference: '+str(folder))
    manifest_path, manifest = h.source_manifest(folder)
    essential = ['include/kd_mutex.h', 'include/kd_owned_mutex_internal.h',
                 'include/kd_owned_mutex_direct.h', 'kernel_module/owned_mutex/core.c',
                 'kernel_module/owned_mutex/osq.c', 'kernel_module/owned_mutex/delegation.c']
    require(all(name in manifest for name in essential), 'missing owned protocol source identity')
    result['owned_protocol_sha256'] = {name: manifest[name] for name in essential}
    return result


def mutation_receipt(folder, source_name, logs, pattern, dictionaries=('mutations',), override=None):
    source = override or folder/'source'/source_name
    expected = assignments(source.read_text(), dictionaries)
    observed = re.findall(pattern, '\n'.join(p.read_text() for p in logs))
    require(len(observed) == len(set(observed)) and set(observed) == expected,
            f'mutation coverage differs for {source}: expected={sorted(expected)}, observed={observed}')
    return dict(driver=receipt(source), logs=[receipt(p) for p in logs],
                rejected_mutations=sorted(expected), count=len(expected))


def unit(folder, reference):
    log = folder/'unit.log'
    text = log.read_text()
    summary = re.findall(r'Unit tests: (\d+) passed, (\d+) failed', text)
    require(len(summary)==1 and int(summary[0][1])==0, 'unit groups failed/incomplete: '+str(log))
    require('[PASS] test_control_call' in text and '[PASS] test_daemon_policy' in text,
            'basic groups missing: '+str(log))
    result = dict(directory=h.relative(folder), scope='Selected basic and affected checks; not a full-suite pass.',
                  groups=int(summary[0][0]), unit_log=receipt(log), sources=sources(folder,reference), mutations={})
    recipes = [
        ('core', 'tests/unit/mutex/test_owned_mutex_core.py', r'owned mutex fixture rejects ([\w-]+)'),
        ('preflight', 'tests/unit/mutex/test_owned_mutex_preflight.py', r'owned preflight fixture rejects ([\w-]+)'),
        ('admission', 'tests/unit/infrastructure/test_hotlock_sampling.py', r'hotlock mutation detected: ([\w-]+)'),
        ('queued_osq', 'tests/unit/mutex/test_owned_mutex_osq.py', r'bounded OSQ fixture rejects ([\w-]+)'),
        ('profiler', 'tests/unit/mutex/test_owned_mutex_profile.py', r'diagnostic preflight fixture rejects ([\w-]+)'),
    ]
    for label, filename, pattern in recipes:
        if re.search(pattern,text):
            result['mutations'][label] = mutation_receipt(folder,filename,[log],pattern)
    for filename, label, pattern, driver in (
        ('osq-mutations.log','queued_osq',r'bounded OSQ fixture rejects ([\w-]+)','tests/unit/mutex/test_owned_mutex_osq.py'),
        ('osq.log','queued_osq',r'bounded OSQ fixture rejects ([\w-]+)','tests/unit/mutex/test_owned_mutex_osq.py'),
    ):
        if (folder/filename).exists():
            result['mutations'][label] = mutation_receipt(folder,driver,[folder/filename],pattern)
    for filename in ('queue.log','queue-mutations.log'):
        path=folder/filename
        if path.exists() and not (folder/'queue-mutations-retry.log').exists():
            require('PASS production owned single outcome:' in path.read_text(), 'queue/notification production check absent')
            result['mutations']['queue_and_notification']=mutation_receipt(folder,
                'tests/unit/mutex/test_owned_mutex_delegation.py',[path],r'PASS rejected mutation: ([\w-]+)',
                ('mutations','notification_mutations'))
    if (folder/'queue-mutations-retry.log').exists():
        original = folder/'source/tests/unit/mutex/test_owned_mutex_delegation.py'
        corrected = folder/'notification-retry-input.py'
        sha = (folder/'notification-retry-input.sha256').read_text().split()[0]
        require(h.digest(corrected)==sha, 'retry driver identity differs')
        old = original.read_text(); new = corrected.read_text()
        before = "'static void kd_owned_mutex_flush_wakes(struct rcuwait **wake,'"
        after = "'static void kd_owned_mutex_flush_wakes(struct rcuwait **wake, unsigned int *count)'"
        require(old.count(before)==1 and old.replace(before,after)==new,
                'retry changed more than the recorded extraction marker')
        failed = folder/'queue-mutations.log'
        require('AssertionError: expected one definition' in failed.read_text(), 'missing original extraction failure')
        result['retry'] = dict(classification='FIXTURE_EXTRACTION_FAILURE_THEN_PASS',
                              initial_log=receipt(failed), original_driver=receipt(original),
                              corrected_driver=receipt(corrected), checksum=receipt(folder/'notification-retry-input.sha256'))
        result['mutations']['queue_and_notification'] = mutation_receipt(folder,
            'tests/unit/mutex/test_owned_mutex_delegation.py', [folder/'queue-mutations-retry.log'],
            r'PASS rejected mutation: ([\w-]+)', ('mutations','notification_mutations'), corrected)
    for filename in ('unit-status.txt','retry-and-wait-status.txt'):
        if (folder/filename).exists():
            status=(folder/filename).read_text().strip()
            values=re.findall(r'^([a-z][a-z_-]*)=(\d+)$',status,re.M)
            zero_statuses=bool(values) and len(values)==len(status.splitlines()) and \
                len(values)==len(set(k for k,_ in values)) and all(int(v)==0 for _,v in values)
            require(status=='PASS' or zero_statuses, 'driver status failed')
            result.setdefault('statuses',[]).append(dict(artifact=receipt(folder/filename),
                exit_statuses={k:int(v) for k,v in values} if zero_statuses else None,summary='PASS'))
    for filename in ('runner.log','study.log'):
        path=folder/filename
        if path.exists():
            body=path.read_text(); counts=re.findall(r'Ran (\d+) tests\b',body)
            require(len(counts)==1 and body.rstrip().endswith('OK'), 'Python checks incomplete: '+str(path))
            result.setdefault('python_checks',[]).append(dict(log=receipt(path),tests=int(counts[0])))
    result['observed_checks'] = [marker for marker in (
        'actual compiled/JIT outer entry', 'production mutex shadow switch',
        'production owned producer destroyed-frame resume', 'production task cache',
        'owned bounded OSQ:', 'diagnostic preflight probes:',
        'hotlock mutation detected:', 'after-outer production functions') if marker in text]
    modes=re.findall(r'^(capture-first|preflight): PASS actual compiled/JIT outer entry:',text,re.M)
    if modes:
        require(sorted(modes)==['capture-first','preflight'],'compiled/JIT outer modes incomplete/duplicated')
        result['compiled_and_generated_jit_outer_modes']=modes
    after_outer=re.findall(r'after-outer production functions: (\d+) checks, (\d+) failures',text)
    if after_outer:
        require(len(after_outer)==1 and int(after_outer[0][1])==0,'after-outer production checks failed')
        result['after_outer_production_checks']=int(after_outer[0][0])
    result['command_receipt_limit'] = 'Unit logs/status files are archived; separate command JSON and numeric exit status were not recorded for every selected group.'
    return result


def failed_unit(folder, retry_folder, reference):
    """One identified fixture failure, never a production correctness pass."""
    log=folder/'unit.log';text=log.read_text()
    require(re.findall(r'Unit tests: (\d+) passed, (\d+) failed',text)==[('10','1')],
            'unexpected retained final unit result')
    require('omit-capture-first-observation' in text and
            ('-Werror=unused-function' in text or '-Wunused-function' in text) and
            ('CalledProcessError' in text or 'returned non-zero exit status' in text),
            'retained failure was not the identified mutation compilation error')
    original_path,original=h.source_manifest(folder)
    retry_path,retry=h.source_manifest(retry_folder)
    changed=sorted(name for name in set(original)|set(retry) if original.get(name)!=retry.get(name))
    driver='tests/unit/mutex/test_owned_mutex_preflight.py'
    require(changed==[driver], 'final retry changed more than the fixture driver: '+str(changed))
    before=folder/'source'/driver;after=retry_folder/'source'/driver
    require(assignments(before.read_text(),('mutations',))==assignments(after.read_text(),('mutations',)),
            'final retry changed the mutation inventory')
    normalized=[]
    for path in (before,after):
        tree=ast.parse(path.read_text());replaced=0
        for node in ast.walk(tree):
            if not isinstance(node,ast.Dict):
                continue
            for index,key in enumerate(node.keys):
                if isinstance(key,ast.Constant) and key.value=='omit-capture-first-observation':
                    node.values[index]=ast.Constant(value='SCOPED_MUTATION');replaced+=1
        require(replaced==1,'missing/duplicate corrected mutation')
        # The retry names the unchanged extracted function so that the mutant
        # can replace that full function. Inline only this exact adjacent local
        # binding/append pair; do not normalize arbitrary driver changes.
        expected=ast.parse("'unsigned long ' + definition(delegate, 'kd_owned_mutex_outer_contended_clobber_v1(')",
                           mode='eval').body
        bindings=0
        for function in ast.walk(tree):
            if not isinstance(function,(ast.FunctionDef,ast.AsyncFunctionDef)):
                continue
            for index,node in enumerate(function.body[:-1]):
                if not (isinstance(node,ast.Assign) and len(node.targets)==1 and
                        isinstance(node.targets[0],ast.Name) and node.targets[0].id=='capture'):
                    continue
                append=function.body[index+1]
                require(ast.dump(node.value,include_attributes=False)==ast.dump(expected,include_attributes=False) and
                        isinstance(append,ast.AugAssign) and isinstance(append.target,ast.Name) and
                        append.target.id=='production' and isinstance(append.op,ast.Add) and
                        isinstance(append.value,ast.Name) and append.value.id=='capture',
                        'retry capture binding differs from the unchanged extraction/append')
                append.value=node.value
                function.body[index:index+2]=[append]
                bindings+=1
                break
        require(bindings<=1 and not any(isinstance(node,ast.Name) and node.id=='capture'
                                       for node in ast.walk(tree)),
                'unexpected capture binding/use outside the corrected mutation')
        normalized.append(ast.dump(tree,include_attributes=False))
    require(normalized[0]==normalized[1], 'retry changed executable driver code outside the one mutation definition')
    return dict(status='FIXTURE_MUTATION_COMPILE_FAILURE_RETRIED',groups_passed=10,groups_failed=1,
                log=receipt(log),sources=sources(folder,reference),retry_directory=h.relative(retry_folder),
                original_driver=receipt(before),retry_driver=receipt(after),changed_source_files=changed,
                reason='A shared mutation text matched both entrypoints and left an unused helper under -Werror. The retry scopes that mutation to one full function; this initial run is not a runtime mutation rejection.',
                driver_change_scope='AST equality after replacing the single corrected mutation value and inlining its exact unchanged extraction/append binding proves other executable driver code and assertions unchanged; comments/formatting are outside this comparison.')


def environment(folder):
    env=read(folder/'environment.json')
    require(env['kernel_identity']['ok'] and env['kernel_identity']['running_build_id']==
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus']==list(range(64)) and
            {'nokaslr','nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'], 'functional environment differs')
    return dict(artifact=receipt(folder/'environment.json'),
                kernel_build_id=env['kernel_identity']['running_build_id'],
                collector_topology=env['collector_topology'],
                collector_limit='Fixed-iteration runs may not record collector affinity; no CPU63 binding is inferred when null.')


def postflight(raw, initial, required=False):
    host_path,guest_path=raw/'host-state-final.json',raw/'guest-final.log'
    if not host_path.exists() and not guest_path.exists():
        require(not required,'final-stage archives require final host/guest postflight receipts')
        return None
    host=read(host_path);guest=guest_path.read_text()
    require(host['verified'] and host['qemu_pid']==initial['qemu_pid'] and
            host['pins']==initial['pins']=={str(n):[n] for n in range(64)},
            'postflight host identity/pins differ')
    require(set(host['cpufreq'])=={str(n) for n in range(64)} and
            all(state['scaling_governor']=='ondemand' and state['scaling_min_freq']=='800000' and
                state['scaling_max_freq']=='3600000' for state in host['cpufreq'].values()),
            'postflight host frequency policy differs')
    identities=[json.loads(line) for line in guest.splitlines() if line.startswith('{')]
    require(len(identities)==1 and identities[0]['ok'] and identities[0]['config'] and
            identities[0]['running_build_id']=='5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            'guest_idle=True' in guest.splitlines(), 'postflight guest identity/idle receipt differs')
    cmdlines=[line for line in guest.splitlines() if line.startswith('BOOT_IMAGE=')]
    require(len(cmdlines)==1 and {'nokaslr','nopvspin'}<=set(cmdlines[0].split()),
            'postflight guest boot policy differs')
    modules=re.findall(r'^([\w]+)\s+\d+\s+\d+\s+.*\bLive\b.*$',guest,re.M)
    require(modules and not any(name.startswith(('kdlock','kd_','mutex_cacheline','spin_cacheline',
                                                 'rwsem_cacheline','tclock')) for name in modules),
            'postflight module listing absent or project module remains')
    return dict(host=receipt(host_path),guest=receipt(guest_path),qemu_pid=host['qemu_pid'],
                exact_vcpu_pins=64,frequency_policy=dict(governor='ondemand',min_khz=800000,max_khz=3600000),
                kernel_build_id=identities[0]['running_build_id'],guest_idle=True,project_modules_present=False,
                scope='Archived final host/guest observations, not a current live-state check. No separate numeric command exit receipt is inferred from these content-only files.')


def functional(folder, reference=None):
    plan, summary=read(folder/'plan.json'),read(folder/'functional.json')
    require(len({s['name'] for s in plan})==len(plan) and
            {s['name'] for s in plan}=={s['name'] for s in summary}, 'functional plan/summary differ')
    output=dict(directory=h.relative(folder), sources=sources(folder,reference), binaries=h.frozen_binaries(folder),
                environment=environment(folder),plan=receipt(folder/'plan.json'),
                summary=receipt(folder/'functional.json'),sessions=[],not_run=[])
    for expected in plan:
        row=next(s for s in summary if s['name']==expected['name'])
        sub=folder/expected['name']
        if row['status']=='NOT_RUN':
            require(not sub.exists() and row['completed']==row['jit_bodies']==0, 'NOT_RUN has execution artifacts')
            output['not_run'].append(expected['name']);continue
        record,m=read(sub/'session.json'),read(sub/'measure.json')
        require(all(record[k]==v for k,v in expected.items()), 'plan/session disagreement')
        require(record['measurement']==m and record['owned_mutex_force_full'] and
                record['mutex_implementation']=='owned-v1' and record['post_work_rounds']==64 and
                record['retired']==h.RETIRED and record['drained'], 'functional identity/drain differs')
        require(m['complete'] and m['data_ok'] and m['cachelines']==1 and m['threads']==expected['threads'] and
                m['iterations']==expected['iterations'], 'incorrect fixed work')
        workers=m['workers']
        require(len(workers)==expected['threads'] and [w['cpu'] for w in workers]==expected['cpus'] and
                all(w['completed']==expected['iterations'] and w['error']==0 and
                    w['observed_cpu']==w['cpu'] and w['cpu_ns']>0 for w in workers), 'worker progress/placement differs')
        require(m['completed']==sum(w['completed'] for w in workers)==expected['threads']*expected['iterations'] and
                m['worker_cpu_ns']==sum(w['cpu_ns'] for w in workers) and
                m['finished_ns']==max(w['finished_ns'] for w in workers) and
                m['wall_ns']==m['finished_ns']-m['started_ns']>0, 'worker aggregate mismatch')
        require(len(m['before'])==len(m['after'])==16 and all(
                a-b==(m['completed'] if i==0 else 0) for i,(b,a) in enumerate(zip(m['before'],m['after']))),
                'protected data mismatch')
        for name in ('measure.counts.json','drain.counts.json'):
            require(read(sub/name)==dict(active=0,values=m['after']), 'incomplete worker drain')
        warm=read(sub/'warmup.json')
        require(warm['complete'] and warm['data_ok'] and warm['completed']==expected['threads']*48000 and
                all(w['completed']==48000 and w['error']==0 for w in warm['workers']) and
                warm['after']==m['before'], 'warmup mismatch')
        for name in ('load-kdlock.log','unload-kdlock.log','load-source.log','unload-source.log'):
            require(not (sub/name).read_text().strip(), 'module operation failure')
        pub=record['published_before']
        require(pub==record['published_after'] and pub['entry']['lock_kind']==3 and
                pub['entry']['entry_abi']==2 and pub['entry']['status']==0, 'JIT publication differs')
        images=sub/'workspace/daemon'/hex(pub['entry']['entry'])/str(pub['entry']['tgid'])/'asm'
        for name,sha in pub['images'].items():
            require(h.digest(images/name)==sha, 'frozen JIT differs')
        require(record['layout']==read(sub/'layout.json') and record['layout']['lock_bytes']==32,
                'public object geometry differs')
        params=record['parameters']
        require(params['owned_mutex_self_route']=='N' and params['owned_mutex_entry_ratio_limit']=='256' and
                params['owned_mutex_native_after_control']=='1' and
                (params.get('owned_mutex_refill','N')=='Y')==record['owned_mutex_refill'], 'FULL controls differ')
        kernel=h.kernel_receipt(sub/'kernel.log')
        require(record['jit_after']-record['jit_before']==record['jit_bodies'] and
                record['owned_observations']==kernel['owned'] and row['drained'] and
                row['jit_bodies']==record['jit_bodies'], 'functional counters differ')
        if row['status']=='NO_JIT':
            require(record['jit_bodies']==0 and record['jit_acceptance']=='NO_JIT' and
                    record['error']=='contended kdlock arm had no actual JIT' and
                    record['cleanup_error']=='checked post-control continuation was not exercised' and
                    kernel['native']['started']==0, 'unrecognized failed FULL case')
            status='REJECTED_NO_JIT_FULL_NOT_EXERCISED'
        else:
            require(row['status']==record['execution_status']=='OK' and record['jit_acceptance']=='PASS' and
                    record['execution_class']=='JIT' and 0<record['jit_bodies']<=m['completed'] and
                    record['owned_full_ack']==kernel['native'] and kernel['native']['started']>0 and
                    kernel['native']['unlocks']>=2 and
                    (sub/'kernel.log').read_text().count('reason=OWNED_CONTROL_NATIVE')==1,
                    'FULL continuation/ACK not proved')
            require(record['scenario']!='early' or kernel['owned']['early_releases']>0, 'early release absent')
            status='PASS_LIVE_FULL_ACK'
        output['sessions'].append(dict(name=expected['name'],workers=expected['threads'],scenario=record['scenario'],
            status=status,completed=m['completed'],jit_bodies=record['jit_bodies'],all_workers_progress=True,
            drained=True,session=receipt(sub/'session.json'),measurement=receipt(sub/'measure.json'),
            kernel=kernel,entry_policy=record.get('owned_preflight_policy','capture_first'),
            spins=record.get('owned_mutex_preflight_spins'),queued=record.get('owned_mutex_preflight_queue',False)))
    output['builds']=[h.build_receipt(folder,name,w1=False) for name in ('build-provider.log','build-kdlock.log')]
    for build in output['builds']:
        # Counts/categories and the exact raw log hash suffice here; do not
        # duplicate hundreds of identical objtool warning lines in this index.
        del build['warning_lines']
    return output


def drivers(extracted):
    result=[]
    for path in sorted(extracted.glob('*driver.log')):
        text=path.read_text()
        starts=re.findall(r'^\[(\d+)/(\d+)\] (\S+)',text,re.M)
        if not starts:
            statuses=re.findall(r'^([a-z][a-z_-]*)=(\d+)$',text,re.M)
            require(statuses and len(statuses)==len(set(k for k,_ in statuses)) and
                    len(statuses)==len(text.splitlines()), 'unrecognized/failed checks driver: '+str(path))
            result.append(dict(log=receipt(path),status=('COMPLETED_EXIT_STATUS_RECEIPT' if
                               all(int(code)==0 for _,code in statuses) else 'FAILED_EXIT_STATUS_RECEIPT'),
                               exit_statuses={name:int(code) for name,code in statuses}))
            continue
        finishes=len(re.findall(r'drained=True',text))
        rejected='STOP: contended kdlock arm had no actual JIT' in text
        require(starts and finishes==len(starts)-(1 if rejected else 0), 'incomplete driver: '+str(path))
        require('Traceback' not in text and not re.search(r'drained=False',text), 'driver execution error')
        require(rejected or (int(starts[-1][0])==int(starts[-1][1])), 'driver stopped before last session')
        result.append(dict(log=receipt(path),sessions_started=len(starts),sessions_completed=finishes,
                           status='REJECTED_NO_JIT' if rejected else 'COMPLETED_LOG_RECEIPT',
                           numeric_exit_status='not recorded in this artifact'))
    return result


def mappings(values):
    result={}
    for value in values:
        key,path=value.split('=',1);require(key not in result,'duplicate phase');result[key]=path
    return result


def prior_osq_coverage(old_folder, new_folder, old_result):
    """Carry over identities only; never present an earlier run as repeated."""
    inputs=('kernel_module/owned_mutex/core.c', 'kernel_module/owned_mutex/osq.c',
            'include/kd_owned_mutex_internal.h', 'tests/unit/mutex/test_owned_mutex_osq.py',
            'tests/unit/mutex/owned_mutex_osq_fixture.c', 'tests/unit/infrastructure/source_text.py')
    hashes={}
    for name in inputs:
        before,after=old_folder/'source'/name,new_folder/'source'/name
        require(h.digest(before)==h.digest(after), 'OSQ carryover input changed: '+name)
        hashes[name]=h.digest(after)
    # OSQ imports only definition() from this otherwise changed driver.
    helper='tests/unit/mutex/test_owned_mutex_preflight.py'
    definitions=[]
    for folder in (old_folder,new_folder):
        text=(folder/'source'/helper).read_text()
        nodes=[node for node in ast.parse(text).body if isinstance(node,ast.FunctionDef) and node.name=='definition']
        require(len(nodes)==1,'missing OSQ extraction helper')
        definitions.append(ast.get_source_segment(text,nodes[0]))
    require(definitions[0]==definitions[1], 'OSQ extraction helper changed')
    return dict(status='PRIOR_MUTATIONS_IDENTICAL_INPUTS_NOT_RERUN',
                original=old_result['mutations']['queued_osq'],unchanged_inputs_sha256=hashes,
                extraction_helper=dict(path=helper,function='definition',
                    sha256=hashlib.sha256(definitions[0].encode()).hexdigest()),
                limit='Current generation ran the production OSQ fixture; ten mutation rejections belong to the earlier queued generation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=RAW)
    parser.add_argument('--output-dir',type=Path,default=HERE)
    parser.add_argument('--unit',action='append',default=[])
    parser.add_argument('--reference',action='append',default=[])
    parser.add_argument('--functional-reference',action='append',default=[])
    parser.add_argument('--failed-unit',action='append',default=[])
    parser.add_argument('--wait',action='append',default=[])
    args=parser.parse_args();raw=args.raw.resolve();extracted=raw/'extracted'
    archives=[]
    for path in sorted(raw.glob('stage*.tar.gz')):
        item=h.archive_receipt(path,extracted)
        item['classification']='SUPERSEDED_ARCHIVE_ATTEMPT' if 'missing-driver-attempt' in path.name else 'CANONICAL_STAGE'
        archives.append(item)
    present={int(re.match(r'stage(\d+)',Path(a['archive']['path']).name)[1])
             for a in archives if a['classification']=='CANONICAL_STAGE'}
    require({1,2,3,4}<=present,'stages1–4 missing')
    units={phase:f'tests/mutex-owned-hybrid-{phase}-20261014' for phase in ('outcome','preflight','queued')}
    refs=dict(outcome='bench/mutex-owned-hybrid-outcome64-20261014',
              preflight='bench/mutex-owned-hybrid-preflight0-refill64-20261014',
              queued='bench/mutex-owned-hybrid-queued-control1024-refill64-20261014')
    units.update(mappings(args.unit));refs.update(mappings(args.reference))
    require(set(units)<=set(refs),'each unit generation needs a source reference')
    unit_results={name:unit(extracted/path,extracted/refs[name]) for name,path in units.items()}
    if 'single' in units and 'queued_osq' not in unit_results['single']['mutations']:
        unit_results['single']['prior_osq_mutation_coverage']=prior_osq_coverage(
            extracted/units['queued'],extracted/units['single'],unit_results['queued'])
    probe=extracted/'tests/mutex-owned-hybrid-outcome-wait-20261014'
    wait=h.probe_receipt(probe,extracted/refs['outcome'],'owned')
    require(not wait['sources']['provider_differences'],'wait probe provider differs')
    failed_units=mappings(args.failed_unit)
    require(set(failed_units)<=set(units),'each failed unit generation needs a passing retry')
    failures={name:failed_unit(extracted/path,extracted/units[name],extracted/refs[name])
              for name,path in failed_units.items()}
    wait_folders=mappings(args.wait)
    require(set(wait_folders)<=set(refs),'each wait generation needs a source reference')
    later_waits={name:h.probe_receipt(extracted/path,extracted/refs[name],'owned')
                 for name,path in wait_folders.items()}
    require(all(not value['sources']['provider_differences'] for value in later_waits.values()),
            'later wait probe provider differs')
    full_refs=mappings(args.functional_reference)
    full=[]
    for folder in sorted((extracted/'tests').glob('*full*')):
        if not (folder/'plan.json').is_file():
            continue
        override=next((full_refs[prefix] for prefix in sorted(full_refs,key=len,reverse=True)
                       if folder.name.startswith(prefix)),None)
        phase=next((name for name in refs if folder.name.startswith(f'mutex-owned-hybrid-{name}-full')),None)
        require(override is not None or phase is not None,'FULL generation needs explicit --functional-reference: '+folder.name)
        full.append(functional(folder,extracted/(override if override is not None else refs[phase])))
    failed=[session for group in full for session in group['sessions'] if session['status'].startswith('REJECTED')]
    require(len(failed)==1 and failed[0]['workers']==4,'expected failed four-worker FULL receipt absent/changed')
    host=read(raw/'host-state-start.json')
    require(host['verified'] and host['pins']=={str(n):[n] for n in range(64)}, 'initial host pin verification differs')
    guest=(raw/'guest-start.log').read_text()
    require('guest_idle=True' in guest and '"ok": true' in guest and
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' in guest, 'initial guest identity/idle receipt differs')
    require(re.search(r'mutex-owned-hybrid-20261014\s+\d', (raw/'snapshot-list.log').read_text()),
            'recovery snapshot listing absent')
    recovery=dict(initial_host=receipt(raw/'host-state-start.json'),initial_guest=receipt(raw/'guest-start.log'),
                  snapshot_listing=receipt(raw/'snapshot-list.log'),
                  scope='Archived pre-run identity, 64 exact vCPU pins and recovery snapshot listing; not a current live-state check.')
    final_state=postflight(raw,host,required=8 in present)
    validation=dict(schema=1,audit='PASS_EVIDENCE_CONSISTENCY',full_suite_pass_claimed=False,
        performance_acceptance_claimed=False,archives=archives,units=unit_results,live_wait=wait,live_full=full,
        retained_unit_failures=failures,additional_live_wait=later_waits,
        configuration=dict(unit_directories=units,source_references=refs,functional_references=full_refs,
                           failed_unit_directories=failed_units,additional_wait_directories=wait_folders,
                           reproduce_from_repository_root=shlex.join([
                               'python3',h.relative(Path(__file__)),*sys.argv[1:]])),
        recovery=recovery,postflight=final_state,drivers=drivers(extracted),limits=[
            'Evidence consistency is not proof of all possible concurrency interleavings.',
            'Initial fixture extraction failure and rejected four-worker NO_JIT FULL attempt are retained, not passes.',
            'The initial final-unit mutant compilation failure is retained separately; only the corrected rerun establishes its mutation rejection.',
            'Unit mutation fixtures use modeled kernel primitives; live wait and FULL receipts are reported separately.',
            'Source identity is exact per frozen generation; earlier checks are not attributed to later source.',
            'Archives and local hashes establish internal byte consistency, not independent execution authentication.',
            'Performance scores, primary/regression coverage and confirmations belong to acceptance.json.',
            'New stage archives alone do not extend unit coverage: append --unit and --reference explicitly.'
        ])
    args.output_dir.mkdir(parents=True,exist_ok=True)
    output=args.output_dir/'validation.json'
    plot_receipt=args.output_dir/'plot-inputs.json'
    if plot_receipt.exists():
        plots=read(plot_receipt)
        inputs={'statistics_sha256':'statistics.csv','coverage_sha256':'coverage.json',
                'acceptance_sha256':'acceptance.json','plot_script_sha256':'plot.py'}
        for key,name in inputs.items():
            require(h.digest(args.output_dir/name)==plots[key], 'plot input changed: '+name)
        for name,sha in plots['output_sha256'].items():
            require(h.digest(args.output_dir/h.safe_relative(name))==sha, 'plot output changed: '+name)
    output.write_text(json.dumps(validation,indent=2,sort_keys=True)+'\n')
    artifacts=dict(schema=1,scope='Compact evidence index; original source/binary manifests remain authoritative.',
        builder=receipt(Path(__file__)),data_reading_helpers=receipt(HELPER),validation=receipt(output),
        archives=[item['archive'] for item in archives],
        source_manifests=[result['sources']['manifest'] for result in unit_results.values()]+[
            group['sources']['manifest'] for group in full]+[wait['sources']['manifest']]+[
            value['sources']['manifest'] for value in failures.values()]+[
            value['sources']['manifest'] for value in later_waits.values()],
        host_and_recovery=[receipt(p) for p in sorted(raw.glob('*')) if p.is_file() and
                           p.name.startswith(('host-state','guest-start','guest-final','snapshot-'))],
        extraction_receipts=[receipt(p) for p in sorted(raw.glob('*extraction.json'))],
        published_report_files=[receipt(p) for p in sorted(args.output_dir.iterdir())
                                if p.is_file() and p.name not in ('artifacts.json','validation.json')],
        plot_input_output_hashes_verified=plot_receipt.exists())
    (args.output_dir/'artifacts.json').write_text(json.dumps(artifacts,indent=2,sort_keys=True)+'\n')
    print(f'Audited {len(archives)} archives, {len(unit_results)} frozen unit generations, '
          f'{sum(len(g["sessions"]) for g in full)} functional sessions including {len(failed)} retained rejection; no tests executed.')


if __name__=='__main__':
    main()
