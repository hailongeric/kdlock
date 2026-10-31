from pathlib import Path
import csv
import math
import nano_core as a
from archive_helpers import apply_exact_patch
from fresh_controls import save

def provider_audit(archive, git, out, commit):
    expected = git.source_hashes(commit)
    frozen = archive.json('source-sha256.json')
    a.need(frozen == expected, 'current source snapshot differs from exact selected Git set; review extras separately')
    production = {n:v for n,v in frozen.items() if n.startswith(('include/','kernel_module/'))
                  and (Path(n).suffix in ('.c','.inc','.h','.S','.def') or Path(n).name == 'Makefile')
                  and not n.endswith('.mod.c')}
    prefix = 'bench/spin_cacheline/provider/'
    patched, hunks = apply_exact_patch(git.blob(commit,prefix+'observation.patch'),git,commit)
    a.need(len(hunks) == 26 and len(patched) == 12, 'current observation overlay shape changed')
    prepared = production | {n:a.sha(data) for n,data in patched.items()} | {
        'kernel_module/kd_bench.c':frozen[prefix+'kd_bench.c'],
        'include/kd_bench.h':frozen[prefix+'kd_bench.h']}
    providers, wanted = [], {}
    commands = {n:archive.text(n) for n in archive.saved if n.endswith('.cmd') and '/build/' in n}
    for profile in a.PROFILES:
        directory = profile+'/build/provider/'
        manifest = archive.json(directory+'manifest.json')
        a.need(manifest.get('complete') is True and manifest.get('kind') == 'spin_cacheline private provider',
               'prepared provider incomplete: '+profile)
        a.need(manifest['production'] == production and manifest['prepared'] == prepared and
               manifest['observation'] == {n:frozen[prefix+n] for n in ('observation.patch','kd_bench.c','kd_bench.h')},
               'provider is not exact Git plus reviewed observation overlay: '+profile)
        a.need(all(archive.hashes.get(directory+n) == digest for n,digest in prepared.items()),
               'prepared provider bytes differ: '+profile)
        for name in ('.kdlock_km.o.cmd','.kd_spin_runtime.o.cmd','.kd_api_provider.o.cmd','.sys.o.cmd','.kd_bench.o.cmd'):
            a.need(directory+'kernel_module/'+name in commands, 'missing compile/link receipt: '+name)
        runtime = commands[directory+'kernel_module/.kd_spin_runtime.o.cmd']
        a.need(all(name in runtime for name in ('kd_mutex.c','kd_spinlock.c','exe.c','mutex/origin_instruction.inc')),
               'runtime dependency receipt omits actual instruction-service source')
        providers.append(dict(profile=profile,manifest_sha256=archive.hashes[directory+'manifest.json'],
                              production_files=len(production),prepared_files=len(prepared)))
        for path,digest in archive.json(profile+'/binary-sha256.json').items():
            if path.endswith('.ko'):
                name = archive.relative(path)
                a.need(archive.hashes.get(name) == digest and name not in wanted, 'module binary map differs')
                wanted[name] = digest
    records = {name:dict(sha256=digest, modinfo=archive.modinfo[name], executed=False)
               for name,digest in wanted.items()}
    a.need(sum(n.endswith('/kdlock_km.ko') for n in records) == 10, 'ten measured provider ELFs required')
    save(out/'elf-provenance.json',records)
    result = dict(source_commit=commit,tracked_source_blobs=len(expected),extra_source_files={},
                  provider_preparation=providers,exact_patch_hunks=hunks,
                  dependency_receipts={n:archive.hashes[n] for n in commands},
                  authenticated_module_elfs=len(records),authenticated_provider_elfs=10,
                  scope='Actual archived module bytes; no requirement to equal the earlier unit-build ELF')
    save(out/'provider-audit.json',result)
    return result

def compare(reference, current):
    a.need(reference['boot_id'] == current['boot_id'] and
           reference['kernel_identity'] == current['kernel_identity'] and
           reference['kernel_bundle_sha256'] == current['kernel_bundle_sha256'] and
           reference['host_fixed_identity'] == current['host_fixed_identity'],
           'cross-campaign kernel/topology/fixed-host identity differs')
    a.need(reference['finished'] <= current['started'] or current['finished'] <= reference['started'], 'campaigns overlap')
    rows = []
    for family,lines,percent in a.PROFILES.values():
        for workers in a.THREADS:
            key = (family,lines,percent,workers,'kdlock')
            old,new = reference['rows'][key],current['rows'][key]
            a.need(old['matched_fields'] == new['matched_fields'], 'KD workload/shell/settings mismatch: '+repr(key))
            metrics = {}
            for metric in ('whole','peak'):
                ratio = new[metric+'_ops_s']/old[metric+'_ops_s']
                loss = (new[metric+'_numerator']*old[metric+'_denominator_ns'] <
                        old[metric+'_numerator']*new[metric+'_denominator_ns'])
                metrics[metric] = dict(ratio=ratio,change_pct=100*(ratio-1),observed_loss=loss)
            rows.append(dict(lock_kind=family,workload=f'c{lines:02d}',cachelines=lines,
                write_percent=percent,threads=workers,repeat=0,rounds_per_point=1,
                reference_commit=reference['commit'],current_commit=current['commit'],
                reference_kd=old,current_kd=new,metrics=metrics,
                execution_transition=old['execution_class']+' -> '+new['execution_class'],
                score_eligible=old['score_eligible'] and new['score_eligible'],
                any_observed_loss=any(m['observed_loss'] for m in metrics.values()),performance_accepted=False))
    a.need(len(rows) == 210, 'expected all210 KD coordinates in each independent comparison')
    return rows

def write_comparison(out, reference, current):
    out.mkdir()
    rows = compare(reference,current)
    losses = [r for r in rows if r['any_observed_loss']]
    save(out/'points.json',rows)
    save(out/'observed-losses.json',losses)
    columns = ['lock_kind','workload','write_percent','threads','repeat','rounds_per_point',
        'reference_commit','current_commit','reference_whole_ops_s','current_whole_ops_s',
        'reference_peak_ops_s','current_peak_ops_s','whole_change_pct','peak_change_pct',
        'whole_observed_loss','peak_observed_loss','any_observed_loss','reference_execution',
        'current_execution','score_eligible','reference_provider_sha256','current_provider_sha256',
        'reference_workload_sha256','current_workload_sha256','performance_accepted']
    with (out/'points.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for row in rows:
            old,new = row['reference_kd'],row['current_kd']
            record={k:row[k] for k in columns if k in row}
            for metric in ('whole','peak'):
                record.update({f'reference_{metric}_ops_s':old[metric+'_ops_s'],
                               f'current_{metric}_ops_s':new[metric+'_ops_s'],
                               metric+'_change_pct':row['metrics'][metric]['change_pct'],
                               metric+'_observed_loss':row['metrics'][metric]['observed_loss']})
            for label,point in (('reference',old),('current',new)):
                record[label+'_execution']=point['execution_class']
                record[label+'_provider_sha256']=point['provider_sha256']
                record[label+'_workload_sha256']=point['workload_binary_sha256']
            writer.writerow(record)
    summary=dict(reference_commit=reference['commit'],current_commit=current['commit'],matched_coordinates=210,
        whole_losses=sum(r['metrics']['whole']['observed_loss'] for r in rows),
        peak_losses=sum(r['metrics']['peak']['observed_loss'] for r in rows),
        either_metric_losses=len(losses),unscored_coordinates=sum(not r['score_eligible'] for r in rows),
        rounds_per_point=1,performance_accepted=False,
        ordering='Sequential recovery, promoted, then reference; one round and no variance estimate',
        historical_other_arms='Only two fresh KD arms from the selected new cohort are compared')
    profiles=[]
    for family,lines,percent in a.PROFILES.values():
        selected=[r for r in rows if (r['lock_kind'],r['cachelines'],r['write_percent'])==(family,lines,percent)]
        a.need(len(selected)==21,'per-profile coordinate count differs')
        record=dict(lock_kind=family,workload=f'c{lines:02d}',write_percent=percent,points=21,
                    unscored_coordinates=sum(not r['score_eligible'] for r in selected),performance_accepted=False,
                    geomean_scope='All 21 measured ratios, including NO_JIT; one round, no significance claim')
        for metric in ('whole','peak'):
            ratios=[r['metrics'][metric]['ratio'] for r in selected]
            a.need(all(math.isfinite(x) and x>0 for x in ratios),'nonpositive/invalid measured ratio')
            record[metric+'_geomean_ratio']=math.exp(sum(math.log(x) for x in ratios)/len(ratios))
            record[metric+'_geomean_change_pct']=100*(record[metric+'_geomean_ratio']-1)
            record[metric+'_losses']=sum(r['metrics'][metric]['observed_loss'] for r in selected)
        record['either_metric_losses']=sum(r['any_observed_loss'] for r in selected)
        for label,key in (('reference','reference_kd'),('current','current_kd')):
            record[label+'_execution_counts']={state:sum(r[key]['execution_class']==state for r in selected)
                for state in ('NO_JIT','PARTIAL_JIT','RETURNED_JIT')}
        profiles.append(record)
    summary['profiles']=profiles
    save(out/'profiles.json',profiles)
    columns=['lock_kind','workload','write_percent','points','unscored_coordinates',
             'whole_geomean_ratio','whole_geomean_change_pct','whole_losses',
             'peak_geomean_ratio','peak_geomean_change_pct','peak_losses','either_metric_losses','performance_accepted']
    with (out/'profiles.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for row in profiles:writer.writerow({k:row[k] for k in columns})
    save(out/'key-workers.json',[r for r in rows if r['threads'] in (20,32,60)])
    save(out/'summary.json',summary)
    return summary
