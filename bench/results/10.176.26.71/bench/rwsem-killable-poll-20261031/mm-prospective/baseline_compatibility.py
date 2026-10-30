#!/usr/bin/env python3
"""Read verified baseline archive data and emit a separate policy interpretation."""
import argparse,datetime,hashlib,json,pathlib,re,subprocess,tarfile
ARM='baseline-f7-scope1-kd'
BOOT='43101fa8-697a-46ad-99c9-be4b39cce0b3'
INDEX='4fa34c365caad5c5288dfef9fce5cd8d95273153c144697014a75fa565c91e92'
ARM_SHA='5fdd9a14cd9dbbd7689e4e3d865335916d0d4e29b9543c184cf6239c9578a2b6'
OWNER='affbb198d73dbdb589a0e08b5b39dbdcabe40056b84b310aa789221c7440c6f0'
RESULT='2f6cb7a6f1d198156510314a68dab4e678abb8b4104f7c39129468080ba9e2e0'
RECIPE='f4ae82cfdf053c679c5d09ee8e503a7919764c9b'
MUTANTS=['different_lock','wrong_caller_return','wrong_wait_return','wrong_adapter_return','running_task','other_wait_channel','rescheduled_task','missing_chain','missing_writer_proof']
PLAN=[('00-scope-1','scope',1,1),('01-cycle-1','cycle',1,1000),('02-cycle-16','cycle',16,5000),('03-lifetime-1','lifetime',1,1),('04-lifetime-16','lifetime',16,1),('05-exit-1','exit',1,1)]
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--trusted-checkout',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);x=p.parse_args()
 need(not x.output.exists(),'new interpretation path required')
 armbytes=(x.baseline/'analysis-arm.json').read_bytes();need(sha(armbytes)==ARM_SHA,'baseline arm descriptor changed');arm=json.loads(armbytes);directory=pathlib.Path(arm['archives']);ib=(directory/'archives.json').read_bytes();need(sha(ib)==INDEX,'original baseline index changed');index=json.loads(ib)
 tb=(x.baseline/'transfer.json').read_bytes();transfer=json.loads(tb);need(transfer['completed'] and transfer['archive_members_verified'] and transfer['analysis_arm_sha256']==ARM_SHA,'full archived baseline validation missing')
 member=json.loads((x.baseline/'member-sha256.json').read_bytes());need(sha((x.baseline/'member-sha256.json').read_bytes())==transfer['member_manifest_sha256'],'verified member manifest changed')
 wanted={'mapping-controller.json','mapping/result.json','mapping/02-cycle-16.jsonl','mapping/writer-sites.json','mmap1-measure-controller.json','mmap1-measure/result.json'};data={};groups={}
 for group in index['groups']:
  if group['group'] not in ('checks','metadata','mmap1'):continue
  archive=directory/group['file'];need(sha(archive.read_bytes())==group['sha256'],'original archive bytes changed')
  with tarfile.open(archive,'r:gz') as t:
   for entry in t:
    name=entry.name.removeprefix(ARM+'/')
    if name not in wanted:continue
    need(name not in data and entry.isfile(),'duplicate/nonregular interpretation input');b=t.extractfile(entry).read();need(sha(b)==member[name],'original member changed');data[name]=b;groups[name]={'archive':group['file'],'archive_sha256':group['sha256'],'member_sha256':sha(b)}
 need(set(data)==wanted,'missing original interpretation input')
 owner=json.loads(data['mapping-controller.json']);result=json.loads(data['mapping/result.json']);sites=json.loads(data['mapping/writer-sites.json']);measure_owner=json.loads(data['mmap1-measure-controller.json']);measure=json.loads(data['mmap1-measure/result.json'])
 need(sha(data['mapping-controller.json'])==OWNER and sha(data['mapping/result.json'])==RESULT and owner['result_sha256']==RESULT,'strict mapping identity changed')
 need(owner['completed'] and owner['passed'] and owner['drained'] and owner['final_idle'] and not owner['drain_unknown'] and owner['boot_id']==BOOT and owner['arm']==ARM,'original strict owner incomplete')
 need(result['passed'] and result['drained'] and result['source_unchanged'] and result['boot_id']==BOOT and result['mode']=='kd' and result['delegated'] is False and result['jit_bodies']==0,'original strict result incomplete')
 need(result.get('eligibility_policy','mmap-writer-proof-v1')=='mmap-writer-proof-v1','baseline is not original strict policy')
 cases=result['cases'];need([(c['name'],c['mode'],c['threads'],c['iterations'])for c in cases]==PLAN,'original six-case plan changed')
 for c in cases:
  need(c['passed'] and c['completion']['passed'] and c.get('eligibility_policy','mmap-writer-proof-v1')=='mmap-writer-proof-v1' and c['protocol']=='KD_LOCAL_MMAP_LOCK' and c['delegated'] is False,'case policy/verdict changed')
  need(all(o['faults']==o['context_errors']==0 and o['maps']+o['clones']==o['closes']+o['vmas'] for o in c['observations']),'functional callback conservation failed')
  if c['mode'] in ('cycle','lifetime'):
   z=c['completion'];need(z['joined']==len(z['workers'])==c['threads'] and z['completed']==c['threads']*c['iterations'],'joins/progress differ')
   need(all(w['errors']==0 and w['completed']==c['iterations'] and all(w[k]==c['identity'][k]for k in('object','mm','mmap_lock','tgid'))for w in z['workers']),'worker identity/errors differ')
 cycle=cases[2];need(cycle['rejected_mutations']==MUTANTS,'original positive-proof mutations differ')
 raw=[json.loads(line)for line in data['mapping/02-cycle-16.jsonl'].decode().splitlines()];stacks=[r for r in raw if r.get('event')=='writer_stack'];need(len(stacks)==1,'original positive stack missing');stack=stacks[0];chain=sites['chains']['kd'];need(stack['proof']=='EXACT_MMAP_WRITER_CHAIN' and stack['mm']==cycle['identity']['mm'] and stack['mmap_lock']==cycle['identity']['mmap_lock'],'original same-object writer witness differs')
 need(stack['tid']in{w['tid']for w in cycle['completion']['workers']} and stack['acquire']==sites['adapter'] and stack['caller']in sites['sites'],'writer identity/caller differs')
 frames=[(name,int(offset,16))for name,offset in re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/',stack['raw_stack'])];expected=[(chain['waiter'],stack['wait_return_offset'])]
 if chain['waiter']!=sites['adapter']:expected.append((sites['adapter'],chain['adapter_return']))
 expected.append((stack['caller'],sites['sites'][stack['caller']]['return_offset']))
 need(stack['waiter']==chain['waiter'] and stack['wait_return_offset']in chain['wait_returns'] and stack['adapter_return_offset']==chain['adapter_return'] and stack['return_offset']==expected[-1][1] and frames[:len(expected)]==expected,'original exact linked chain differs')
 need(stack['state_before']==stack['state_after']=='D' and stack['wchan_before']==stack['wchan_after']==chain['waiter'] and stack['schedstat_before']==stack['schedstat_after'],'original sleeping-writer bracket differs')
 need(measure_owner['passed'] and measure_owner['drained'] and measure['passed'] and measure['drained'] and measure['boot_id']==BOOT and measure['single_round'] and len(measure['sessions'])==42,'original unchanged timing incomplete')
 source={}
 for path in ('bench/mmap_lock/eligibility.py','tests/kernel/mmap_writer/run.py','tests/kernel/mmap_lock/mapping.py','bench/mmap_writer/linux70.py','bench/mmap1/run.py'):
  b=subprocess.check_output(['git','-C',str(x.trusted_checkout),'show',RECIPE+':'+path]);source[path]=sha(b)
 record=dict(schema=1,kind='baseline-strict-functional-compatibility',baseline_arm=ARM,baseline_boot_id=BOOT,interpretation_policy='mmap-functional-v1',original_policy='mmap-writer-proof-v1',original_policy_was_implicit_default='eligibility_policy'not in result,original_receipts_unchanged=True,timing_reused_without_modification=True,mapping_owner_sha256=OWNER,mapping_result_sha256=RESULT,six_cases_validated=True,writer_observation='observed',rejected_mutations=MUTANTS,compatible=True,performance_qualified=False,performance_accepted=False,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),builder_sha256=sha(pathlib.Path(__file__).read_bytes()),harness_commit=RECIPE,harness_source_sha256=source,archive_index_sha256=INDEX,analysis_arm_sha256=ARM_SHA,full_archive_verification_receipt_sha256=sha(tb),original_members=groups,common_checks=['Six original strict cases passed and drained in the same KD boot','Exact worker mm/lock/object identity, joins and per-worker completion','Zero worker errors and zero fault/context errors','Map/clone/close/VMA conservation','Actual sleeping-writer chain and stable scheduler bracket','All nine positive-observation mutations rejected','Original unchanged 42-point one-round mmap1 result retained'],cases=[dict(name=c['name'],policy='mmap-writer-proof-v1',passed=c['passed'],checks=c['completion']['checks'],completed=c['completion'].get('completed'),joined=c['completion'].get('joined'))for c in cases],validation_basis='Retained strict VM verdicts plus source-host structural/hash checks; no VM rerun or rewritten receipt',new_test_executed=False,measurement_repeated=False,limits=['Later functional-policy interpretation, not a new baseline run or retroactive policy change','Does not pass or erase the candidate original strict failure','Does not establish candidate correctness, performance qualification or acceptance'])
 x.output.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n');print(json.dumps({'path':str(x.output),'sha256':sha(x.output.read_bytes()),'compatible':True,'new_test_executed':False}))
if __name__=='__main__':main()
