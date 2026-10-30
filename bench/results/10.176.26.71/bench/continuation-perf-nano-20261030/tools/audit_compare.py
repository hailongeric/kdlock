#!/usr/bin/env python3
"""Offline finalized KD210 audit; separate KD comparisons to acfa and 8617.

Never execute archived source or ELF bytes. Only hash-matched trusted checkout
oracles may run. A failed audit leaves its output and validation receipt intact.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
import nano_core as a
from archive_helpers import apply_exact_patch, capture_elfs

ACFA = 'acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f'
OLD = '8617e97c02432a7c0b931aa8263d5edd0f6eb5b8'
CURRENT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
RAW = Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/kernel-proxy-nano-20261030')
REF8617 = Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/continuation-nano-8617e97c-20261030')
REPORT = Path('/tmp/kdlock-kernel-proxy-20261030/bench/results/10.176.26.71/bench/kernel-proxy-nano-20261030')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


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
    records = capture_elfs(archive,wanted,out)
    a.need(sum(n.endswith('/kdlock_km.ko') for n in records) == 10, 'expected ten measured KD provider ELFs')
    save(out/'elf-provenance.json',records)
    result = dict(source_commit=commit,tracked_source_blobs=len(expected),extra_source_files={},
                  provider_preparation=providers,exact_patch_hunks=hunks,
                  dependency_receipts={n:archive.hashes[n] for n in commands},
                  captured_module_elfs=len(records),captured_provider_elfs=10,
                  scope='Actual archived module bytes; no requirement to equal the earlier unit-build ELF')
    save(out/'provider-audit.json',result)
    return result


def compare(reference, current):
    a.need(reference['boot_id'] == current['boot_id'] and
           reference['kernel_identity'] == current['kernel_identity'] and
           reference['kernel_bundle_sha256'] == current['kernel_bundle_sha256'] and
           reference['host_fixed_identity'] == current['host_fixed_identity'],
           'cross-campaign kernel/topology/fixed-host identity differs')
    a.need(reference['finished'] <= current['started'], 'campaigns overlap or chronology differs')
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
        ordering='Sequential older reference then current KD; no randomized pairs or variance estimate',
        historical_other_arms='Reference Native/TCLock observations are not used or relabelled as current comparators')
    save(out/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-archives',type=Path,required=True)
    parser.add_argument('--current-control',type=Path,required=True)
    parser.add_argument('--current-host-after',type=Path,required=True)
    parser.add_argument('--trusted-checkout',type=Path,default=Path('/tmp/kdlock-continuation-perf-20261030'))
    parser.add_argument('--acfa-archives',type=Path,default=RAW/'kernel-proxy-nano-baseline-acfa-20261030-archives')
    parser.add_argument('--acfa-control',type=Path,default=RAW/'kernel-proxy-nano-baseline-acfa-20261030-control')
    parser.add_argument('--acfa-host-after',type=Path,default=REPORT/'baseline-host-after.json')
    parser.add_argument('--reference8617-archives',type=Path,default=REF8617/'continuation-nano-8617e97c-20261030-archives')
    parser.add_argument('--reference8617-control',type=Path,default=REF8617/'continuation-nano-8617e97c-20261030-control')
    parser.add_argument('--reference8617-host-after',type=Path,default=REF8617/'continuation-nano-8617e97c-20261030-control/host-after.json')
    parser.add_argument('--historical-extra-review',type=Path,default=REPORT/'extra-source-review.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve();root=args.trusted_checkout.resolve(strict=True)
    a.need(not args.output.exists() and not args.output.is_symlink(), 'new analysis output required')
    for name,path in vars(args).items():
        if isinstance(path,Path) and name != 'output':
            resolved=path.resolve()
            a.need(not out.is_relative_to(resolved) and not resolved.is_relative_to(out), 'output must be separate from inputs')
    out.mkdir(parents=True)
    receipt=dict(completed=False,validated=False,performance_accepted=False,
        arguments={k:str(v) for k,v in vars(args).items()},
        tool_sha256={n:a.file_sha(Path(__file__).parent/n) for n in ('audit_compare.py','nano_core.py','archive_helpers.py','prerequisites.py')})
    save(out/'validation.json',receipt)
    try:
        git=a.Git(root)
        oracle,fault,hashes=a.trusted_oracles(git,ACFA,CURRENT)
        other_oracle,other_fault,other_hashes=a.trusted_oracles(git,OLD,CURRENT)
        a.need(hashes == other_hashes and fault.pattern == other_fault.pattern, 'oracle versions differ')
        extras=a.local_json(args.historical_extra_review)
        a.need(set(extras) == {'baseline','candidate'}, 'historical extra review labels differ')
        campaigns={}
        selections=[('acfa',ACFA,['kdlock'],'baseline',args.acfa_archives,args.acfa_control,args.acfa_host_after),
                    ('8617',OLD,['kdlock'],'reference8617',args.reference8617_archives,args.reference8617_control,args.reference8617_host_after),
                    ('current',CURRENT,['kdlock'],'current',args.current_archives,args.current_control,args.current_host_after)]
        with tempfile.TemporaryDirectory(prefix='kdf7-nano-offline-') as temporary:
            for label,commit,arms,extra_label,archives,control,after in selections:
                cache=Path(temporary)/label;cache.mkdir()
                archive=a.Archive(archives,cache)
                if label in ('current','8617'):
                    current_out=out/label;current_out.mkdir()
                    receipt[label+'_provider_audit']=provider_audit(archive,git,current_out,commit)
                result=a.campaign(extra_label,archive,control,after,commit,git,other_oracle,fault,
                                  extras if label == 'acfa' else {extra_label:{}},arms=arms)
                campaigns[label]=result
                target=out/label;target.mkdir(exist_ok=True)
                save(target/'points.json',list(result['rows'].values()))
                save(target/'campaign.json',{k:v for k,v in result.items() if k != 'rows'})
        receipt.update(comparisons={
            'vs-acfa':write_comparison(out/'vs-acfa',campaigns['acfa'],campaigns['current']),
            'vs-8617':write_comparison(out/'vs-8617',campaigns['8617'],campaigns['current'])},
            completed=True,validated=True,oracle_sha256=hashes,
            reference_archive_points={'acfa':210,'8617':210},current_points=210,
            limits=['Strict timing qualification remains false; no promotion or performance pass.',
                    'One measurement round per point, all NO_JIT and observed losses retained.',
                    'PARTIAL_JIT rows are retained and marked unscored, never silently removed.',
                    'No data pooling across commits, topology, call shells, arms or instrumentation.',
                    'Endpoint identity does not prove uninterrupted host isolation.',
                    'No current Native/TCLock measurements or claims are manufactured.',
                    'Offline receipts and bytes do not prove weak-memory correctness or causal attribution.'])
    except BaseException as error:
        receipt['error']=repr(error)
        raise
    finally:
        save(out/'validation.json',receipt)
    print(json.dumps({'validated':True,'current_points':210,'comparisons':receipt['comparisons'],'performance_accepted':False}))


if __name__ == '__main__':
    main()
