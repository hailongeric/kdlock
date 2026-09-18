#!/usr/bin/env python3
"""Separate flat-IP sampling of the exact binaries from a completed comparison.

Keep sampling out of reported throughput. Reuse preparation, actual delegation,
data and drain oracles, and attribute IPs only to bounded ELF/JIT ranges.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tc_comparison', HERE/'run.py')
comparison = importlib.util.module_from_spec(spec); spec.loader.exec_module(comparison)
from bench_runtime import command, require, digest, ROOT, Failure
from session import BackendSession, TC_MODULE
from profile import ProfileSession
from profile_summary import symbol_ranges, aggregate
from summarize import write_json
import kernel_identity


class ProfileBackendSession(ProfileSession, BackendSession):
    def __init__(self, out, plan, workload, perf, frequency):
        BackendSession.__init__(self,out,plan,workload_module=workload)
        self.perf, self.frequency, self.event = perf, frequency, 'cycles:k'
        self.record.update(diagnostic='kernel-ip-sampling',performance_result=False,
                           sample_event=self.event,sample_frequency_hz=frequency,callchain=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--perf',type=Path,required=True)
    p.add_argument('--arm',choices=('native','tclock','kdlock'),required=True)
    p.add_argument('--abi',choices=('legacy','clobber'),default='clobber')
    p.add_argument('--threads',type=int,choices=(4,20),default=20)
    p.add_argument('--cachelines',type=int,choices=(1,16),default=1)
    p.add_argument('--iterations',type=int,default=1000000)
    p.add_argument('--frequency',type=int,default=199)
    kernel_identity.arguments(p); args=p.parse_args()
    require(ROOT==Path('/root/host_fs/kdlock') and os.geteuid()==0 and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1','confirmed recovery guest required')
    require(1 <= args.frequency <= 999 and 0 < args.iterations <= 100000000,'invalid sampling settings')
    out=args.output.resolve(); origin=args.comparison.resolve(); perf=args.perf.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT),'new external output required')
    require(perf.is_file(),'missing perf')
    original=json.loads((origin/'records.json').read_text())
    require(original and all(r['execution_status']=='OK' and r['drained'] for r in original),
            'comparison incomplete')
    frozen=json.loads((origin/'source-sha256.json').read_text())
    hashes=json.loads((origin/'binary-sha256.json').read_text())
    require(comparison.source_state()==frozen and all(digest(Path(n))==h for n,h in hashes.items()),
            'comparison inputs changed')
    tracing=Path('/sys/kernel/debug/tracing')
    require((tracing/'current_tracer').read_text().strip()=='nop' and
            (tracing/'function_profile_enabled').read_text().strip()=='0','disable ftrace/function profiling')
    comparison.idle(); out.mkdir(parents=True)
    # Session's translator resolves these frozen sibling sources.
    (out/'source').symlink_to(origin/'source',target_is_directory=True)
    identity=kernel_identity.capture(args,out,command)
    plan=dict(name='profile',arm=args.arm,caller_abi=args.abi,cachelines=args.cachelines,
              threads=args.threads,iterations=args.iterations,repeat=0,cpus=list(range(args.threads)))
    topology=comparison.runtime.capture_topology(plan['cpus']);plan['cpu_nodes']=topology['role_nodes']
    write_json(out/'plan.json',[plan])
    write_json(out/'environment.json',dict(comparison=str(origin),argv=sys.argv,kernel_identity=identity,
        topology=topology,perf_sha256=digest(perf),perf_version=command([perf,'version'],out/'perf-version.txt'),
        snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),source_sha256=frozen,binary_sha256=hashes))
    workload=origin/'variants'/args.abi/'spin_cacheline.ko'
    session=ProfileBackendSession(out,plan,workload,perf,args.frequency)
    try:
        session.execute(); comparison.idle(); session.report(args.kernel_source)
        report=(session.path/'perf-report.txt').read_text()
        lost=re.search(r'Total Lost Samples: ([0-9]+)',report)
        require(lost and int(lost[1])==0,'lost samples')
        header=(session.path/'perf-header.txt').read_text()
        fields=re.search(r'sample_type = ([A-Z_|]+)',header)
        require(fields and set(fields[1].split('|'))=={'IP','TID','TIME','PERIOD'},'unexpected sampling fields')
        symbols=(session.path/'kallsyms.txt').read_text()
        ranges=symbol_ranges(symbols,(session.path/'kernel-symbol-sizes.txt').read_text(),'kernel')
        modules=[('spin_cacheline',workload)]
        if args.arm=='tclock': modules.append(('tclock_backend_km',TC_MODULE))
        if args.arm=='kdlock': modules.append(('kdlock_km',comparison.PROVIDER))
        for name,binary in modules:
            sizes=command(['nm','-S','--defined-only',binary],out/f'{name}-sizes.txt')
            command(['objdump','-dr',binary],out/f'{name}-disassembly.txt')
            ranges+=symbol_ranges(symbols,sizes,name)
        if args.arm=='kdlock':
            entry=session.record['published_before']['entry']
            image=session.path/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm/jit.bin'
            ranges.append((entry['code'],entry['code']+image.stat().st_size,'generated:jit_image'))
        write_json(out/'symbol-ranges.json',ranges)
        result=aggregate((session.path/'perf-samples.txt').read_text(),ranges)
        result.update(arm=args.arm,caller_abi=args.abi,threads=args.threads,cachelines=args.cachelines,
                      delegation_share=session.record['delegation_share'],lost_samples=0,
                      scope='flat sampled cycles; not isolated function latency',performance_result=False)
        write_json(out/'hotspots.json',result)
        require(comparison.source_state()==frozen and all(digest(Path(n))==h for n,h in hashes.items()),
                'diagnostic inputs changed')
        print(json.dumps({k:v for k,v in result.items() if k!='symbols'}))
        for row in result['symbols'][:12]:
            print(f'{row["sample_weight_percent"]:7.2f}% {row["symbol"]}')
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        raise


if __name__=='__main__': main()
