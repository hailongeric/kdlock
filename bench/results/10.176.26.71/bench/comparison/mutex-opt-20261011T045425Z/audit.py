"""Read-only evidence audit: screening stages and the final mutex-only matrix."""
import argparse, collections, importlib.util, json, re, shutil
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args(); root=a.root.resolve(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('helpers',Path(__file__).with_name('matrix-audit-helpers.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
counts=collections.Counter(); samples=[]; diagnoses=[]; failures=[]; groups=[]
final=root/'final-66'
state=json.loads((final/'matrix-status.json').read_text())
assert state['state']=='COMPLETE' and state['expected_sessions']==396
assert state['threads']==e.THREADS and state['worker_cpus']==[*range(32),*range(33,65)] and state['collector_cpu']==65
approved=json.loads((root/'final-source-approved.json').read_text())
folders=sorted({x.parent for x in root.glob('*/plan.json')}|{x.parent for x in final.glob('*/plan.json')})
for folder in folders:
    name=folder.relative_to(root).as_posix(); is_final=folder.parent==final
    plan=json.loads((folder/'plan.json').read_text())
    if (folder/'failure.json').exists(): failures.append(dict(group=name,failure=json.loads((folder/'failure.json').read_text())))
    info=dict(group=name,planned=len(plan),executed=0,accepted=0,statuses=collections.Counter(),topology_vcpus=66 if is_final else 64)
    source=folder/'source-sha256.json'
    if not source.exists():
        assert (folder/'failure.json').exists()
        assert not any((folder/r['name']/'session.json').exists() for r in plan)
        info['statuses']['BUILD_FAILED_BEFORE_FREEZE']=len(plan);groups.append(info);continue
    for rel,sha in json.loads(source.read_text()).items():
        assert e.digest(folder/'source'/rel)==sha,(name,rel)
        if is_final and rel in approved:assert approved[rel]==sha,('approved source',name,rel)
        counts['source_hashes']+=1
    for original,sha in json.loads((folder/'binary-sha256.json').read_text()).items():
        _,mark,rel=original.partition('/'+folder.name+'/')
        path=folder/rel if mark else folder/'binaries'/Path(original).name
        assert e.digest(path)==sha,path
        counts['binary_hashes']+=1
    identity_file=folder/'diagnostic-identity.json'
    if identity_file.exists():
        identity=json.loads(identity_file.read_text())
        assert e.digest(folder/'diagnostic-driver.py')==identity['driver_sha256']
        counts['diagnostic_driver_hashes']+=1
        if 'perf_sha256' in identity:
            assert e.digest(folder/'binaries/perf-diagnostic')==identity['perf_sha256']
            counts['diagnostic_perf_hashes']+=1
    configurations=set()
    for planned in plan:
        path=folder/planned['name']; file=path/'session.json'
        if not file.exists():
            info['statuses']['NOT_RUN']+=1;continue
        original=json.loads(file.read_text()); row=original
        original_status=row.get('execution_status','NOT_RUN')
        info['statuses'][original_status]+=1
        if original_status in ('NOT_RUN',None):continue
        info['executed']+=1
        recovery=None
        if not row.get('drained'):
            assert name=='packet-prefetch-stalls' and original_status=='MEASURING' and not row.get('performance_result',True),(name,row['name'])
            recovery='parser-recovery-2'
            row=json.loads((path/recovery/'session.json').read_text())
            assert row['execution_status']=='DIAGNOSTIC_PARSER_FAILED' and row['drained'] and row['jit_bodies']>0
            assert row['name']==original['name'] and row['published_before']==original['published_before']
        assert row['drained'] is True,(name,row['name'])
        assert row['lock_kind']=='mutex' and row['workload'] in ('cacheline','rcuht') and row['cachelines'] in (0,1)
        configs=(row['workload'],row['cachelines'],row['threads'],row['arm'],row['repeat'])
        assert configs not in configurations,(name,configs)
        configurations.add(configs)
        if is_final:
            assert row['cpus']==state['worker_cpus'][:row['threads']] and row['collector_cpu']==65
            assert row['cpu_nodes']==[0 if cpu<32 else 1 for cpu in row['cpus']]
        else:
            assert row['collector_cpu']==63
        if row['arm']=='kdlock':
            assert row['published_before']==row['published_after']
            assert row['retired']==dict(state=2,modules=0,frames=0,writers=0)
            publication=row['published_before']
            if publication:
                entry=publication['entry']; images=path/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
                for image,sha in publication['images'].items():
                    assert e.digest(images/image)==sha,(name,row['name'],image)
                    counts['jit_image_hashes']+=1
        logs=[path/'kernel.log']+([path/recovery/'kernel.log'] if recovery else [])
        text='\n'.join(f.read_text() for f in logs if f.exists())
        assert not re.search(r'BUG:|WARNING:|Oops:|general protection fault|kernel panic|KASAN:|UBSAN:',text,re.I),(name,row['name'])
        m=row.get('measurement',{})
        raw=json.loads((path/'measure.json').read_text())
        assert all(m.get(k)==v for k,v in raw.items()),('raw client',name,row['name'])
        assert m['complete'] and m['data_ok']
        assert all(w['completed']>0 for w in m['workers'])
        if m.get('peak',{}).get('throughput_ops_s',0)>0:
            e.independently_check_peak(row);counts['independent_peaks']+=1
        if not row.get('performance_result',True) or row.get('measurement_mode')=='functional':
            d=dict(group=name,name=row['name'],status=row['execution_status'],original_status=original_status,
                   drained=True,recovery=recovery,jit_bodies=row.get('jit_bodies'),lost_samples=row.get('lost_samples'),completed=m['completed'])
            if (path/'perf-report.txt').exists():
                report=(path/'perf-report.txt').read_text()
                lost=re.search(r'Total Lost Samples: ([0-9]+)',report)
                assert lost and int(lost[1])==0,(name,row['name'])
                d['lost_samples']=0
                header=(path/'perf-header.txt').read_text()
                fields=re.search(r'sample_type = ([A-Z_|]+)',header)
                assert fields
                d['actual_sample_type']=fields[1]
                if recovery:
                    assert set(fields[1].split('|'))=={'IP','TID','TIME'}
                    assert '100003' in header
                    d['actual_fixed_period']=100003
                else:assert set(fields[1].split('|'))=={'IP','TID','TIME','PERIOD'}
                counts['zero_loss_profiles']+=1
            if (path/'perf-stat.csv').exists():
                counters={}
                for line in (path/'perf-stat.csv').read_text().splitlines():
                    if not line or line.startswith('#'):continue
                    fields=line.split(';');assert float(fields[4])==100
                    counters[fields[2]]=int(fields[0])
                d['counters']=counters;d['per_completed_op']={k:v/m['completed'] for k,v in counters.items()}
            diagnoses.append(d);continue
        if e.accepted(row):info['accepted']+=1
        else:assert row['execution_status']=='NO_JIT' and row['arm']=='kdlock' and row['jit_bodies']==0
        result=e.sample(name,row)
        result['topology_vcpus']=info['topology_vcpus']
        diagnostics=[dict((k,int(v)) for k,v in re.findall(r'([a-z_]+)=([0-9]+)(?= |$)',line)) for line in re.findall(r'kd_mutex stats: [^\n]+',text)]
        result['lifetime_combiner_count']=sum(d.get('combiner',0) for d in diagnostics)
        result['lifetime_jit_success']=sum(d.get('jit_success',0) for d in diagnostics)
        result['lifetime_jit_bodies_per_combiner']=result['lifetime_jit_success']/result['lifetime_combiner_count'] if result['lifetime_combiner_count'] else None
        result['min_worker_peak_ops']=min(m['peak']['worker_completed'])
        result['min_worker_whole_ops']=min(w['completed'] for w in m['workers'])
        result['peak_node_share']={k:v/sum(result['peak_node_completed'].values()) for k,v in result['peak_node_completed'].items()}
        samples.append(result)
    if is_final:
        payload='cacheline' if folder.name.endswith('c01') else 'rcuht';lines=1 if payload=='cacheline' else 0
        expected={(payload,lines,t,arm,r) for t in e.THREADS for arm in e.ARMS for r in range(3)}
        assert configurations==expected and len(plan)==198,(name,len(configurations))
    groups.append(info)

buckets=collections.defaultdict(list); separated=collections.defaultdict(list)
for row in samples:
    key=(row['group'],row['write_percent'],row['threads'],row['arm'])
    buckets[key].append(row);separated[key+(row['execution_type'],)].append(row)
statistics=[e.aggregate(key,rows) for key,rows in buckets.items()]
by_execution=[e.aggregate(key[:4],rows,key[4]) for key,rows in separated.items()]
final_samples=[r for r in samples if r['group'].startswith('final-66/')]
assert len(final_samples)==396
final_stats=[r for r in statistics if r['group'].startswith('final-66/')]
comparisons=[]; points=collections.defaultdict(dict)
for row in final_stats:points[(row['group'],row['threads'])][row['arm']]=row
for (group,t),arms in points.items():
    row=dict(group=group,threads=t,status='INCOMPLETE')
    if set(arms)==set(e.ARMS) and all(r['complete'] for r in arms.values()):
        for arm in ('native','tclock'):
            for metric in ('best_peak_ops_s','whole_median_ops_s'):
                row[f'kd_over_{arm}_{metric}']=arms['kdlock'][metric]/arms[arm][metric]
        row['descriptive_status']='PASS' if all(v>=1 for k,v in row.items() if k.startswith('kd_over_')) else 'FAIL'
        row['status']='MIXED_EXECUTION' if arms['kdlock']['execution_type']=='MIXED' else row['descriptive_status']
    comparisons.append(row)
for name,rows in [('samples',samples),('statistics',statistics),('statistics-by-execution',by_execution),('final-samples',final_samples),('final-statistics',final_stats),('comparison',comparisons),('diagnostics',diagnoses)]:
    e.csv_write(out/(name+'.csv'),rows);e.json_write(out/(name+'.json'),rows)
verification=dict(groups=groups,checks=dict(counts),timed_sessions=len(samples),accepted=sum(r['accepted'] for r in samples),
    final_sessions=len(final_samples),final_accepted=sum(r['accepted'] for r in final_samples),
    final_kd_jit=sum(r['accepted'] and r['arm']=='kdlock' and r['jit_bodies']>0 for r in final_samples),
    final_kd_no_jit=sum(r['accepted'] and r['arm']=='kdlock' and r['jit_bodies']==0 for r in final_samples),
    diagnostics=len(diagnoses),failures=failures,
    final_multithread_statuses=dict(collections.Counter(r['status'] for r in comparisons if r['threads']>1)))
e.json_write(out/'verification.json',verification)
e.json_write(out/'environment.json',dict(matrix_status=state,groups={p.name:json.loads((p/'environment.json').read_text()) for p in final.iterdir() if p.is_dir() and (p/'environment.json').exists()}))
for name in ('audit.py','matrix-audit-helpers.py'):
    src=Path(__file__).with_name(name);dest=out/name
    if src.resolve()!=dest.resolve():shutil.copyfile(src,dest)
print(json.dumps({k:v for k,v in verification.items() if k not in ('groups','failures')}),flush=True)
