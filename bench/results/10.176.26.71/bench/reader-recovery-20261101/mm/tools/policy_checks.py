"""Shared current mapping/held-writer evidence; no historical eligibility reuse."""
import re
from pathlib import Path
import nano_core as a
POLICY='mmap-functional-held-writer-v1'
PLAN=[('00-scope-1','scope',1,1),('01-cycle-1','cycle',1,1000),('02-cycle-16','cycle',16,5000),('03-lifetime-1','lifetime',1,1),('04-lifetime-16','lifetime',16,1),('05-exit-1','exit',1,1)]
MUTATIONS=['different_lock','wrong_caller_return','wrong_wait_return','wrong_adapter_return','running_task','other_wait_channel','rescheduled_task','missing_chain','missing_writer_proof']
def diagnostic_sources(ar,e,c,git):
 m=ar.json(e['diagnostic_manifest_member']);d=c['strict_diagnostic'];prefix=str(Path(e['logical_steps']['strict-hold']['result']).parent)
 a.need(ar.hashes[e['diagnostic_manifest_member']]==d['manifest']['sha256']and m['commit']==d['commit']and
        set(m['files'])=={'README.md','run.py','payload/Makefile','payload/api.h','payload/client.c','payload/module.c'},'six diagnostic leaves required')
 exact=set()
 for leaf,digest in m['files'].items():
  a.need(digest==a.sha(git.blob(d['commit'],'tests/kernel/mmap_writer/strict_hold/'+leaf)),'diagnostic Git source differs')
  for member in(prefix+'/source/'+leaf,'preservation-inputs/diagnostic-source/'+leaf):
   a.need(ar.hashes.get(member)==digest,'captured diagnostic source differs: '+member);exact.add(member)
 return exact

def strict_chain(stack,target,operation,sites):
 chain=sites['chains']['kd']
 a.need(stack['proof']=='EXACT_MMAP_WRITER_CHAIN'and stack['tid']==target['tid']and stack['mm']==target['mm']and
        stack['mmap_lock']==target['mmap_lock']and stack['caller']==('vm_mmap_pgoff'if operation=='mmap'else'__vm_munmap')and
        stack['acquire']==sites['adapter'],'held writer exact object/caller differs')
 frames=[(name,int(offset,16))for name,offset in re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/',stack['raw_stack'])]
 expected=[(chain['waiter'],stack['wait_return_offset'])]
 for index,frame in enumerate(chain.get('intermediate',[]),1):
  a.need(len(frames)>index and frames[index][0]==frame['symbol']and frames[index][1]in frame['return_offsets'],'held intermediate frame differs');expected.append(frames[index])
 if chain['waiter']!=sites['adapter']:expected.append((sites['adapter'],chain['adapter_return']))
 expected.append((stack['caller'],sites['sites'][stack['caller']]['return_offset']))
 a.need(stack['waiter']==chain['waiter']and stack['wait_return_offset']in chain['wait_returns']and
        stack['adapter_return_offset']==chain['adapter_return']and stack['return_offset']==expected[-1][1]and frames[:len(expected)]==expected and
        stack['state_before']==stack['state_after']=='D'and stack['wchan_before']==stack['wchan_after']==chain['waiter']and
        stack['schedstat_before']==stack['schedstat_after']and len(stack['schedstat_before'].split())==3 and
        all(v.isdigit()for v in stack['schedstat_before'].split()),'held exact sleeping chain differs')

def check_policy(ar,e,c,owners,results,bind,git):
 members=e['logical_steps']
 if c['harness']['commit']=='9f9fb90e9de861fddeb498e068c0c31122919337':
  api=results['api'];q=api['queue_observation'];prefix=str(Path(members['api']['result']).parent)
  expected={p:a.sha(git.blob(c['harness']['commit'],p))for p in('kernel_module/kd_mutex_local.c','tests/kernel/mmap_lock/payload/gate_waiter_layout.h')}
  a.need(q==dict(schema=1,kinds=['reader-phase','writer-gate','reader-drain'],gate_source_sha256=expected['kernel_module/kd_mutex_local.c'],
         gate_layout_sha256=expected['tests/kernel/mmap_lock/payload/gate_waiter_layout.h'],singleton_task_checked_under_wait_lock=True,
         cancellation_holder_checked_before_release=True),'fresh API exact queue observation differs')
  source=ar.json(prefix+'/source-sha256.json')
  a.need(all(source[p]==h==ar.hashes[prefix+'/source/'+p]for p,h in expected.items()),'API queue layout source correspondence differs')
 mapping=results['mapping'];policies={x[0]:'mmap-functional-v1'if x[0]=='02-cycle-16'else'mmap-writer-proof-v1'for x in PLAN}
 a.need(mapping.get('eligibility_policy')=='mmap-functional-v1'and mapping.get('performance_qualified')is False and
        mapping.get('source_unchanged')is True and mapping.get('case_policies')==policies and
        [(z['name'],z['mode'],z['threads'],z['iterations'])for z in mapping['cases']]==PLAN and
        all(z.get('passed')is True and z.get('eligibility_policy')==policies[z['name']]for z in mapping['cases']),'six shared-policy mapping cases differ')
 cycle=mapping['cases'][2];observed=mapping['writer_observation']
 a.need(observed in('observed','inconclusive')and cycle.get('writer_observation')==observed and cycle['completion'].get('functional_complete')is True,'mapping observation differs')
 a.need((cycle.get('rejected_mutations')==MUTATIONS and cycle.get('mutation_checks_status')=='passed-positive-observation')if observed=='observed'else
        (cycle.get('rejected_mutations')==[]and cycle.get('mutation_checks_status')=='not-applicable-no-positive-observation'),'mapping observation/mutations relabeled')
 mprefix=str(Path(members['mapping']['result']).parent);adapter=c['mapping_adapter']
 a.need(mapping['external_runner']['sha256']==adapter['sha256']and mapping['external_runner']['base_harness_commit']==c['harness']['commit']and
        mapping['external_runner']['base_mapping_sha256']==adapter['base_mapping_sha256']and ar.hashes[mprefix+'/executed-runner.py']==adapter['sha256'],'executed mapping adapter differs')
 strict=results['strict-hold'];sprefix=str(Path(members['strict-hold']['result']).parent);d=c['strict_diagnostic']
 a.need(strict.get('diagnostic')=='same-mm-held-writer-v1'and strict.get('final_idle')is True and strict.get('source_unchanged')is True and
        strict.get('timing')is False and strict.get('accepted')is False and strict.get('mode')=='kd'and
        strict['boot_id']==ar.meta['boot_id']and strict['harness_commit']==c['harness']['commit']and
        strict['harness_manifest_sha256']==c['harness']['manifest']['sha256']and strict['diagnostic_commit']==d['commit']and
        strict['diagnostic_manifest_sha256']==d['manifest']['sha256']and strict['kernel_binding']==results['mmap1-measure']['kernel_binding']and
        strict['api_result_sha256']==ar.hashes[members['api']['result']]and strict['writer_sites_sha256']==ar.hashes[members['sites']['result']],'fresh held-writer source/boot differs')
 text=git.blob(c['harness']['commit'],'bench/mmap_writer/client.c').decode();pieces=[]
 for start,end in(('static void json_string(','static int proc_text('),('static char task_state(','/* Called only after successful joins')):
  a.need(text.count(start)==text.count(end)==1 and text.index(start)<text.index(end),'classifier extraction bounds differ');pieces.append(text[text.index(start):text.index(end)])
 source=a.sha(text.encode());extracted=a.sha(''.join(pieces).encode());cl=strict['classifier']
 expected_functions=['json_string','task_state','chain_frame','writer_chain_tail','writer_observation','writer_contention']
 if d['commit']=='31d3bc28d55abcab3f8af379a0e57c6e80d7d399':expected_functions.insert(2,'chain_wait_arguments')
 a.need(cl.get('source_sha256')==source and cl.get('extracted_sha256')==extracted and cl.get('changed_bodies')is False and
        cl.get('functions')==expected_functions and
        ar.hashes[sprefix+'/source/payload/classifier.inc']==extracted and ar.hashes[sprefix+'/frozen-classifier-source/bench/mmap_writer/client.c']==source,'held classifier differs')
 bind(strict['files']);a.need([z['operation']for z in strict['cases']]==['mmap','munmap'],'both held syscall witnesses required');sites=results['sites']
 for index,case in enumerate(strict['cases'],1):
  target=case['target'];observer=case['observer'];done=case['completion']
  a.need(case.get('passed')is True and case['rejected_mutations']==MUTATIONS and case['health']==f'files=0 mm_refs=0 active=0 errors=0 objects={index}'and
         target['mm']and target['mmap_lock']and target['object']and target['tgid']==target['tid']and target['use_kd']==1 and
         observer['mm']and observer['mm']!=target['mm']and observer['tgid']==observer['tid']and observer['tgid']!=target['tgid']and
         done['passed']is True and done['mm']==target['mm']and done['mmap_lock']==target['mmap_lock']and done['target_tid']==target['tid']and
         done['holder_tid']not in(0,target['tid'],observer['tid'])and done['acquired']==done['unlocked']==done['joined']==1 and done['timed_out']==done['errors']==0,'held ownership/retirement differs')
  strict_chain(case['writer_stack'],target,case['operation'],sites)
 p=ar.json(e['measurement_policy_member']);measure=owners['mmap1-measure']
 a.need(measure['measurement_policy']==dict(path=ar.meta['guest_base']+'/'+e['measurement_policy_member'],sha256=ar.hashes[e['measurement_policy_member']])and
        p['schema']==1 and p['harness_commit']==c['harness']['commit']and p['harness_manifest_sha256']==c['harness']['manifest']['sha256']and
        p['boot_id']==ar.meta['boot_id']and p['kernel']==owners['mmap1-measure']['kernel']and p['eligibility_policy']==POLICY and
        p['measurement_result']==measure['result']and p['mapping_owner']==e['owners']['mapping']and p['strict_hold_owner']==e['owners']['strict-hold']and
        p['mapping_result']==owners['mapping']['result']and p['strict_hold_result']==owners['strict-hold']['result']and
        p['mapping_policy']=='mmap-functional-v1'and p['incidental_writer_observation']==observed and p['held_writer_policy']=='same-mm-held-writer-v1'and
        p['fresh_same_boot_witnesses']is True and p['host_strict_qualified']is True and p['raw_measurement_changed']is False and
        p['measurement_repeated']is False and p['performance_accepted']is False,'unchanged raw measurement/shared policy differs')
 return dict(policy=POLICY,incidental_writer_observation=observed,strict_syscalls=2,strict_negative_controls=18,
             scope='Same shared prospective policy; artificial held intervals are separate from scored execution',performance_accepted=False)
