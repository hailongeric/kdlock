#!/usr/bin/env python3
"""Offline receipt arithmetic/hash audit; never loads captured Python or runs tests."""
import argparse,hashlib,json,pathlib,re,subprocess,tarfile,tempfile
HERE=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive',type=pathlib.Path,required=True)
parser.add_argument('--repo',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,default=HERE/'verification.json')
args=parser.parse_args()
REPO=args.repo.resolve();OUT=args.output.parent
meta=json.loads((HERE/'receipt-archive.json').read_text())
if hashlib.sha256(args.archive.read_bytes()).hexdigest()!=meta['sha256']:
 raise ValueError('receipt archive SHA256 differs')
TEMP=tempfile.TemporaryDirectory(prefix='kdlock-proxy-receipts-')
BASE=pathlib.Path(TEMP.name);R=BASE/'receipts'
# Extract only regular receipts to a private directory; never import captured code.
with tarfile.open(args.archive,'r:gz') as archive:
 for member in archive:
  name=pathlib.PurePosixPath(member.name)
  if not member.isfile() or name.is_absolute() or '..' in name.parts or name.parts[0]!='receipts':
   raise ValueError('unexpected receipt member '+member.name)
  path=BASE/pathlib.Path(*name.parts)
  if path.exists():raise ValueError('duplicate receipt '+member.name)
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(archive.extractfile(member).read())
BOOT='677b7afa-5358-4ece-a650-5f4a4adecd55'
BUILD='b61c7bef25d2068f2a05ca3c31a5714c20c4aa62'
BASIC='0ef4e92bea5db63b9201c3dd24310cbd6929d928'
def read(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def require(v,why):
 if not v: raise ValueError(why)
def identity(i):
 require(i['ok'] and i['schema']==2 and i['runtime_policy_verified'],'kernel identity flags')
 require(i['running_build_id']==BUILD,'kernel Build ID')
 require(i['runtime_policy']['preempt']=='lazy','runtime preempt policy')
fetch=read(HERE/'fetch-verification.json')
for row in fetch['sha256']:
 p=R/row['path'];require(p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],str(p))
require(len(fetch['sha256'])==fetch['files']==1921,'fetch count')
result={'completed':False,'scope':'Offline receipt/hash/source-manifest audit, not test execution or new binary authentication',
 'archive_sha256':meta['sha256'],
 'fetch':{'files':fetch['files'],'bytes':fetch['bytes'],'manifest_sha256':digest(HERE/'fetch-verification.json')},
 'boot_id':BOOT,'kernel_build_id':BUILD,'attempts':[],'source_manifests':[],'live':[],'basic':[],
 'limits':['Versions and instrumented call shells are separate; no performance claim.',
 'Raw images/ELFs are represented by captured hashes; complete bulk archives are outside this receipt audit.',
 'Context mixed-IF phase is stress only, not deterministic mismatched-pair proof.',
 'Native CALL live coverage is a mutex root and fixed Native spin target; borrowed owner, no role swap or arbitrary JIT re-entry.']}
commits={}
for p in sorted(R.glob('*/owner.json')):
 d=read(p);require(d['boot_id']==BOOT,str(p));root=p.parent.name
 commit=subprocess.check_output(['git','rev-parse',d['source_commit']+'^{commit}'],cwd=REPO,text=True).strip();commits[root]=commit
 blocks=[{'name':b.get('name',b.get('family')),'returncode':b['returncode']} for b in d['blocks']]
 if d['completed']: require(all(b['returncode']==0 for b in blocks),'completed block failed')
 log=p.parent/'unit.log';totals=[]
 if log.exists(): totals=[list(map(int,x)) for x in re.findall(r'Unit tests: (\d+) passed, (\d+) failed',log.read_text())]
 result['attempts'].append({'root':root,'source_commit':commit,'completed':d['completed'],'unit_driver_totals':totals,'blocks':blocks})
commits['kernel-proxy-calls-basic-20261030']=BASIC
expected_units={
 'kernel-proxy-marker-unit-20261030':[9,1], 'kernel-proxy-ordering-unit-20261030':[9,1],
 'kernel-proxy-ordering-r3-unit-20261030':[3,0], 'kernel-proxy-context-unit-20261030':[5,2],
 'kernel-proxy-context-r2-unit-20261030':[3,1], 'kernel-proxy-context-r3-unit-20261030':[3,0],
 'kernel-proxy-context-live-20261030':[3,0], 'kernel-proxy-context-live-r2-20261030':[3,0],
 'kernel-proxy-calls-unit-20261030':[13,1], 'kernel-proxy-calls-r2-unit-20261030':[3,0],
 'kernel-proxy-profile-unit-20261030':[6,0], 'kernel-proxy-native-call-live-20261030':[5,0],
 'kernel-proxy-native-call-live-r2-20261030':[3,0]}
for attempt in result['attempts']:
 if attempt['root'] in expected_units:
  require(attempt['unit_driver_totals']==[expected_units[attempt['root']]],'unit driver totals '+attempt['root'])
require('Ran 7 tests' in (R/'kernel-proxy-profile-unit-20261030/mm-platform.log').read_text(),'MM platform case count')
failed_context=read(R/'kernel-proxy-context-live-20261030/probe/session/session.json')
require(failed_context['retired']==dict(state=2,modules=0,frames=0,writers=0),'failed context cleanup')
# Authenticate every captured source-manifest path against its declared Git version.
queries={}
tracked={c:set(subprocess.check_output(['git','ls-tree','-r','--name-only',c],cwd=REPO,text=True).splitlines()) for c in set(commits.values())}
for p in sorted(R.rglob('source-sha256.json')):
 c=commits[p.relative_to(R).parts[0]]
 for path,sha in read(p).items():
  if path in tracked[c]: queries[c+':'+path]=sha
proc=subprocess.Popen(['git','cat-file','--batch'],cwd=REPO,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
blobs={}
for spec in queries:
 proc.stdin.write((spec+'\n').encode());proc.stdin.flush()
 head=proc.stdout.readline().decode().split();require(len(head)==3 and head[1]=='blob','missing Git blob '+spec)
 data=proc.stdout.read(int(head[2]));require(proc.stdout.read(1)==b'\n','batch framing')
 blobs[spec]=hashlib.sha256(data).hexdigest()
proc.stdin.close();require(proc.wait()==0,'git cat-file')
for p in sorted(R.rglob('source-sha256.json')):
 c=commits[p.relative_to(R).parts[0]];m=read(p)
 generated=[x for x in m if x not in tracked[c]]
 mismatches=[x for x,h in m.items() if x not in generated and blobs[c+':'+x]!=h]
 require(not mismatches,'source mismatch '+str(p)+str(mismatches))
 result['source_manifests'].append({'path':str(p.relative_to(R)),'commit':c,'recorded_files':len(m),'git_verified_files':len(m)-len(generated),'nontracked_snapshot_paths_not_Git_verified':generated,'sha256':digest(p)})
result['source_manifest_unique_blobs']=len(blobs)

def audit_live(root,arm,kind):
 base=R/root/arm;s=read(base/'session/session.json');env=read(base/'environment.json')
 require(env['boot_id']==BOOT and env['snapshot_tag']=='linux70-kdlock1-clean-20261027','environment')
 identity(s['kernel_identity']);require(s['accepted'] and s['drained'] and s['execution_status']=='OK','live accepted')
 require(s['retired']==dict(state=2,modules=0,frames=0,writers=0),'live retirement')
 require(s['cpus']==list(range(16)),'worker pins')
 pub=s['publication'];require(pub['entry']['status']==0 and pub['source']==dict(state=0,modules=1,frames=0,writers=1),'publication')
 phases=[];total={};hotpids=set()
 for p in s['phases']:
  require(p['complete'] and p['returncodes']==[0]*16,'phase result')
  require(len(p['workers'])==16 and len(p['callers'])==16,'worker count')
  for w in p['workers']:
   require(w['completed']==w['iterations'] and w['errors']==0 and w['cpu']==w['worker'],'worker effects')
  for c in p['callers']: require(c['pid']>0,'caller PID')
  after,before=p['after'],p['before'];n=sum(w['completed'] for w in p['workers'] if w.get('role','writer')=='writer')
  require(after['active']==0 and after['idle']==1 and after['failures']==0,'phase idle/effects')
  require(after['prefix']-before['prefix']==n and after['suffix']-before['suffix']==n,'prefix/suffix exact')
  require(p['source_after']==dict(state=0,modules=1,frames=0,writers=1),'phase source')
  require(p['registry_before']==p['registry_after']==s['image_registry'],'registry unchanged')
  for k,v in pub['entry'].items(): require(s['image_registry'][0][k]==v,'publication/registry')
  delta=p['jit_delta'];require(all(delta[k]==p['counters_after'][k]-p['counters_before'][k]>=0 for k in delta),'counter delta')
  for k,v in delta.items():total[k]=total.get(k,0)+v
  ent,complete=delta['bench_jit_bodies'],delta['bench_jit_completions']
  if kind!='context':
   require(p['write_operations']==n and p['read_operations']==sum(w['completed'] for w in p['workers'] if w.get('role')=='reader'),'operation totals')
   require(after['taken' if kind=='call' else 'hot_taken']-before['taken' if kind=='call' else 'hot_taken']==(n if p['hot'] else 0),'taken effects')
   if p['hot']:
    hotpids.update(c['pid'] for c in p['callers'] if c.get('role')=='writer')
    key='native_call_probe_count' if kind=='call' else 'native_escape_count'
    require(ent==delta[key]>0 and complete==0,'native phase counts')
   else: require(ent==complete>0 and delta['native_call_probe_count' if kind=='call' else 'native_escape_count']==0,'cold returned JIT')
   if kind=='call':
    require(delta['native_escape_count']==0,'CALL not instruction escape')
    require(all(delta[k]==delta['native_call_probe_count'] for k in ['native_started','native_completed','native_unlocks']),'native ACK totals')
  else:
   require(ent==complete and delta['address_guard_count']==0,'context returned count')
   local=p['name'] in ['bh-local','rcu-local','preempt-local','migration-local']
   require((ent==0) if local else (ent>0),'context local/delegated mode')
   require(not p['context_oracle']['mismatch_refusal_proved'],'mixed IF scope')
  phases.append({'name':p['name'],'operations':n,'read_operations':p.get('read_operations',0),'jit_entries':ent,'jit_completions':complete,'deltas':delta})
 for k,n in total.items():
  require(s['phases'][-1]['counters_after'][k]-s['phases'][0]['counters_before'][k]==n,'phase counter sum')
  if k in s['final_parameters']: require(int(s['final_parameters'][k])-int(s['initial_parameters'][k])==n,'session counter sum')
 if kind=='marker':
  require([p['name'] for p in phases]==['cold-warmup','cold-delegated','hot-escape','cold-after-escape','hot-repeat'],'marker sequence')
  require(pub['entry']['generation']==1,'immutable generation')
  for e in s['escape_events']:
   require(e['entry']==s['layout']['entry'] and e['rip']==s['layout']['marker'] and e['generation']==1 and e['waiter_pid'] in hotpids,'marker event')
  require(len(s['escape_events'])>0,'marker event evidence')
  log=(base/'session/kernel.log').read_text();require('action=native_suffix_keep_eligible' in log,'marker action')
 if kind=='call':
  require([p['name'] for p in phases]==['cold-warmup','cold-delegated','taken-native','cold-after-native','taken-repeat'],'CALL sequence')
  require(s['capabilities']['version']==12 and s['capabilities']['features'] & (1<<12),'CALL capability')
  require(pub['entry']['generation']==1 and s['entry_abi']==2,'CALL ABI')
  require(s['native_totals']==dict(started=total['native_started'],completed=total['native_completed'],unlocks=total['native_unlocks']),'final native totals')
  reason='NATIVE_CALL_TERMINAL' if arm=='direct' else 'INDIRECT_CALL_NATIVE'
  for e in s['call_events']:
   require(e['reason']==reason and e['entry']==s['layout']['entry'] and e['target']==s['layout']['native_target'] and e['lock']==s['layout']['lock_address'] and e['sp']>0 and e['hostcall']==0 and e['task'] in hotpids and e['return_ip']==s['layout']['call_site']+s['call_audit']['length'],'exact CALL event')
  require(len(s['call_events'])>0,'CALL events')
 result['live'].append({'root':root,'arm':arm,'kind':kind,'source_commit':commits[root],'phase_count':len(phases),'phases':phases,'publication':pub,'event_samples':len(s.get('call_events',s.get('escape_events',[]))),'retired':s['retired']})
for arm in ['mutex','spin','rwlock','rwsem']:audit_live('kernel-proxy-marker-live-20261030',arm,'marker')
audit_live('kernel-proxy-context-live-r2-20261030','probe','context')
for arm in ['direct','indirect']:audit_live('kernel-proxy-native-call-live-r2-20261030',arm,'call')
basic=read(R/'kernel-proxy-calls-basic-20261030/result.json');require(basic['passed'] and basic['final_idle'] and not basic['performance_accepted'] and not basic['timing_started'],'basic scope')
require(basic['boot_id']==BOOT,'basic boot');identity(basic['kernel_identity'])
for row in basic['results']:
 p=R/pathlib.Path(row['receipt']).relative_to(fetch['remote_base']);require(digest(p)==row['receipt_sha256'],'basic receipt hash')
 s=read(p);require(s['drained'] and s['execution_status']=='OK' and s['retired']==dict(state=2,modules=0,frames=0,writers=0),'basic drain')
 require(s['jit_bodies']==s['jit_completions']==row['jit_completions']>0,'basic JIT')
 m=s['measurement'];require(m['complete'] and m['data_ok'] and m['completed']==row['operations']==1600000,'basic data')
 require(all(w['error'] in (0,None) and w.get('read_errors',0)==0 and w['completed']==100000 and w['cpu']==w['observed_cpu'] for w in m['workers']),'basic workers')
 result['basic'].append(row)
result['completed']=True
OUT.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'completed':True,'fetched_files':fetch['files'],'source_manifests':len(result['source_manifests']),'unique_Git_blobs':len(blobs),'live_sessions':len(result['live']),'live_phases':sum(r['phase_count'] for r in result['live']),'basic_sessions':len(result['basic'])}))
