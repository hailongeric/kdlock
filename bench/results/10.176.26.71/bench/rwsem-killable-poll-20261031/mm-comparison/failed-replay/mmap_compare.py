#!/usr/bin/env python3
"""Offline fresh scope1/scope2 KD mmap1 comparison; no workload execution."""
import argparse
import ast
import csv
import datetime
import json
from pathlib import Path
import re
import sys
import tarfile
import tempfile
from types import SimpleNamespace
sys.dont_write_bytecode=True
import nano_core as a
import policy_checks as policy
from fresh_controls import F7,C22,POOL,PROPERTIES,checked,save,host_identity,pool,qualification

RECIPE='f4ae82cfdf053c679c5d09ee8e503a7919764c9b'
MANIFEST='57b031b6c2b27e33a3d7434abf7864b7e8b0aebb00e7a38dc4e135d64314bb7b'
CONTROLLER=policy.OLD_CONTROLLER
MEASURE_CONTROLLER='8af9b7f078555abbf8547aea13e22e49a0ae288a1f2784b233cfc446684e2288'
STRICT_HOLD_COMMIT='3b34414a259d6061a4b566ac33579f9547df080e'
INPUTS='beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0'
PREP='512fbd6f6855cdb109f33641d17107b629cd47a0ceea2e553c5efab6b1c4dac4'
DIAGNOSTIC='5c23db457fc9cfc91ff68c7f392e5c003812cb54a66fe082a0e73a0b459b6120'
BINARIES={'threads':'e6a8102ff408e0a3909248fef301a41b0b0bd07861662002e4e13833534f59c6',
          'processes':'6ec2ac78249dd13ad201faa0a2708e176f9628d2b537d69d5ff8d584004da733'}
ARMS={'baseline':('baseline-f7-scope1-kd','7.0.0-38-kdscope1','kdscope1-kd','8446f4ecb08816380a4c233197a8ce5e4d333aac',F7),
      'candidate':('candidate-22d-scope2-kd','7.0.0-38-kdscope2','kdscope2-kd',RECIPE,C22)}
STEPS=('sites','api','mapping','faults','completed','mmap1-identity','mmap1-measure','endpoint')

def original_logs(archive,names):
    remaining=set(names);result={};prefix=archive.meta['archive_prefix']+'/'
    for group in archive.meta['groups']:
        with tarfile.open(archive.directory/group['file'],'r|gz') as stream:
            for item in stream:
                name=item.name.removeprefix(prefix)
                if name not in remaining:continue
                a.need(item.isfile() and item.size<=8*1024*1024,'unexpected score log')
                data=stream.extractfile(item).read()
                a.need(a.sha(data)==archive.hashes[name],'original score log differs')
                result[name]=data.decode();remaining.remove(name)
    a.need(not remaining,'missing original score logs');return result

def parser(git):
    source=git.blob(RECIPE,'bench/mmap1/run.py')
    a.need(source==git.blob(F7,'bench/mmap1/run.py'),'original mmap1 harness changed')
    node=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='parse_output')
    namespace=dict(rt=SimpleNamespace(require=a.need),re=re,DESCRIPTION='Anonymous memory mmap/munmap of 128MB',
                   SAMPLES=2,UPSTREAM_S=2,WARMUP_SAMPLES=6)
    # Only the pinned pure parser is evaluated; no runner top-level code runs.
    exec(compile(ast.Module(body=[node],type_ignores=[]),'pinned mmap1 parse_output','exec'),namespace)
    return namespace['parse_output'],a.sha(source)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inputs-sha256',required=True)
    p.add_argument('--trusted-checkout',type=Path,required=True);p.add_argument('--cache-root',type=Path)
    p.add_argument('--output',type=Path,required=True);x=p.parse_args()
    spec=checked(x.inputs,x.inputs_sha256)
    a.need(spec.get('schema')==2 and set(spec['arms'])==set(ARMS) and
           spec.get('eligibility_policy')==policy.FUNCTIONAL,'explicit prospective two-arm input required')
    a.need(isinstance(MEASURE_CONTROLLER,str) and re.fullmatch('[0-9a-f]{64}',MEASURE_CONTROLLER) and
           isinstance(STRICT_HOLD_COMMIT,str) and re.fullmatch('[0-9a-f]{40}',STRICT_HOLD_COMMIT),
           'prospective controller and strict diagnostic pins are not finalized')
    a.need(not x.output.exists(),'new analysis output required');x.output.mkdir(parents=True)
    receipt=dict(completed=False,validated=False,performance_accepted=False,inputs_sha256=x.inputs_sha256,
                 script_sha256=a.file_sha(Path(__file__)),harness_commit=RECIPE,
                 eligibility_policy=policy.FUNCTIONAL,performance_qualified=False,strict_qualified=False,
                 no_regression_evidence_gate=False,policy_checker_sha256=a.file_sha(Path(policy.__file__)))
    save(x.output/'validation.json',receipt)
    try:
        git=a.Git(x.trusted_checkout);parse,parser_sha=parser(git)
        with tempfile.TemporaryDirectory(prefix='kd-killable-mm-offline-',dir=x.cache_root) as tmp:
            entries=dict(spec.get('support',{}));a.need(not set(entries)&set(ARMS),'support label collides with scored arm')
            entries.update(spec['arms']);archives={};absolute={};kernel_files={};dependencies={}
            for label,e in entries.items():
                a.need(a.safe(label)==label and '/'not in label,'archive label must be a basename')
                directory=Path(e['archives']);checked(directory/'archives.json',e['archives_sha256'])
                a.need(not x.output.resolve().is_relative_to(directory.resolve()),'output overlaps archive')
                cache=Path(tmp)/label;cache.mkdir();ar=a.Archive(directory,cache);archives[label]=ar
                for name,digest in ar.hashes.items():absolute[ar.meta['guest_base']+'/'+name]=digest
                for original,member in e.get('aliases',{}).items():
                    a.need(Path(original).is_absolute() and member in ar.hashes,'alias has no archived bytes')
                    digest=ar.hashes[member]
                    a.need(original not in absolute or absolute[original]==digest,'aliased bytes changed')
                    absolute[original]=digest
            prep_ref=spec['preparation'];pa=archives[prep_ref['archive']]
            inputs=pa.json(prep_ref['inputs_member']);prep=pa.json(prep_ref['result_member'])
            a.need(pa.hashes[prep_ref['inputs_member']]==INPUTS and pa.hashes[prep_ref['result_member']]==PREP and
                   prep.get('passed') is True and prep.get('action')=='prepare' and prep['inputs_sha256']==INPUTS and
                   inputs['binary_sha256']==BINARIES and inputs['executable_modified'] is False,'original application preparation differs')
            for label in ARMS:
                ar=archives[label];e=entries[label];bundle=ar.json(e['bundle_member'])
                a.need(bundle['variant']==ARMS[label][2],'kernel bundle mode differs')
                for kind in ('source','build'):
                    for name,digest in bundle[kind+'_files'].items():
                        path=bundle[kind+'_root']+'/'+name
                        a.need(path not in kernel_files or kernel_files[path]==digest,'kernel input alias changed')
                        a.need(path not in absolute or absolute[path]==digest,'archived/kernel identity alias changed')
                        kernel_files[path]=digest
                manifest=ar.json('mmap1-measure-inputs/recipe-manifest.json')
                a.need(ar.hashes['mmap1-measure-inputs/recipe-manifest.json']==MANIFEST and
                       manifest['source_commit']==RECIPE and len(manifest['files'])==5846,'common harness differs')
                for name,row in manifest['files'].items():
                    path='/root/host_fs/kdlock/'+name
                    a.need(path not in absolute or absolute[path]==row['sha256'],'archived/common harness alias changed')
                    absolute[path]=row['sha256']
                for name,digest in ar.hashes.items():
                    for marker in ('/runtime-source/','/source/'):
                        if marker in name:
                            relative=name.split(marker,1)[1]
                            if relative in manifest['files']:
                                a.need(digest==manifest['files'][relative]['sha256'],'captured harness source differs')
            def bind(files,external=None):
                for name,digest in files.items():
                    if name in absolute:a.need(absolute[name]==digest,'artifact/source binding differs: '+name)
                    elif name in kernel_files:a.need(kernel_files[name]==digest,'runner kernel identity differs: '+name)
                    else:
                        a.need(external is not None and external.get(name)==digest,'unarchived prerequisite: '+name)
                        dependencies[name]=digest
            bind(inputs['files'],inputs['dependencies'])
            points=[];grids={};cohort=None
            for label,(arm,release,variant,kcommit,pcommit) in ARMS.items():
                ar=archives[label];e=entries[label];boot=ar.meta['boot_id'];bundle=ar.json(e['bundle_member'])
                a.need(set(e['owners'])==set(STEPS),'all same-boot owner hashes required')
                owners={};results={};members={}
                expected_mapping={name:dict(owner=('mapping-functional'if name=='mapping'else name)+'-controller.json',
                    result=('mapping-functional'if name=='mapping'else name)+('/writer-sites.json'if name=='sites'else'/result.json'))
                    for name in STEPS} if label=='candidate'else{}
                a.need(e.get('logical_steps',{})==expected_mapping,'explicit logical mapping selection differs')
                for step in STEPS:
                    physical='mapping-functional'if label=='candidate'and step=='mapping'else step
                    owner_member=physical+'-controller.json'
                    member=physical+('/writer-sites.json'if step=='sites'else'/result.json')
                    controller=(policy.MAPPING_CONTROLLER if physical=='mapping-functional'else
                                MEASURE_CONTROLLER if label=='candidate'and step in('mmap1-measure','endpoint')else CONTROLLER)
                    owner=ar.json(owner_member);r=ar.json(member);owners[step]=owner;results[step]=r
                    members[step]={'owner':owner_member,'result':member}
                    a.need(ar.hashes[owner_member]==e['owners'][step] and owner['result_sha256']==ar.hashes[member] and
                           owner.get('completed') is True and owner.get('state')=='COMPLETE' and owner.get('passed') is True and
                           owner.get('drained') is True and owner.get('final_idle') is True and owner.get('drain_unknown') is False and
                           owner.get('completion_checks_passed') is True and owner.get('controller_sha256')==controller and
                           owner.get('arm')==arm and owner.get('step')==physical and owner.get('boot_id')==boot and
                           owner.get('harness_commit')==RECIPE and owner.get('harness_manifest_sha256')==MANIFEST and
                           owner['kernel']['kernel_project_commit']==kcommit and owner['kernel']['provider_comparison_commit']==pcommit and
                           owner['kernel']['variant']==variant and owner['kernel']['release']==release and
                           owner['bundle_manifest_sha256']==ar.hashes[e['bundle_member']], 'same-boot action incomplete or changed: '+step)
                    a.need(step=='endpoint' or owner.get('child_returncode')==0,'child did not complete')
                    a.need(r.get('captured') is True if step=='sites'else r.get('passed') is True and r.get('drained') is True,
                           'runner result incomplete')
                    bind(owner['prerequisite_bindings'])
                    if step not in ('sites','endpoint'):
                        b=r['kernel_binding']
                        a.need(r['mode']=='kd' and r['boot_id']==boot and b['release']==release and b['variant']==variant and
                               b['kernel_mmap_backend']=='kd' and b['private_backing_locks'] is False and
                               b['manifest_sha256']==ar.hashes[e['bundle_member']] and
                               b['build_id']==bundle['running']['build_id'] and
                               b['runtime_policy']['mmap_mode']=='on' and r['kernel_identity']['runtime_policy_verified'] is True and
                               all(b[k]==bundle[k] for k in ('source_files','build_files')),'compiled KD image differs')
                r=results['mmap1-measure'];owner=owners['mmap1-measure'];ep=results['endpoint']
                if label=='baseline':
                    a.need(results['mapping'].get('eligibility_policy',policy.STRICT)==policy.STRICT and
                           results['mapping']['cases'][2]['rejected_mutations']==policy.MUTATIONS,
                           'baseline original strict policy/proof changed')
                    eligibility=dict(original_policy=policy.STRICT,interpretation_policy=policy.FUNCTIONAL,
                                     original_receipts_unchanged=True,performance_qualified=False)
                else:
                    observed=policy.mapping(results['mapping'],owners['mapping'],ar)
                    eligibility=policy.prospective(ar,archives['baseline'],results,owners,members,
                        bind,git,MEASURE_CONTROLLER,STRICT_HOLD_COMMIT,observed)
                expected=[(m,n,0)for m in('threads','processes')for n in a.THREADS]
                a.need(r.get('state')=='COMPLETE' and r.get('action')=='measure' and r.get('final_idle') is True and
                       r.get('single_round') is True and r.get('planned')==42 and r.get('accepted') is False and
                       [(s['model'],s['workers'],s['round'])for s in r['sessions']]==expected and
                       r['inputs_sha256']==INPUTS and r['binary_sha256']==BINARIES and
                       ar.json('mmap1-measure/inputs.json')==inputs,'one-round grid/application inputs differ')
                for step in ('api','mapping','faults','completed','mmap1-identity'):
                    a.need(results[step]['kernel_binding']==r['kernel_binding'],'same-boot check image differs')
                diagnostic=results['mmap1-identity'];adapter=diagnostic['diagnostic_runner']
                a.need(diagnostic.get('scope')=='diagnostic-class-proof' and diagnostic['inputs_sha256']==INPUTS and
                       adapter['sha256']==DIAGNOSTIC and ar.hashes['mmap1-identity/diagnostic-runner.py']==DIAGNOSTIC and
                       adapter['source_commit']=='d22a36567de28c024ebb8d1c79997c0d39541bd2' and
                       'kd_mmap1_identity.mod.c'not in diagnostic['source_sha256'],'fresh diagnostic runner binding differs')
                bind(diagnostic['files'],inputs['dependencies']);bind({r['identity_result']['path']:r['identity_result']['sha256']})
                a.need(r['identity_result']['sha256']==ar.hashes['mmap1-identity/result.json'],'diagnostic result differs')
                before=ar.json('mmap1-measure-inputs/host-before.json');after=ar.json('endpoint-inputs/host-before.json')
                reference=ar.json('mmap1-measure-inputs/host-reference.json');activation=ar.json('mmap1-measure-inputs/pool-activation.json')
                reference_sha=ar.hashes['mmap1-measure-inputs/host-reference.json'];pool(activation,reference,reference_sha)
                activation_sha=ar.hashes['mmap1-measure-inputs/pool-activation.json']
                identity=host_identity(before)[0]
                a.need(identity==host_identity(after)[0]==host_identity(reference)[0],'host endpoints/reference differ')
                for step in ('mmap1-measure','endpoint'):
                    o=owners[step];verification=ar.json(step+'-inputs/pool-verification.json')
                    a.need(o['pool_activation_sha256']==activation_sha and o['host_reference_sha256']==reference_sha and
                           o['host_state_sha256']==ar.hashes[step+'-inputs/host-before.json'] and
                           o['pool_verification_sha256']==ar.hashes[step+'-inputs/pool-verification.json'] and
                           verification.get('completed') is True and verification.get('action')=='verify' and
                           verification.get('controller_sha256')==POOL and verification.get('mutation_attempted') is False and
                           verification.get('policy_state_unknown') is False and verification.get('final_properties')==PROPERTIES and
                           verification['activation_receipt_sha256']==activation_sha and
                           verification['captures']['after']['sha256']==o['host_state_sha256'],'phase pool binding differs')
                a.need(ep['measure_owner_sha256']==ar.hashes['mmap1-measure-controller.json'] and
                       ep['measure_result_sha256']==ar.hashes['mmap1-measure/result.json'] and
                       ep['host_before_sha256']==owner['host_state_sha256'] and
                       ep['host_after_sha256']==ar.hashes['endpoint-inputs/host-before.json'] and
                       ep['reference_sha256']==reference_sha and ep['grid_points']==42 and ep['rounds_per_point']==1 and
                       ep['strict_required'] is True and ep['arm']==arm and ep['boot_id']==boot and
                       0<=ep['capture_delay_from_child_exit_seconds']<=300 and
                       ep['capture_delay_from_child_exit_seconds']==datetime.datetime.fromisoformat(after['captured_utc']).timestamp()-owner['child_finished'],
                       'immediate strict endpoint differs')
                a.need(all(qualification(q) for q in (r['host_qualification'],owner['host_admission'],ep['comparison'],ep['comparison_to_before'])),
                       'strict qualification failed')
                topology=ar.json('mmap1-measure/topology.json');env=ar.json('mmap1-measure/environment.json')
                a.need(topology['online_cpus']==list(range(64)) and topology['role_cpus']==list(range(60)) and
                       topology['role_nodes']==[0]*32+[1]*28 and env['boot_id']==boot and env['collector_topology']['role_cpus']==[63],
                       'worker/collector topology differs')
                common=dict(host=identity,pool=activation_sha,reference=reference_sha,topology=topology,
                            environment={k:env[k] for k in ('preemption','packages','python','semantic_builder','collector_topology')})
                if cohort is None:cohort=common
                a.need(common==cohort,'new cohort/harness/runtime settings differ across arms')
                names=[f'mmap1-measure/{m}-n{n:02d}-r00/upstream.log'for m,n,_ in expected];logs=original_logs(ar,names)
                for s,name in zip(r['sessions'],names):
                    member=name.removesuffix('upstream.log')+'result.json'
                    a.need(ar.json(member)==s and s['state']=='COMPLETE' and s['passed'] is True and s['drained'] is True and
                           s['scored'] is True and s['nominal_seconds']==2 and s['instrumentation']=='none' and s['returncode']==0 and
                           s['executable_sha256']==BINARIES[s['model']],'scored point incomplete or instrumented')
                    parsed=parse(logs[name],s['workers']);a.need(parsed==s['output'],'original two-sample score differs')
                    workers=s['workers_observed'];pid=s['pid'];n=s['workers'];model=s['model']
                    a.need(len(workers)==n and len({w['tid']for w in workers})==n and
                           all(w['tid']!=pid and type(w['start_ticks']) is int and w['start_ticks']>0 and
                               w['executable']==inputs['binaries'][model] and len(w['cpus'])==1 and
                               w['tgid']==(pid if model=='threads'else w['tid']) and
                               (model=='threads' or w['ppid']==pid) for w in workers) and
                           sorted(w['cpus'][0]for w in workers)==list(range(n)) and
                           s['observation_finished_ns']-s['started_ns']<5_000_000_000,'retained worker placement differs')
                    points.append(dict(arm=label,model=model,workers=n,round=0,score=parsed['pairs_per_nominal_second'],
                         numerator=parsed['completed_pairs'],denominator=2,metric='pairs_per_nominal_second',
                         host_qualification='strict',eligibility_policy=policy.FUNCTIONAL,performance_qualified=False,
                         boot_id=boot,kernel_project_commit=kcommit,provider_comparison_commit=pcommit,
                         result_sha256=ar.hashes[member],log_sha256=ar.hashes[name],performance_accepted=False))
                grids[label]=dict(owners=e['owners'],archive=ar.provenance,kernel_binding=r['kernel_binding'],
                                  started=owner['started'],finished=owner['child_finished'],logical_members=members,eligibility=eligibility)
            a.need(grids['baseline']['finished']<=grids['candidate']['started'],'arms overlap or chronology differs')
            comparisons=[]
            for model,n,_ in [(m,n,0)for m in('threads','processes')for n in a.THREADS]:
                old=next(s for s in points if (s['arm'],s['model'],s['workers'])==('baseline',model,n))
                new=next(s for s in points if (s['arm'],s['model'],s['workers'])==('candidate',model,n))
                comparisons.append(dict(model=model,workers=n,round=0,metric='pairs_per_nominal_second',
                    baseline=old['score'],candidate=new['score'],ratio=new['score']/old['score'],change_pct=100*(new['score']/old['score']-1),
                    observed_loss=new['numerator']*old['denominator']<old['numerator']*new['denominator'],
                    baseline_boot=old['boot_id'],candidate_boot=new['boot_id'],host_qualification='strict',
                    eligibility_policy=policy.FUNCTIONAL,performance_qualified=False,performance_accepted=False))
            a.need(len(points)==84 and len(comparisons)==42,'full two-arm matrix required')
            save(x.output/'points.json',points);save(x.output/'comparisons.json',comparisons)
            save(x.output/'observed-losses.json',[r for r in comparisons if r['observed_loss']])
            for model in ('threads','processes'):
                rows=[r for r in comparisons if r['model']==model]
                with (x.output/(model+'.csv')).open('x',newline='')as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            receipt.update(completed=True,validated=True,points=84,pairs=42,grids=grids,pure_parser_sha256=parser_sha,
                pool_activation_sha256=cohort['pool'],host_reference_sha256=cohort['reference'],
                host_strict_qualified=True,strict_qualified=False,models={m:dict(pairs=21,losses=sum(r['observed_loss']for r in comparisons if r['model']==m))for m in('threads','processes')},
                no_observed_mmap_losses=not any(r['observed_loss']for r in comparisons),no_regression_evidence_gate=False,
                runner_verified_external_dependencies=dependencies,runner_verified_kernel_files=kernel_files,
                limits=['One round; no statistical or causal claim.','Unchanged application, distinct built-in kernel recipes.',
                        'Separate diagnostic proves lock class, not every timed mm address.','No timed parking/JIT instrumentation or performance acceptance.',
                        'Candidate original strict mapping failed; later functional-policy continuation is explicit.',
                        'Baseline strict receipts remain unchanged; common functional eligibility is a later interpretation.',
                        'Held-writer proof is a separate artificial interval, not the free-running observation.',
                        'Nano no-regression gate already failed; this comparison does not qualify or promote the candidate.'])
    except BaseException as error:receipt['error']=repr(error);raise
    finally:save(x.output/'validation.json',receipt)

if __name__=='__main__':main()
