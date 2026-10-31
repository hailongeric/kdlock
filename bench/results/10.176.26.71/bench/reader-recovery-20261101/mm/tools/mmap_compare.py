#!/usr/bin/env python3
"""Offline fresh common-policy scope3/scope4 comparison; no workload execution."""
import argparse,ast,csv,datetime,json,re,sys,tarfile,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
import nano_core as a
from fresh_controls import F7,CAND,POOL,PROPERTIES,checked,save,host_identity,pool,qualification
from policy_checks import check_policy,diagnostic_sources
RECIPE='9f9fb90e9de861fddeb498e068c0c31122919337'
MANIFEST='cf4fe6f839d49f05c0a253aa8b14cce88815c1b8c22dbf2ec7f11cecbea1b975'
CONFIG='6d950639b6b9ae30049b36fa26f88a2c584418b7bd70a2b96f8a96afb0239003'
CONTROLLER='36db793b4c354eed620d579b5689d244c6e95e99e3d43d1a6650bcaf6423942d'
ARCHIVER='56ba402cd98ac0379e47c0b8bddfa5b5cb4277c8b1367a8ed479861696dae6b0'
COORDINATOR='12652d93708db2f28b7a15f3de8b4aa061734f7165ef99589a3e2f071dc5775a'
INPUTS='beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0'
PREP='512fbd6f6855cdb109f33641d17107b629cd47a0ceea2e553c5efab6b1c4dac4'
POLICY='mmap-functional-held-writer-v1'
STEPS=('sites','api','mapping','faults','completed','strict-hold','mmap1-identity','mmap1-measure','endpoint')
BINARIES={'threads':'e6a8102ff408e0a3909248fef301a41b0b0bd07861662002e4e13833534f59c6','processes':'6ec2ac78249dd13ad201faa0a2708e176f9628d2b537d69d5ff8d584004da733'}

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

def archive_controls(ar,e,label):
 control=Path(e['control']);pins=e['expected_sha256']
 a.need(set(pins)=={'archive-owner','archive','inventory','aliases','preservation-map'} and
        pins['archive']==e['archives_sha256'] and pins['archive-owner']==e['archive_owner_sha256'],'five finalized control hashes required')
 owner=checked(control/'owner.json',pins['archive-owner']);amap=checked(control/'alias-map.json',pins['aliases'])
 preservation=checked(control/'preservation-map.json',pins['preservation-map'])
 checked(ar.directory/'input-inventory.json',pins['inventory']);c=checked(control/'config.json',CONFIG)
 bindings=checked(control/'bindings.json',owner['bindings_sha256'])
 a.need(a.file_sha(control/'controller.py')==ARCHIVER and owner.get('completed')is True and owner.get('idle')is True and
  owner.get('drain_unknown')is False and owner.get('child_returncode')==0 and owner.get('state')=='COMPLETE'and
  owner['script_sha256']==ARCHIVER and owner['arm']==label and owner['boot_id']==ar.meta['boot_id']and
  owner['kernel']==c['arms'][label]and owner['harness_commit']==RECIPE and owner['config_sha256']==CONFIG and
  owner['eligibility_policy']==POLICY and owner['performance_accepted']is False and owner['step_owners']==e['owners'],'archive control identity differs')
 a.need(owner['archives_sha256']==pins['archive']and owner['input_inventory_sha256']==pins['inventory']and
  owner['alias_map_sha256']==pins['aliases']and owner['preservation_map_sha256']==pins['preservation-map']and
  ar.hashes['preservation-inputs/alias-map.json']==pins['aliases']and ar.json('preservation-inputs/alias-map.json')==amap and
  ar.hashes['preservation-inputs/preservation-map.json']==pins['preservation-map']and ar.json('preservation-inputs/preservation-map.json')==preservation and
  ar.hashes['preservation-inputs/archive-controller.py']==ARCHIVER and ar.hashes['preservation-inputs/archive-bindings.json']==owner['bindings_sha256'],'archive/control byte linkage differs')
 a.need(bindings['schema']==1 and bindings['arm']==label and bindings['boot_id']==owner['boot_id']and
  bindings['config']['sha256']==CONFIG and bindings['owners']==e['owners']and
  ar.meta['guest_base']==c['campaign']+'/'+label and ar.meta['kernel_variant']==c['arms'][label]['variant']and
  ar.meta['kernel_release']==c['arms'][label]['release'],'archive configuration differs')
 health=ar.json(ar.meta['health_path'])
 a.need(ar.hashes[ar.meta['health_path']]==owner['final_health_sha256']and health['arm']==label and
  health['kernel']==owner['kernel']and health['step_owners']==e['owners']and health['config_sha256']==CONFIG and
  health['harness_commit']==RECIPE and health['preservation_map_sha256']==pins['preservation-map'],'archive final health differs')
 source={}
 for row in preservation['files']:
  a.need(ar.hashes.get(row['member'])==row['sha256'],'preserved original member differs')
  a.need(row['source']not in source or source[row['source']]==row['sha256'],'conflicting preserved original');source[row['source']]=row['sha256']
 for original,member in e['aliases'].items():a.need(source.get(original)==ar.hashes[member],'alias lacks exact preserved original')
 return dict(control=str(control),expected_sha256=pins,archive_owner_sha256=e['archive_owner_sha256'])

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in('inputs','trusted-checkout','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--inputs-sha256',required=True);p.add_argument('--cache-root',type=Path);x=p.parse_args()
 spec=checked(x.inputs,x.inputs_sha256);a.need(spec.get('schema')==1 and set(spec['arms'])=={'promoted','recovery'},'two fresh arms required')
 a.need(not x.output.exists(),'new analysis output required');x.output.mkdir(parents=True)
 receipt=dict(completed=False,validated=False,performance_accepted=False,inputs_sha256=x.inputs_sha256,script_sha256=a.file_sha(Path(__file__)),
              harness_commit=RECIPE,config_sha256=CONFIG,eligibility_policy=POLICY)
 save(x.output/'validation.json',receipt)
 try:
  git=a.Git(x.trusted_checkout);parse,parser_sha=parser(git)
  with tempfile.TemporaryDirectory(prefix='kd-reader-mm-',dir=x.cache_root)as tmp:
   entries=dict(spec.get('support',{}));a.need(not set(entries)&set(spec['arms']),'support/scored labels collide');entries.update(spec['arms'])
   archives={};absolute={};kernel_files={};dependencies={};configs={}
   for label,e in entries.items():
    a.need(a.safe(label)==label and'/'not in label,'simple archive label required');directory=Path(e['archives']);checked(directory/'archives.json',e['archives_sha256'])
    a.need(not x.output.resolve().is_relative_to(directory.resolve()),'output overlaps raw archive');cache=Path(tmp)/label;cache.mkdir();ar=a.Archive(directory,cache);archives[label]=ar
    for name,digest in ar.hashes.items():
     original=ar.meta['guest_base']+'/'+name;a.need(original not in absolute or absolute[original]==digest,'original archived path differs');absolute[original]=digest
    for original,member in e.get('aliases',{}).items():
     a.need(Path(original).is_absolute()and member in ar.hashes,'alias lacks retained bytes');digest=ar.hashes[member]
     a.need(original not in absolute or absolute[original]==digest,'alias changes original bytes');absolute[original]=digest
   prep_ref=spec['preparation'];pa=archives[prep_ref['archive']];inputs=pa.json(prep_ref['inputs_member']);prep=pa.json(prep_ref['result_member'])
   a.need(pa.hashes[prep_ref['inputs_member']]==INPUTS and pa.hashes[prep_ref['result_member']]==PREP and prep.get('passed')is True and
          prep.get('action')=='prepare'and prep['inputs_sha256']==INPUTS and inputs['binary_sha256']==BINARIES and inputs['executable_modified']is False,'unchanged original application preparation differs')
   for label in spec['arms']:
    ar=archives[label];e=entries[label];archive_controls(ar,e,label);c=ar.json(e['config_member']);configs[label]=c
    a.need(ar.hashes[e['config_member']]==CONFIG and c['harness']['commit']==RECIPE and c['harness']['manifest']['sha256']==MANIFEST and
           c['eligibility_policy']==POLICY and e['config_sha256']==CONFIG and e['eligibility_policy']==POLICY,'shared current config differs')
    amap=ar.json('preservation-inputs/alias-map.json')
    for key in('owners','aliases','logical_steps','config_member','bundle_member','harness_manifest_member','diagnostic_manifest_member','measurement_policy_member'):
     a.need(e[key]==amap[key],'explicit archived logical map differs: '+key)
    a.need(amap['arm']==label and amap['boot_id']==ar.meta['boot_id']and amap['config_sha256']==CONFIG and amap['eligibility_policy']==POLICY,'alias map cohort differs')
    bundle=ar.json(e['bundle_member']);arm=c['arms'][label];a.need(bundle['variant']==arm['variant'],'kernel bundle mode differs')
    for kind in('source','build'):
     for name,digest in bundle[kind+'_files'].items():
      path=bundle[kind+'_root']+'/'+name;a.need(path not in kernel_files or kernel_files[path]==digest,'kernel input alias differs')
      a.need(path not in absolute or absolute[path]==digest,'archived/kernel identity alias differs');kernel_files[path]=digest
    manifest=ar.json(e['harness_manifest_member']);a.need(ar.hashes[e['harness_manifest_member']]==MANIFEST and manifest['source_commit']==RECIPE and len(manifest['files'])==5931,'common harness differs')
    for name,row in manifest['files'].items():
     for prefix in('/root/host_fs/kdlock/',c['harness']['source']+'/'):
      path=prefix+name;a.need(path not in absolute or absolute[path]==row['sha256'],'captured common source alias differs');absolute[path]=row['sha256']
    diagnostic=diagnostic_sources(ar,e,c,git)
    for name,digest in ar.hashes.items():
     if name in diagnostic:continue
     for marker in('/runtime-source/','/source/'):
      if marker in name:
       relative=name.split(marker,1)[1]
       if relative in manifest['files']:a.need(digest==manifest['files'][relative]['sha256'],'captured common source differs: '+name)
   def bind(files,external=None):
    for name,digest in files.items():
     if name in absolute:a.need(absolute[name]==digest,'retained original binding differs: '+name)
     elif name in kernel_files:a.need(kernel_files[name]==digest,'runner kernel identity differs: '+name)
     else:a.need(external is not None and external.get(name)==digest,'unretained prerequisite: '+name);dependencies[name]=digest
   bind(inputs['files'],inputs['dependencies']);points=[];grids={};cohort=None
   for label in('promoted','recovery'):
    ar=archives[label];e=entries[label];c=configs[label];arm=c['arms'][label];bundle=ar.json(e['bundle_member']);boot=ar.meta['boot_id'];members=e['logical_steps']
    a.need(set(members)==set(e['owners'])==set(STEPS),'nine exact logical witnesses required');owners={};results={}
    for step in STEPS:
     op=members[step]['owner'];rp=members[step]['result'];owner=ar.json(op);r=ar.json(rp);owners[step]=owner;results[step]=r
     a.need(e['owners'][step]==dict(path=ar.meta['guest_base']+'/'+op,sha256=ar.hashes[op])and
            owner['result']==dict(path=ar.meta['guest_base']+'/'+rp,sha256=ar.hashes[rp])and
            owner['output']==ar.meta['guest_base']+'/'+str(Path(op).parent)and Path(rp).parent==Path(op).parent/'run','explicit logical member identity differs')
     a.need(owner.get('completed')is True and owner.get('passed')is True and owner.get('drained')is True and owner.get('final_idle')is True and
            owner.get('drain_unknown')is False and owner.get('state')=='COMPLETE'and owner['controller_sha256']==CONTROLLER and
            owner['config_sha256']==CONFIG and owner['step']==step and owner['arm']==label and owner['boot_id']==boot and owner['kernel']==arm and
            owner['harness_commit']==RECIPE and owner['harness_manifest_sha256']==MANIFEST and owner['bundle_manifest_sha256']==ar.hashes[e['bundle_member']]and
            owner['eligibility_policy']==POLICY and(step=='endpoint'or owner['child_returncode']==0),'completed same-boot action differs: '+step)
     a.need(r.get('captured')is True if step=='sites'else r.get('passed')is True and r.get('drained')is True,'runner result incomplete')
     required={'mapping':('sites','api'),'strict-hold':('sites','api','mapping'),'mmap1-measure':('api','mapping','faults','completed','strict-hold','mmap1-identity'),'endpoint':('mmap1-measure',)}.get(step,())
     a.need(set(owner['prerequisite_owners'])==set(required),'logical prerequisite set differs')
     for prior,reference in owner['prerequisite_owners'].items():a.need(reference==e['owners'][prior],'prerequisite uses another attempt')
     prefix=str(Path(op).parent/'inputs')
     a.need(ar.hashes[prefix+'/controller.py']==CONTROLLER and ar.hashes[prefix+'/config.json']==CONFIG and
            ar.hashes[prefix+'/bindings.json']==owner['bindings_sha256']and ar.hashes[prefix+'/harness-manifest.json']==MANIFEST,'executed controller inputs differ')
     bind(owner['prerequisite_bindings']);bind(r.get('files',{}),inputs['dependencies'])
     if step not in('sites','endpoint'):
      b=r['kernel_binding'];a.need(r['mode']=='kd'and r['boot_id']==boot and b['release']==arm['release']and b['variant']==arm['variant']and
       b['kernel_mmap_backend']=='kd'and b['private_backing_locks']is False and b['manifest_sha256']==ar.hashes[e['bundle_member']]and
       b['build_id']==bundle['running']['build_id']and b['runtime_policy']['mmap_mode']=='on'and r['kernel_identity']['runtime_policy_verified']is True and
       all(b[k]==bundle[k]for k in('source_files','build_files')),'compiled KD image differs')
    r=results['mmap1-measure'];owner=owners['mmap1-measure'];ep=results['endpoint'];mprefix=str(Path(members['mmap1-measure']['result']).parent)
    expected=[(m,n,0)for m in('threads','processes')for n in a.THREADS]
    a.need(r.get('state')=='COMPLETE'and r.get('action')=='measure'and r.get('final_idle')is True and r.get('single_round')is True and
     r.get('planned')==42 and r.get('accepted')is False and[(s['model'],s['workers'],s['round'])for s in r['sessions']]==expected and
     r['inputs_sha256']==INPUTS and r['binary_sha256']==BINARIES and ar.json(mprefix+'/inputs.json')==inputs,'one-round unchanged application grid differs')
    for step in('api','mapping','faults','completed','strict-hold','mmap1-identity'):a.need(results[step]['kernel_binding']==r['kernel_binding'],'same-boot check image differs')
    diagnostic=results['mmap1-identity'];adapter=diagnostic['diagnostic_runner'];iprefix=str(Path(members['mmap1-identity']['result']).parent)
    a.need(diagnostic.get('scope')=='diagnostic-class-proof'and diagnostic['inputs_sha256']==INPUTS and adapter['sha256']==c['identity_adapter']['sha256']and
      ar.hashes[iprefix+'/diagnostic-runner.py']==adapter['sha256']and adapter['source_commit']==c['identity_adapter']['commit']and
      'kd_mmap1_identity.mod.c'not in diagnostic['source_sha256'],'actual identity diagnostic differs')
    bind({r['identity_result']['path']:r['identity_result']['sha256']});a.need(r['identity_result']==owners['mmap1-identity']['result'],'identity result differs')
    policy_evidence=check_policy(ar,e,c,owners,results,bind,git)
    before_member=str(Path(members['mmap1-measure']['owner']).parent/'inputs/host-before.json');after_member=str(Path(members['endpoint']['owner']).parent/'inputs/host-before.json')
    reference_member=str(Path(members['mmap1-measure']['owner']).parent/'inputs/host-reference.json');activation_member=str(Path(members['mmap1-measure']['owner']).parent/'inputs/pool-activation.json')
    before=ar.json(before_member);after=ar.json(after_member);reference=ar.json(reference_member);activation=ar.json(activation_member)
    reference_sha=ar.hashes[reference_member];activation_sha=ar.hashes[activation_member];pool(activation,reference,reference_sha)
    identity=host_identity(before)[0];a.need(identity==host_identity(after)[0]==host_identity(reference)[0],'host endpoints/reference differ')
    for step in('mmap1-measure','endpoint'):
     o=owners[step];prefix=str(Path(members[step]['owner']).parent/'inputs');verification=ar.json(prefix+'/pool-verification.json')
     a.need(o['pool_activation_sha256']==activation_sha and o['host_reference_sha256']==reference_sha and
      o['host_state_sha256']==ar.hashes[prefix+'/host-before.json']and o['pool_verification_sha256']==ar.hashes[prefix+'/pool-verification.json']and
      verification.get('completed')is True and verification.get('action')=='verify'and verification.get('controller_sha256')==POOL and
      verification.get('mutation_attempted')is False and verification.get('policy_state_unknown')is False and verification.get('final_properties')==PROPERTIES and
      verification['activation_receipt_sha256']==activation_sha and verification['captures']['after']['sha256']==o['host_state_sha256'],'phase pool binding differs')
    a.need(ep['measure_owner']==e['owners']['mmap1-measure']and ep['measure_result']==owner['result']and ep['measurement_policy']==owner['measurement_policy']and
     ep['host_before_sha256']==owner['host_state_sha256']and ep['host_after_sha256']==ar.hashes[after_member]and ep['host_reference_sha256']==reference_sha and
     ep['grid_points']==42 and ep['rounds_per_point']==1 and ep['host_strict_qualified']is True and ep['eligibility_policy']==POLICY and ep['boot_id']==boot and
     0<=ep['capture_delay_from_child_exit_seconds']<=300 and ep['capture_delay_from_child_exit_seconds']==datetime.datetime.fromisoformat(after['captured_utc']).timestamp()-owner['child_finished'],'immediate strict endpoint differs')
    ab=ar.json('preservation-inputs/archive-bindings.json')
    sequence_ref=ab['sequence'];script_ref=ab['sequence_controller']
    bind({sequence_ref['path']:sequence_ref['sha256'],script_ref['path']:script_ref['sha256']})
    sequence=ar.json(e['aliases'][sequence_ref['path']])
    a.need(script_ref['sha256']==COORDINATOR and sequence.get('completed')is True and
     sequence.get('coordinator_sha256')==COORDINATOR and sequence['controller_sha256']==CONTROLLER and
     sequence['config_sha256']==CONFIG and sequence['arm']==label and sequence['boot_id']==boot and
     sequence['owners']==e['owners']and [z['step']for z in sequence['steps']]==list(STEPS)and
     all(z['completed']and z['owner']==e['owners'][z['step']]for z in sequence['steps']),
     'retained sequential coordinator and immediate endpoint differ')
    a.need(all(qualification(q)for q in(r['host_qualification'],owner['host_admission'],ep['comparison_to_reference'],ep['comparison_to_before'])),'strict host qualification failed')
    topology=ar.json(mprefix+'/topology.json');env=ar.json(mprefix+'/environment.json')
    a.need(topology['online_cpus']==list(range(64))and topology['role_cpus']==list(range(60))and topology['role_nodes']==[0]*32+[1]*28 and
     env['boot_id']==boot and env['collector_topology']['role_cpus']==[63],'worker/collector topology differs')
    common=dict(host=identity,pool=activation_sha,reference=reference_sha,topology=topology,
                environment={k:env[k]for k in('preemption','packages','python','semantic_builder','collector_topology')})
    if cohort is None:cohort=common
    a.need(common==cohort,'fresh pair settings differ')
    names=[f'{mprefix}/{m}-n{n:02d}-r00/upstream.log'for m,n,_ in expected];logs=original_logs(ar,names)
    for s,name in zip(r['sessions'],names):
     member=name.removesuffix('upstream.log')+'result.json';a.need(ar.json(member)==s and s['state']=='COMPLETE'and s['passed']is True and s['drained']is True and
      s['scored']is True and s['nominal_seconds']==2 and s['instrumentation']=='none'and s['returncode']==0 and s['executable_sha256']==BINARIES[s['model']],'point incomplete/instrumented')
     parsed=parse(logs[name],s['workers']);a.need(parsed==s['output'],'original two-sample score differs');workers=s['workers_observed'];pid=s['pid'];n=s['workers'];model=s['model']
     a.need(len(workers)==n and len({w['tid']for w in workers})==n and all(w['tid']!=pid and type(w['start_ticks'])is int and w['start_ticks']>0 and
      w['executable']==inputs['binaries'][model]and len(w['cpus'])==1 and w['tgid']==(pid if model=='threads'else w['tid'])and(model=='threads'or w['ppid']==pid)for w in workers)and
      sorted(w['cpus'][0]for w in workers)==list(range(n))and s['observation_finished_ns']-s['started_ns']<5_000_000_000,'retained worker placement differs')
     points.append(dict(arm=label,model=model,workers=n,round=0,score=parsed['pairs_per_nominal_second'],numerator=parsed['completed_pairs'],denominator=2,
      metric='pairs_per_nominal_second',qualification='strict-host/shared-functional-held-writer',boot_id=boot,kernel_project_commit=arm['kernel_project_commit'],
      provider_comparison_commit=arm['provider_comparison_commit'],result_sha256=ar.hashes[member],log_sha256=ar.hashes[name],performance_accepted=False))
    grids[label]=dict(archive_controls=dict(control=e['control'],expected_sha256=e['expected_sha256']),owners=e['owners'],logical_steps=members,archive=ar.provenance,kernel_binding=r['kernel_binding'],policy_evidence=policy_evidence,started=owner['started'],finished=owner['child_finished'])
   a.need(grids['promoted']['finished']<=grids['recovery']['started'],'arms overlap or chronology differs');comparisons=[]
   for model,n,_ in[(m,n,0)for m in('threads','processes')for n in a.THREADS]:
    old=next(s for s in points if(s['arm'],s['model'],s['workers'])==('promoted',model,n));new=next(s for s in points if(s['arm'],s['model'],s['workers'])==('recovery',model,n))
    comparisons.append(dict(model=model,workers=n,round=0,metric='pairs_per_nominal_second',baseline_arm='promoted',candidate_arm='recovery',baseline=old['score'],candidate=new['score'],ratio=new['score']/old['score'],change_pct=100*(new['score']/old['score']-1),
     observed_loss=new['numerator']*old['denominator']<old['numerator']*new['denominator'],baseline_boot=old['boot_id'],candidate_boot=new['boot_id'],qualification='strict-host/shared-functional-held-writer',performance_accepted=False))
   a.need(len(points)==84 and len(comparisons)==42,'full fresh two-arm matrix required');save(x.output/'points.json',points);save(x.output/'comparisons.json',comparisons)
   save(x.output/'observed-losses.json',[z for z in comparisons if z['observed_loss']]);save(x.output/'key-workers.json',[z for z in comparisons if z['workers']in(20,32,60)])
   for model in('threads','processes'):
    rows=[z for z in comparisons if z['model']==model]
    with(x.output/(model+'.csv')).open('x',newline='')as stream:
     writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
   receipt.update(completed=True,validated=True,points=84,pairs=42,grids=grids,pure_parser_sha256=parser_sha,pool_activation_sha256=cohort['pool'],host_reference_sha256=cohort['reference'],
    strict_host_qualified=True,shared_functional_policy=POLICY,models={m:dict(pairs=21,losses=sum(z['observed_loss']for z in comparisons if z['model']==m),gains=sum(z['ratio']>1 for z in comparisons if z['model']==m))for m in('threads','processes')},
    no_regression_evidence_gate=not any(z['observed_loss']for z in comparisons),runner_verified_external_dependencies=dependencies,runner_verified_kernel_files=kernel_files,
    limits=['One round; no statistical or causal claim.','Unchanged application, distinct built-in kernel recipes.','Both arms use fresh common functional mapping plus separate artificial held-writer proof.',
            'Original application preparation contributes bytes only; no historical timing/eligibility substitution.','No timed parking/JIT instrumentation or automatic acceptance.'])
 except BaseException as error:receipt['error']=repr(error);raise
 finally:save(x.output/'validation.json',receipt)
if __name__=='__main__':main()
