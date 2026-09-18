#!/usr/bin/env python3
"""Alternate all four caller-ABI/backend arms on one verified kdclobber1 guest.

Reuse the existing measured workload, publication/body oracle and owner drain.
Build variants once outside measurement; preserve both binaries and caller
assembly, so differing spills and JIT coverage remain visible in the results.
"""
import argparse
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import shutil
import statistics
import sys

import kernel_identity
from bench_runtime import ROOT, HERE, WORKLOAD, PROVIDER, Failure, require, command, source_state, digest, idle, capture_topology
from bench_session import Session
from summarize import csv_file, valid, write_json


def plan(cachelines, threads, repeats, iterations):
    require(repeats > 0 and iterations > 0, 'positive repeats and iterations required')
    result = []
    for n,t in itertools.product(cachelines,threads):
        for repeat in range(repeats):
            arms=[('legacy','native'),('clobber','native'),('legacy','kdlock'),('clobber','kdlock')]
            if repeat % 2:
                arms.reverse()
            for abi,backend in arms:
                result.append(dict(name=f'c{n:02d}-t{t:02d}-r{repeat:02d}-{abi}-{backend}',
                    cachelines=n,threads=t,repeat=repeat,iterations=iterations,cpus=list(range(t)),arm=backend,caller_abi=abi))
    return result


def report(out):
    schedule=json.loads((out/'plan.json').read_text())
    records=[]
    for spec in schedule:
        path=out/spec['name']/'session.json'
        record=json.loads(path.read_text()) if path.exists() else dict(spec,execution_status='NOT_RUN',drained=False)
        measurement=record.get('measurement',{})
        good=valid(record)
        records.append(dict(record,
            throughput_ops_s=measurement['completed']*1e9/measurement['wall_ns'] if good else None,
            amortized_ns_op=measurement['wall_ns']/measurement['completed'] if good else None))
    write_json(out/'records.json',records)
    groups={}
    for record in records:
        key=(record['cachelines'],record['threads'],record['caller_abi'],record['arm'])
        groups.setdefault(key,[]).append(record)
    summary=[]
    for key,rows in groups.items():
        good=[r for r in rows if valid(r)]
        entry=dict(cachelines=key[0],threads=key[1],caller_abi=key[2],arm=key[3],
            sessions=len(rows),valid=len(good),no_jit=sum(r.get('jit_status')=='NO_JIT' for r in good),
            records=[r['name'] for r in rows])
        for metric in ('throughput_ops_s','amortized_ns_op','jit_share'):
            values=[r[metric] for r in good if r.get(metric) is not None]
            entry['median_'+metric]=statistics.median(values) if values else None
        summary.append(entry)
    write_json(out/'summary.json',summary)
    csv_file(out/'summary.csv',list(summary[0]),summary)
    # Compare medians without selecting a faster run with less JIT coverage.
    comparisons=[]
    for lines,threads in dict.fromkeys((r['cachelines'],r['threads']) for r in summary):
        arms={(r['caller_abi'],r['arm']):r for r in summary if (r['cachelines'],r['threads'])==(lines,threads)}
        entry=dict(cachelines=lines,threads=threads)
        for backend in ('native','kdlock'):
            old,new=(arms[(abi,backend)]['median_throughput_ops_s'] for abi in ('legacy','clobber'))
            entry[f'clobber_over_legacy_{backend}']=new/old if old and new else None
        comparisons.append(entry)
    write_json(out/'comparisons.json',comparisons)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--cachelines',type=int,nargs='+',default=[1,16],choices=[1,16])
    parser.add_argument('--threads',type=int,nargs='+',default=[1,4,20],choices=[1,4,20])
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--iterations',type=int,default=100000)
    parser.add_argument('--dry-run',action='store_true')
    kernel_identity.arguments(parser)
    args=parser.parse_args(argv)
    schedule=plan(args.cachelines,args.threads,args.repeats,args.iterations)
    if args.dry_run:
        print(json.dumps(schedule,indent=2));return 0
    require(ROOT==Path('/root/host_fs/kdlock') and os.geteuid()==0 and os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1','requires confirmed recovery guest')
    require(os.uname().release=='6.1.159-kdclobber1','requires the same kdclobber1 kernel for all arms')
    require(args.output and not args.output.exists(),'choose a new output directory')
    out=args.output.resolve()
    require(not out.is_relative_to(ROOT),'evidence must be outside checkout')
    idle();out.mkdir(parents=True)
    write_json(out/'plan.json',schedule)
    try:
        identity=kernel_identity.capture(args,out,command)
        require(command(['findmnt','-T',ROOT,'-n','-o','FSTYPE'],out/'mount.txt').strip()=='ext4','recovery ext4 required')
        require('nokaslr' in Path('/proc/cmdline').read_text().split() and '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text(),'kernel runtime differs')
        packages={p:importlib.metadata.version(p) for p in ('miasm','future','pyparsing','pyelftools')}
        require(packages==dict(miasm='0.1.5',future='1.0.0',pyparsing='2.4.7',pyelftools='0.27'),'pinned dependencies required')
        topology=capture_topology(list(range(max(args.threads))))
        for spec in schedule:
            spec['cpu_nodes']=topology['role_nodes'][:spec['threads']]
        write_json(out/'plan.json',schedule)
        write_json(out/'environment.json',dict(kernel_identity=identity,topology=topology,packages=packages,python=sys.executable,
            snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),cmdline=Path('/proc/cmdline').read_text(),
            preemption=Path('/sys/kernel/debug/sched/preempt').read_text(),uname=list(os.uname()),
            watchdog=Path('/proc/sys/kernel/watchdog').read_text(),argv=sys.argv))
        for name,build in [('provider',['make','-C',HERE,'provider']),('daemon',['make','-C',ROOT/'daemon','CFLAGS=-O2 -Wall -Wextra -Werror']),('client',['make','-C',HERE,'client'])]:
            command([*build,f'KDIR={args.kernel_source}'],out/f'build-{name}.log',timeout=180)
        variants={}
        for abi in ('legacy','clobber'):
            folder=out/'variants'/abi;folder.mkdir(parents=True)
            for source in WORKLOAD.iterdir():
                if source.suffix in {'.c','.h','.inc'} or source.name=='Makefile':
                    shutil.copyfile(source,folder/source.name)
            flags='-DKD_SPIN_LEGACY_CALLER' if abi=='legacy' else ''
            command(['make','-C',folder,f'KDIR={args.kernel_source}',f'KCFLAGS={flags}'],out/f'build-{abi}.log',timeout=120)
            variants[abi]=folder/'spin_cacheline.ko'
            command(['objdump','-dr',variants[abi]],out/f'caller-{abi}.txt')
        frozen=source_state();write_json(out/'source-sha256.json',frozen)
        for relative in frozen:
            target=out/'source'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
        binaries=[*variants.values(),PROVIDER,ROOT/'daemon/daemon',HERE/'client']
        hashes={str(p):digest(p) for p in binaries};write_json(out/'binary-sha256.json',hashes)
        (out/'binaries').mkdir()
        for binary in (PROVIDER,ROOT/'daemon/daemon',HERE/'client'):
            shutil.copyfile(binary,out/'binaries'/binary.name)
        for index,spec in enumerate(schedule):
            if (out/'STOP').exists():
                raise Failure('STOPPED','requested at a drained session boundary')
            require(source_state()==frozen and all(digest(Path(p))==h for p,h in hashes.items()),'frozen inputs changed')
            idle();print(f'[{index+1}/{len(schedule)}] {spec["name"]}',flush=True)
            session=Session(out,spec,workload_module=variants[spec['caller_abi']])
            session.execute()
            print(f'  {session.record["jit_status"]} share={session.record["jit_share"]:.4%} drained={session.record["drained"]}',flush=True)
        idle();report(out);return 0
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        report(out);print(f'STOP: {error}; retained evidence {out}',file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
