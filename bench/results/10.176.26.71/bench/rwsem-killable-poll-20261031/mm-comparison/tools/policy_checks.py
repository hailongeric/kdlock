"""Explicit prospective correctness-policy evidence; no source execution."""
import re
import nano_core as a
STRICT='mmap-writer-proof-v1'
FUNCTIONAL='mmap-functional-v1'
OLD_CONTROLLER='2d22529f3871946c1b40b1e0028411072d095a3d69bb13ac9b629b0845213758'
MAPPING_CONTROLLER='fc1c0d78d3d4d0872defe877d890fd046bed82fc758de6dc2f3a87af858678dd'
MAPPING_RUNNER='1dbf545b3ecfdca1956584ca7f9784c30975ae74d4972b962817f4b4bbb1d16f'
COMPATIBILITY='00ad3bc9873a2c75c37b4d1b2059d3253bb778057ee9b23894d66663e17e0247'
FAILED_OWNER='71568d5f8374b7cd8e90119cf56aebd150334a91d98be09ac69675779548df2e'
FAILED_RESULT='284e2cbffc95a2c56f9d23b768646ed774b6143de0d3f537e27fcee526ae23c2'
PRESERVATION='16561602201b33c7eeaac746b36008846539caf4a3f6bc8d705e61d0857c9f14'
MUTATIONS=['different_lock','wrong_caller_return','wrong_wait_return','wrong_adapter_return','running_task','other_wait_channel','rescheduled_task','missing_chain','missing_writer_proof']
PLAN=[('00-scope-1','scope',1,1),('01-cycle-1','cycle',1,1000),('02-cycle-16','cycle',16,5000),('03-lifetime-1','lifetime',1,1),('04-lifetime-16','lifetime',16,1),('05-exit-1','exit',1,1)]
LOGICAL_MAPPING={'owner':'mapping-functional-controller.json','result':'mapping-functional/result.json'}

def mapping(result,owner,archive):
    policies={row[0]:FUNCTIONAL if row[0]=='02-cycle-16'else STRICT for row in PLAN}
    a.need(result.get('eligibility_policy')==owner.get('eligibility_policy')==FUNCTIONAL and
           result.get('performance_qualified') is False and owner.get('performance_qualified') is False and
           result.get('performance_accepted') is False and result.get('source_unchanged') is True and
           result.get('case_policies')==policies and
           [(c['name'],c['mode'],c['threads'],c['iterations'])for c in result['cases']]==PLAN,
           'prospective six-case policy differs')
    a.need(all(c.get('passed') is True and c.get('eligibility_policy')==policies[c['name']]for c in result['cases']),
           'prospective case did not pass its declared policy')
    cycle=result['cases'][2];observed=result.get('writer_observation')
    a.need(observed in('observed','inconclusive') and owner.get('writer_observation')==observed and
           cycle.get('writer_observation')==observed and cycle['completion'].get('functional_complete') is True,
           'prospective free-running observation missing')
    if observed=='observed':
        a.need(cycle.get('rejected_mutations')==MUTATIONS and cycle.get('mutation_checks_status')=='passed-positive-observation',
               'positive observation mutations missing')
    else:
        a.need(cycle.get('rejected_mutations')==[] and cycle.get('mutation_checks_status')=='not-applicable-no-positive-observation',
               'inconclusive observation relabeled as a positive proof')
    a.need(result['external_runner']['sha256']==owner['functional_runner_sha256']==MAPPING_RUNNER and
           archive.hashes['mapping-functional/executed-runner.py']==MAPPING_RUNNER,
           'executed functional runner identity differs')
    return observed

def strict_chain(stack,target,operation,sites):
    chain=sites['chains']['kd']
    a.need(stack['proof']=='EXACT_MMAP_WRITER_CHAIN' and stack['tid']==target['tid'] and
           stack['mm']==target['mm'] and stack['mmap_lock']==target['mmap_lock'] and
           stack['caller']==('vm_mmap_pgoff'if operation=='mmap'else'__vm_munmap') and
           stack['acquire']==sites['adapter'],'held writer object/caller differs')
    frames=[(name,int(offset,16))for name,offset in re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/',stack['raw_stack'])]
    expected=[(chain['waiter'],stack['wait_return_offset'])]
    if chain['waiter']!=sites['adapter']:expected.append((sites['adapter'],chain['adapter_return']))
    expected.append((stack['caller'],sites['sites'][stack['caller']]['return_offset']))
    a.need(stack['waiter']==chain['waiter'] and stack['wait_return_offset']in chain['wait_returns'] and
           stack['adapter_return_offset']==chain['adapter_return'] and stack['return_offset']==expected[-1][1] and
           frames[:len(expected)]==expected and stack['state_before']==stack['state_after']=='D' and
           stack['wchan_before']==stack['wchan_after']==chain['waiter'] and
           stack['schedstat_before']==stack['schedstat_after'] and len(stack['schedstat_before'].split())==3 and
           all(x.isdigit()for x in stack['schedstat_before'].split()),'held writer exact sleeping chain differs')

def compatibility(record,archive,baseline):
    a.need(archive.hashes['mmap1-measure-inputs/baseline-compatibility.json']==COMPATIBILITY,
           'exact baseline compatibility record differs')
    a.need(record.get('schema')==1 and record.get('kind')=='baseline-strict-functional-compatibility' and
           record.get('baseline_arm')=='baseline-f7-scope1-kd' and record.get('baseline_boot_id')==baseline.meta['boot_id'] and
           record.get('interpretation_policy')==FUNCTIONAL and record.get('original_policy')==STRICT and
           record.get('original_receipts_unchanged') is True and record.get('timing_reused_without_modification') is True and
           record.get('six_cases_validated') is True and record.get('writer_observation')=='observed' and
           record.get('rejected_mutations')==MUTATIONS and record.get('compatible') is True and
           record.get('performance_qualified') is False and record.get('performance_accepted') is False and
           record.get('new_test_executed') is False and record.get('measurement_repeated') is False and
           record['mapping_owner_sha256']==baseline.hashes['mapping-controller.json'] and
           record['mapping_result_sha256']==baseline.hashes['mapping/result.json'] and
           record['archive_index_sha256']==a.file_sha(baseline.directory/'archives.json'),
           'baseline compatibility changes original strict evidence')
    for name,row in record['original_members'].items():
        a.need(baseline.hashes[name]==row['member_sha256'],'baseline compatibility member differs')

def prospective(ar,baseline,results,owners,members,bind,git,controller,diagnostic_commit,observed):
    record=ar.json('mmap1-measure-inputs/baseline-compatibility.json')
    compatibility(record,ar,baseline)
    failed=ar.json('mapping-controller.json');failed_result=ar.json('mapping/result.json')
    a.need(ar.hashes['mapping-controller.json']==FAILED_OWNER and ar.hashes['mapping/result.json']==FAILED_RESULT and
           failed.get('state')=='FAILED' and failed.get('completed') is False and failed.get('passed') is False and
           failed.get('drained') is False and failed.get('drain_unknown') is True and
           failed_result.get('passed') is False and failed_result.get('drained') is False,
           'original strict failure was replaced or relabeled')
    preserved_members=[name for name,digest in ar.hashes.items()if digest==PRESERVATION]
    a.need(preserved_members,'actual failed-arm preservation receipt missing')
    preserved=ar.json(sorted(preserved_members)[0])
    a.need(preserved.get('completed') is True and preserved.get('state')=='FAILED_ARM_ARCHIVED_IDLE' and
           preserved.get('actual_idle') is True and preserved.get('drain_unknown') is False and
           preserved.get('failed_flags_unchanged') is True and preserved.get('canonical_paths_changed') is False and
           preserved.get('boot_id')==ar.meta['boot_id'] and
           preserved.get('controller_sha256')=='8452a6abeecc658b95169c3374b8d31febe59b231da067678285080897e5b5e4',
           'post-failure preservation identity differs')
    bind({preserved['archive']:preserved['archive_sha256']})
    strict=ar.json('strict-hold/result.json');manifest=ar.json('strict-hold/diagnostic-manifest.json')
    manifest_sha='ea057985c5dc0443b54e2e279c01ad76581e7f82416f448abcdddc30771b201a'
    a.need(ar.hashes['strict-hold/diagnostic-manifest.json']==manifest_sha and
           manifest.get('commit')==diagnostic_commit and
           set(manifest['files'])=={'README.md','run.py','payload/Makefile','payload/api.h','payload/module.c','payload/client.c'},
           'reviewed strict diagnostic manifest differs')
    for leaf,digest in manifest['files'].items():
        a.need(digest==a.sha(git.blob(diagnostic_commit,'tests/kernel/mmap_writer/strict_hold/'+leaf)) and
               ar.hashes['strict-hold/source/'+leaf]==digest,'strict diagnostic source differs from reviewed commit')
    a.need(strict.get('schema')==1 and strict.get('diagnostic')=='same-mm-held-writer-v1' and
           strict.get('state')=='COMPLETE' and strict.get('passed') is True and strict.get('drained') is True and
           strict.get('final_idle') is True and strict.get('source_unchanged') is True and strict.get('timing') is False and
           strict.get('accepted') is False and strict.get('boot_id')==ar.meta['boot_id'] and strict.get('mode')=='kd' and
           strict.get('harness_commit')=='f4ae82cfdf053c679c5d09ee8e503a7919764c9b' and
           strict.get('diagnostic_commit')==diagnostic_commit and strict.get('diagnostic_manifest_sha256')==manifest_sha and
           strict['kernel_binding']==results['mmap1-measure']['kernel_binding'] and
           strict['api_result_sha256']==ar.hashes['api/result.json'] and
           strict['writer_sites_sha256']==ar.hashes['sites/writer-sites.json'],
           'separate same-boot strict diagnostic incomplete or different')
    cls=strict['classifier'];source='ffdb744d0b8c6c62474d3bb7f9c79db66091acbb1b83600fc78105aeb84a4679';extracted='5784c48ed920131bab044390e46ae2df533f80d1a9d023f4b945c95056362693'
    a.need(cls.get('source_sha256')==source and cls.get('extracted_sha256')==extracted and
           cls.get('changed_bodies') is False and cls.get('functions')==['json_string','task_state','chain_frame','writer_observation','writer_contention'] and
           ar.hashes['strict-hold/source/payload/classifier.inc']==extracted and
           ar.hashes['strict-hold/frozen-classifier-source/bench/mmap_writer/client.c']==source,
           'strict classifier bytes differ')
    bind(strict['files'])
    a.need([c['operation']for c in strict['cases']]==['mmap','munmap'],'both strict syscall witnesses required')
    sites=ar.json('sites/writer-sites.json')
    for i,case in enumerate(strict['cases'],1):
        target=case['target'];observer=case['observer'];done=case['completion']
        a.need(case.get('passed') is True and case['rejected_mutations']==MUTATIONS and
               case['health']==f'files=0 mm_refs=0 active=0 errors=0 objects={i}' and
               target['mm'] and target['mmap_lock'] and target['object'] and target['tgid']==target['tid'] and target['use_kd']==1 and
               observer['mm'] and observer['mm']!=target['mm'] and observer['tgid']==observer['tid'] and observer['tgid']!=target['tgid'] and
               done['passed'] is True and done['mm']==target['mm'] and done['mmap_lock']==target['mmap_lock'] and
               done['target_tid']==target['tid'] and done['holder_tid']not in(0,target['tid'],observer['tid']) and
               done['acquired']==done['unlocked']==done['joined']==1 and done['timed_out']==done['errors']==0,
               'separate strict holder ownership/mutations/retirement differ')
        strict_chain(case['writer_stack'],target,case['operation'],sites)
    mp=ar.json('measurement-policy.json');ms=ar.hashes['measurement-policy.json']
    fields=dict(eligibility_policy=FUNCTIONAL,performance_qualified=False,performance_accepted=False,
        mapping_step='mapping-functional',mapping_owner_sha256=ar.hashes[members['mapping']['owner']],
        mapping_result_sha256=ar.hashes[members['mapping']['result']],writer_observation=observed,
        strict_hold_result=mp['strict_hold_result'],strict_hold_result_sha256=ar.hashes['strict-hold/result.json'],
        strict_hold_diagnostic_commit=diagnostic_commit,strict_hold_diagnostic_manifest_sha256=manifest_sha,
        baseline_compatibility_sha256=COMPATIBILITY,original_failed_mapping_owner_sha256=FAILED_OWNER,
        original_failed_mapping_result_sha256=FAILED_RESULT,failed_arm_preservation_sha256=PRESERVATION)
    a.need(mp.get('schema')==1 and mp.get('kind')=='prospective-mmap-functional-measurement-policy' and
           mp.get('arm')=='candidate-22d-scope2-kd' and mp.get('boot_id')==ar.meta['boot_id'] and
           mp.get('controller_sha256')==controller and mp.get('original_measurement_result_unchanged') is True and
           mp.get('raw_measurement_result_sha256')==ar.hashes['mmap1-measure/result.json'] and
           all(mp.get(k)==v and owners['mmap1-measure'].get(k)==v and owners['endpoint'].get(k)==v for k,v in fields.items()) and
           owners['mmap1-measure']['measurement_policy_sha256']==owners['endpoint']['measurement_policy_sha256']==ms and
           results['endpoint']['measurement_policy_sha256']==ms and results['endpoint']['eligibility_policy']==FUNCTIONAL and
           results['endpoint']['performance_qualified'] is False,'measurement/endpoint policy does not bind actual raw evidence')
    bind({mp['strict_hold_result']:fields['strict_hold_result_sha256']})
    a.need(ar.hashes['mmap1-measure-inputs/strict-hold-result.json']==fields['strict_hold_result_sha256'] and
           ar.hashes['endpoint-inputs/strict-hold-result.json']==fields['strict_hold_result_sha256'] and
           ar.hashes['endpoint-inputs/baseline-compatibility.json']==COMPATIBILITY,
           'copied prospective prerequisites differ')
    return dict(original_strict_failure_retained=True,original_strict_failure_sha256=FAILED_RESULT,
        prospective_policy=FUNCTIONAL,free_running_writer_observation=observed,
        strict_hold_scope='Separate artificial held interval; not a free-running or timing observation',
        strict_hold_result_sha256=fields['strict_hold_result_sha256'],baseline_compatibility_sha256=COMPATIBILITY,
        measurement_policy_sha256=ms,performance_qualified=False,performance_accepted=False)
