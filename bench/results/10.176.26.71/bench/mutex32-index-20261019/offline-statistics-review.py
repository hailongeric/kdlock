"""Independent, data-only offline audit. Do not import retained report code."""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction
from bisect import bisect_left
import csv, datetime, hashlib, io, json, math, re, tarfile

ROOT=Path('/home/eric/vm/vm-shared/kdlock')
REPORT=ROOT/'bench/results/10.176.26.71/bench/mutex32-index-20261019'
RAW=ROOT/'bench/results/10.176.26.71/raw/bench/mutex32-index-20261019'
ARMS=('compact-rcu','precompact-256','compact-index','compact-transfer')
PLAIN,PROFILES,GROUPS=24*len(ARMS),2*len(ARMS),8*len(ARMS)
issues=[];checks=Counter();raw_bytes={};hashes={};archive_receipts={}
def sha(blob):return hashlib.sha256(blob).hexdigest()
def check(kind, condition, detail):
 checks[kind]+=1
 if not condition:issues.append(dict(check=kind,detail=detail))
def equal(kind, actual, expected, detail):
 if isinstance(actual,set):actual=sorted(actual)
 if isinstance(expected,set):expected=sorted(expected)
 if type(actual) in (int,float) and type(expected) in (int,float):
  ok=actual==expected if isinstance(actual,int) and isinstance(expected,int) else math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-15)
 else:ok=actual==expected
 check(kind,ok,detail if ok else dict(item=detail,actual=actual,expected=expected))
def js(path):return json.loads((REPORT/path).read_bytes())
def stable_id(manifest):return sha(json.dumps(manifest,sort_keys=True).encode())
def stat(numbers):
 values=sorted(numbers);n=len(values)
 middle=(values[(n-1)//2]+values[n//2])/2 if n else None
 return dict(n=n,min=values[0] if n else None,median=middle,max=values[-1] if n else None,
             spread_pct=100*(values[-1]-values[0])/middle if n and middle else None)

comparison=js('comparison.json');profile=js('profile-analysis.json')
equal('matrix_arms',comparison['arms'],list(ARMS),'four source versions in captured order')
expected_complete=(all(r['valid'] for r in comparison['sessions'])
                   and all(p['command'].get('exit_code')==0 for p in comparison['provenance'])
                   and all(g['status']=='COMPLETE' for g in comparison['comparison']))
equal('comparison_complete',comparison['complete'],expected_complete,'mixed groups remain visibly incomplete for aggregate comparison')
C={}; groups=defaultdict(list)
for row in comparison['sessions']:
 key=(row['arm'],row['collection'],row['name']);check('unique_session',key not in C,str(key));C[key]=row
 check('valid_session',row['valid'] and row['execution_status']=='OK' and row['drained'] and not row['rejection_reasons'],str(key))
 whole=float(Fraction(row['completed']*1000,row['wall_ns']))
 equal('session_whole_arithmetic',row['observed_whole_mops'],whole,str(key))
 is_profile=row['collection']=='profile';is_synthetic=row['collection'] in ('synthetic','profile')
 equal('eligibility',row['score_eligible'],not is_profile,str(key))
 equal('session_scored_rate',row['whole_mops'],None if is_profile else whole,str(key))
 equal('body_counter_semantics',row['body_counter_meaning'],'body_entries',str(key))
 equal('completion_probe',row['completion_measured'],not is_synthetic,str(key))
 equal('body_entry_share',row['measured_body_entry_share'],row['jit_bodies']/row['completed'],str(key))
 if is_synthetic:
  equal('synthetic_class',row['jit_class'],'WITNESSED_JIT',str(key))
  equal('synthetic_completion',row['jit_completions'],None,str(key))
  equal('synthetic_returned_share',row['measured_returned_jit_share'],None,str(key))
 else:
  returned=row['jit_completions'];check('api_counter_bounds',0<=returned<=row['jit_bodies']<=row['completed'],str(key))
  equal('api_class',row['jit_class'],'RETURNED_JIT' if returned else 'PARTIAL_JIT' if row['jit_bodies'] else 'NO_JIT',str(key))
  equal('api_returned_share',row['measured_returned_jit_share'],returned/row['completed'],str(key))
 if not is_profile:groups[row['arm'],row['workload'],row['threads']].append(row)
expected_groups={(arm,case,n) for arm in ARMS for case in ('c01','c08','seek-set-n16','pipebytes-query-n16') for n in (8,60)}
comparison_keys=[(r['arm'],r['workload'],r['threads']) for r in comparison['comparison']]
equal('exported_group_count',len(comparison_keys),GROUPS,'32 exported comparison groups')
equal('unique_exported_groups',len(set(comparison_keys)),len(comparison_keys),'comparison group keys')
equal('exported_group_keys',set(comparison_keys),expected_groups,'complete exported comparison matrix')
for group in comparison['comparison']:
 key=(group['arm'],group['workload'],group['threads'])
 if key not in groups:
  check('exported_group_has_sessions',False,str(key));continue
 rows=groups[key]
 classes={r['jit_class'] for r in rows};usable=rows if len(classes)==1 else []
 equal('group_repeats',sorted(r['repeat'] for r in rows),[0,1,2],str(key))
 equal('group_complete',(group['valid'],group['planned'],group['status']),(3,3,'COMPLETE' if usable else 'MIXED_EXECUTION_CLASSES'),str(key))
 for metric in ('whole_mops','peak_mops'):
  expected=stat([r[metric] for r in usable])
  for field,value in expected.items():equal('group_statistics',group[metric][field],value,str(key)+(metric,field).__str__())
 count=sum(r['completed'] for r in usable) if usable else None
 body=sum(r['jit_bodies'] for r in usable) if usable else None
 equal('group_completed',group['completed'],count,str(key));equal('group_body_count',group['measured_body_count'],body,str(key))
 equal('group_body_share',group['measured_body_entry_share'],body/count if count else None,str(key))
 returned=None if group['collection']=='synthetic' or not usable else sum(r['jit_completions'] for r in usable)
 equal('group_completion_count',group['measured_completion_count'],returned,str(key))
 equal('group_returned_count',group['measured_returned_jit_bodies'],returned,str(key))
 equal('group_returned_share',group['measured_returned_jit_share'],returned/count if returned is not None else None,str(key))
 equal('group_class',group['jit_class'],rows[0]['jit_class'] if usable else 'MIXED',str(key))
 equal('group_class_count',group['jit_classes'],dict(Counter(r['jit_class'] for r in rows)),str(key))
 equal('group_source_identity',group['source_identity'],rows[0]['source_identity'],str(key))
 equal('group_auxiliary_diagnostics',group['whole_session_auxiliary_counts'],[r['whole_session_diagnostics'].get('mutex_aux') for r in rows],str(key))
equal('matrix_sessions',len(C),PLAIN+PROFILES,'104 total');equal('matrix_plain',sum(r['score_eligible'] for r in C.values()),PLAIN,'96 plain')
equal('matrix_groups',len(groups),GROUPS,'32 groups');equal('profile_count',len(profile['profiles']),PROFILES,'8 profiles')
equal('matrix_group_keys',set(groups),expected_groups,'four workloads, two worker counts, four versions')
pipe=[r for r in comparison['comparison'] if r['collection']=='pipe']
for case,n in {(r['workload'],r['threads']) for r in comparison['comparison']}:
 matched=[r for r in comparison['comparison'] if (r['workload'],r['threads'])==(case,n)]
 classes={r['arm']:r['jit_class'] for r in matched};same=len(set(classes.values()))==1
 for row in matched:
  equal('cross_arm_classes',row['cross_arm_execution_classes'],classes,(case,n,row['arm']))
  equal('cross_arm_same_class',row['same_execution_class_across_arms'],same,(case,n,row['arm']))

# Check the full CSV key/column inventory before comparing cells. Equal row
# counts alone cannot detect a duplicate row replacing a missing result.
for name, rows, keyfields in [('comparison.csv',comparison['comparison'],('arm','workload','threads')),('sessions.csv',comparison['sessions'],('arm','collection','name'))]:
 flattened=[]
 for source in rows:
  original=dict(source)
  if name=='comparison.csv':
   for metric in ('whole_mops','peak_mops'):
    original.update({metric+'_'+k:v for k,v in original.pop(metric).items()})
  flattened.append(original)
 lookup={tuple(str(r[k]) for k in keyfields):r for r in flattened}
 expected_columns=set().union(*(set(r) for r in flattened))
 with (REPORT/name).open(newline='') as stream:
  reader=csv.DictReader(stream);columns=reader.fieldnames or [];csvrows=list(reader)
 equal('csv_row_count',len(csvrows),len(flattened),name)
 equal('csv_unique_columns',len(set(columns)),len(columns),name)
 equal('csv_columns',set(columns),expected_columns,name)
 csvkeys=[tuple(str(r.get(k)) for k in keyfields) for r in csvrows]
 equal('csv_unique_keys',len(set(csvkeys)),len(csvkeys),name)
 equal('csv_keys',set(csvkeys),set(lookup),name)
 for row,rowkey in zip(csvrows,csvkeys):
  check('csv_row_shape',None not in row and all(value is not None for value in row.values()),(name,rowkey))
  if rowkey not in lookup:
   continue
  original=lookup[rowkey]
  for key in expected_columns:
   expected=original.get(key)
   formatted='' if expected is None else json.dumps(expected,sort_keys=True) if isinstance(expected,(list,dict)) else str(expected)
   equal('csv_cell',row.get(key),formatted,(name,rowkey,key))

P={(p['arm'],p['name']):p for p in profile['profiles']};profile_totals=[]
check('profile_complete',profile.get('complete') is True,'complete profile report')
equal('unique_profiles',len(P),len(profile['profiles']),'profile identities')
equal('profile_version_workers',{(p['arm'],p['threads']) for p in P.values()},{(arm,n) for arm in comparison['arms'] for n in (8,60)},'c01 profiles')
for key,p in P.items():
 check('profile_row_complete',p.get('complete') is True and not p.get('issues'),str(key))
 session=C[p['arm'],'profile',p['name']]
 equal('profile_workload',session['workload'],'c01',str(key))
 equal('profile_source_identity',p['source_identity'],session['source_identity'],str(key))
 equal('profile_source_commit',p['source_commit'],session['source_commit'],str(key))
 rows=p['comm_symbols'];whole=sum(r['all_kernel']['observed_sum_period'] for r in rows)
 samples=sum(r['all_kernel']['samples'] for r in rows)
 worker=sum(r['all_kernel']['observed_sum_period'] for r in rows if r['comm']=='sc_worker')
 worker_samples=sum(r['all_kernel']['samples'] for r in rows if r['comm']=='sc_worker')
 equal('profile_period_total',p['denominator_all_kernel'],dict(observed_sum_period=whole,samples=samples),str(key))
 equal('profile_worker_total',p['denominator_sc_worker'],dict(observed_sum_period=worker,samples=worker_samples),str(key))
 equal('profile_samples',p['parsed_sample_lines'],samples,str(key));equal('profile_loss',p['report_lost_samples'],[0],str(key))
 equal('profile_report_period',p['report_approx_event_counts'],[whole],str(key))
 sym=defaultdict(lambda:[0,0,0,0])
 for row in rows:
  period=row['all_kernel']['observed_sum_period'];n=row['all_kernel']['samples'];isworker=row['comm']=='sc_worker'
  equal('profile_all_percent',row['all_kernel']['percent_of_denominator'],100*period/whole,str((key,row['comm'],row['symbol'])))
  equal('profile_worker_percent',row['sc_worker']['percent_of_denominator'],100*period/worker if isworker else 0,str((key,row['comm'],row['symbol'])))
  v=sym[row['symbol'],row['dso']];v[0]+=period;v[1]+=n
  if isworker:v[2]+=period;v[3]+=n
 for row in p['symbols']:
  v=sym[row['symbol'],row['dso']]
  equal('profile_symbol_sums',[row['all_kernel']['observed_sum_period'],row['all_kernel']['samples'],row['sc_worker']['observed_sum_period'],row['sc_worker']['samples']],v,str((key,row['symbol'],row['dso'])))
 for label,f in p['focus'].items():
  matched=[v for (symbol,dso),v in sym.items() if re.search(f['symbol_regex'],re.sub(r'\.(constprop|isra|part)\.\d+$','',symbol.split('+0x')[0]))]
  totals=[sum(v[i] for v in matched) for i in range(4)]
  equal('profile_focus_sums',[f['all_kernel']['observed_sum_period'],f['all_kernel']['samples'],f['sc_worker']['observed_sum_period'],f['sc_worker']['samples']],totals,str((key,label)))
  equal('profile_focus_all_percent',f['all_kernel']['percent_of_denominator'],100*totals[0]/whole,str((key,label)))
  equal('profile_focus_worker_percent',f['sc_worker']['percent_of_denominator'],100*totals[2]/worker,str((key,label)))
 profile_totals.append(dict(arm=p['arm'],threads=p['threads'],samples=samples,period=whole,worker_samples=worker_samples,worker_period=worker))
profile_sample_total=sum(p['samples'] for p in profile_totals)
check('total_profile_samples',profile_sample_total>0,'observed total; no count assumed before collection')

# Streaming raw archive inspection: retain only records/logs/manifests needed by
# this audit; hash all regular members without extracting or executing anything.
raw_available=(RAW/'archives.json').is_file();raw_sessions={};source_files=Counter();peak_reconstructions=0;raw_sample_count=0
if raw_available:
 archives=json.loads((RAW/'archives.json').read_bytes())
 wanted={'records.json','session.json','source-sha256.json','binary-sha256.json','binaries.json','plan.json','perf-samples.txt','perf-report.txt','kernel.log','comparison.json','profile-analysis.json'}
 for entry in archives['groups']:
  path=RAW/entry['file'];h=hashlib.sha256();size=0
  with path.open('rb') as stream:
   for block in iter(lambda:stream.read(1048576),b''):h.update(block);size+=len(block)
  equal('compressed_archive_hash',h.hexdigest(),entry['sha256'],entry['file']);equal('compressed_archive_size',size,entry['bytes'],entry['file'])
  archive_receipts[entry['file']]=dict(sha256=h.hexdigest(),bytes=size)
  with tarfile.open(path,mode='r|gz') as archive:
   for member in archive:
    if not member.isfile():continue
    name=member.name.split('/',1)[1] if '/' in member.name else member.name
    check('unique_regular_member',name not in hashes,name)
    keep=(Path(name).name in wanted and '/source/' not in '/'+name and '/build/' not in '/'+name)
    hasher=hashlib.sha256();parts=[]
    with archive.extractfile(member) as stream:
     for block in iter(lambda:stream.read(1048576),b''):
      hasher.update(block)
      if keep:parts.append(block)
    hashes[name]=hasher.hexdigest()
    if keep:raw_bytes[name]=b''.join(parts)
 def rjs(name):return json.loads(raw_bytes[name])
 equal('archived_comparison',hashes['comparison.json'],sha((REPORT/'comparison.json').read_bytes()),'compact/raw report binding')
 equal('archived_profiles',hashes['profile-analysis.json'],sha((REPORT/'profile-analysis.json').read_bytes()),'compact/raw profile binding')
 for provenance in comparison['provenance']:
  prefix=provenance['arm']+'/'+provenance['collection'];manifest=rjs(prefix+'/source-sha256.json')
  equal('source_manifest',manifest,provenance['source_manifest'],prefix)
  equal('source_identity',stable_id(manifest),provenance['source_identity'],prefix)
  for relative,expected in manifest.items():
   equal('frozen_source_hash',hashes[prefix+'/source/'+relative],expected,prefix+'/'+relative);source_files[prefix]+=1
  for relative,expected in provenance['input_sha256'].items():equal('provenance_input_hash',hashes[prefix+'/'+relative],expected,prefix+'/'+relative)
  records=rjs(prefix+'/records.json');plan=rjs(prefix+'/plan.json')
  equal('plan_order',[r['name'] for r in records],[r['name'] for r in plan],prefix)
  for r,spec in zip(records,plan):
   name=prefix+'/'+r['name'];key=(provenance['arm'],provenance['collection'],r['name']);out=C[key];raw_sessions[key]=r
   check('planned_identity',all(r.get(k)==v for k,v in spec.items()),name)
   saved=rjs(name+'/session.json');check('raw_session_binding',all(r.get(k)==v for k,v in saved.items()),name)
   m=r['measurement'];whole=float(Fraction(m['completed']*1000,m['wall_ns']))
   equal('raw_session_rate',out['observed_whole_mops'],whole,name)
   equal('raw_session_count',out['completed'],m['completed'],name)
   equal('raw_body_count',out['jit_bodies'],r['jit_bodies'],name)
   if provenance['collection'] in ('synthetic','profile'):
    equal('raw_entry_witness_delta',r['jit_after']-r['jit_before'],r['jit_bodies'],name)
    check('raw_completion_disabled',r['parameters']['bench_complete_probe'] in ('N','0'),name)
    if provenance['collection']=='profile':equal('raw_profile_payload',r['cachelines'],1,name)
   else:equal('raw_completion_count',out['jit_completions'],r['jit_completions'],name)
   workers=m['workers'];samples=m['samples'];deadline=min([m['deadline_ns']]+[w['kernel_finished_ns'] for w in workers]);start=max(w['active_started_ns'] for w in workers)+m['peak_settle_ns']
   eligible=[i for i,s in enumerate(samples) if s['started_ns']>=start and s['finished_ns']<=deadline]
   ends=[samples[i]['finished_ns'] for i in eligible];best=None
   for pos,i in enumerate(eligible):
    j=bisect_left(ends,samples[i]['started_ns']+m['peak_window_ns'],lo=pos+1)
    if j==len(eligible):continue
    k=eligible[j];delta=[b-a for a,b in zip(samples[i]['completed'],samples[k]['completed'])];elapsed=samples[k]['finished_ns']-samples[i]['started_ns'];rate=Fraction(sum(delta),elapsed)
    if min(delta)>0 and (best is None or rate>best[0]):best=(rate,i,k,sum(delta),elapsed,delta)
   check('raw_peak_exists',best is not None,name)
   if best:
    p=m['peak'];equal('raw_peak_selection',(p['start_sample_index'],p['end_sample_index'],p['completed'],p['elapsed_ns'],p['worker_completed']),best[1:],name)
    equal('raw_peak_rate',out['observed_peak_mops'],float(best[0]*1000),name);peak_reconstructions+=1
   log=raw_bytes[name+'/kernel.log'].decode(errors='replace')
   check('runtime_log',not re.search(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|unable to handle|general protection fault|Oops:|\[ERROR\]|invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:',log,re.I),name)
   for field,marker in (('mutex_stats','kd_mutex stats:'),('mutex_tasks','kd_mutex tasks:'),('mutex_aux','kd_mutex aux:')):
    diagnostic_lines=[l for l in log.splitlines() if marker in l]
    values={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',diagnostic_lines[-1])} if diagnostic_lines else None
    equal('raw_final_diagnostics',out['whole_session_diagnostics'].get(field),values,(name,field))
    equal('raw_final_diagnostic_lines',out['whole_session_diagnostics'].get(field+'_lines'),diagnostic_lines,(name,field))
    if field=='mutex_aux' and provenance['arm'] in ('compact-index','compact-transfer'):
     check('indexed_table_diagnostics',values is not None and values.get('slots')==65536 and values.get('bytes')==16777216,name)
     check('indexed_refusal_diagnostics',values is not None and all(type(values.get(k)) is int and values[k]>=0 for k in ('collision','busy','generation_race','exhausted','injected')),name)
 for key,p in P.items():
  prefix=p['profile_path'];text=raw_bytes[prefix+'/perf-samples.txt'].decode();rawperiod=Counter();rawcounts=Counter()
  for lineno,line in enumerate(text.splitlines(),1):
   if not line.strip() or line.lstrip().startswith('#'):continue
   check('raw_profile_no_loss','PERF_RECORD_LOST' not in line,(prefix,lineno))
   lead,tail=line.split(' cycles:k: ',1);header,period=lead.rsplit(':',1);comm,pidtid,cpu,timestamp=header.rsplit(None,3)
   ip,tail=tail.split(None,1);symbol,dso=tail.rsplit(' (',1)
   check('raw_profile_shape',pidtid.count('/')==1 and cpu.startswith('[') and cpu.endswith(']') and dso.endswith(')'),(prefix,lineno))
   period=int(period);comm=comm.strip();k=(comm,symbol,dso[:-1]);rawperiod[k]+=period;rawcounts[k]+=1;raw_sample_count+=1
  expected={(r['comm'],r['symbol'],r['dso']):(r['all_kernel']['observed_sum_period'],r['all_kernel']['samples']) for r in p['comm_symbols']}
  equal('raw_profile_weighted_rows',{k:(v,rawcounts[k]) for k,v in rawperiod.items()},expected,prefix)
  for filename,expected_hash in p['input_sha256'].items():equal('raw_profile_artifact_hash',hashes[prefix+'/'+filename],expected_hash,prefix+'/'+filename)
  lost=re.findall(r'Total Lost Samples:\s*(\d+)',raw_bytes[prefix+'/perf-report.txt'].decode());equal('raw_profile_lost',lost,['0'],prefix)
 equal('raw_session_total',len(raw_sessions),PLAIN+PROFILES,'bound sessions');equal('raw_profile_sample_total',raw_sample_count,profile_sample_total,'raw lines independently reparsed')

result=dict(schema=1,passed=not issues and raw_available,compact_statistics_passed=not issues,
 scope='Independent read-only offline data audit; no archived code, report script, benchmark, build or VM command executed.',
 checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),comparison_sha256=sha((REPORT/'comparison.json').read_bytes()),profile_analysis_sha256=sha((REPORT/'profile-analysis.json').read_bytes()),
 raw_archives_available=raw_available,archives=archive_receipts,checks=dict(checks),issues=issues,
 sessions=len(C),plain_sessions=sum(r['score_eligible'] for r in C.values()),groups=len(groups),profiles=profile_totals,profile_samples=sum(p['samples'] for p in profile_totals),
 comparison_complete=comparison['complete'],mixed_groups=sum(g['status']=='MIXED_EXECUTION_CLASSES' for g in comparison['comparison']),
 raw_bound_sessions=len(raw_sessions),independently_reconstructed_peaks=peak_reconstructions,raw_profile_samples=raw_sample_count,source_files_per_collection=dict(source_files),
 pipe=[dict(arm=r['arm'],threads=r['threads'],median_whole_mops=r['whole_mops']['median'],execution_class=r['jit_class'],same_execution_class_across_arms=r['same_execution_class_across_arms']) for r in pipe],
 method=dict(whole='Exact Fraction(completed*1000,wall_ns), then float comparison',aggregate='Independent sorted median/min/max/spread over three eligible plain sessions per source/workload/worker group',
 peak='Independent earliest eligible endpoint found by binary search; positive full-cohort windows ranked with exact rational arithmetic',profile='Independent whitespace/delimiter parsing of every raw sample, period-weighted comm/symbol/DSO sums; all-client kernel and sc_worker denominators stay separate'),
 limits=['Profiles are diagnostic; flat IP sampling has skid and no caller attribution. Profile weights are not exact cycle cost per operation.',
 'Synthetic JIT counters are entry witnesses; completion count/share are intentionally null. API explicit completions remain separate.',
 'Source versions were run sequentially; three repeats and observed ranges do not eliminate order/frequency drift or establish statistical significance.',
 'Any API JIT/NO_JIT category change remains explicit; different execution classes are not a registry-only speed comparison.',
 'Archive regular-file hashes and source/record/profile bindings are checked here; directory/symlink inventory correctness is a separate archive review.'])
(REPORT/'statistics-review.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:result[k] for k in ('passed','compact_statistics_passed','raw_archives_available','sessions','plain_sessions','groups','profile_samples','raw_bound_sessions','independently_reconstructed_peaks','raw_profile_samples','issues')},indent=2))
raise SystemExit(0 if result['passed'] else 1)
