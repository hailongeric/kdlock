#!/usr/bin/env python3
"""Independently review pipecap archives and diagnostic arithmetic on 380G10."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import struct
import random
import math
import socket
from statistics import median, mean, stdev
import sys
import tarfile
from types import SimpleNamespace

HELPER='bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA='05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ORIGINAL_SHA='7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'
MODES=('plain','reference','sampled')
RESIDUAL={'kd_hotlock_mutex_entries','kd_hotlock_mutex_contentions','kd_hotlock_mutex_last_entries'}


def save(path,data):
    with path.open('x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')


def stats(v):
    return dict(n=len(v),minimum=min(v),median=median(v),maximum=max(v),
                spread_pct=100*(max(v)-min(v))/median(v),cv_pct=100*stdev(v)/mean(v) if len(v)>1 else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[5]
    assert socket.gethostname()=='380G10' and not args.output.exists()
    args.output.mkdir()
    sys.dont_write_bytecode=True
    helper_path=repo/HELPER
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest()==HELPER_SHA
    spec=importlib.util.spec_from_file_location('pipecap_inert_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    original_raw=args.raw.parent/'mutex-public-20261020-r2'
    assert helper.hashfile(original_raw/'archives.json')==ORIGINAL_SHA
    original_manifest=json.loads((original_raw/'archives.json').read_text())
    original_inventory=json.loads((original_raw/'input-inventory.json').read_text())
    assert helper.hashfile(original_raw/'input-inventory.json')==original_manifest['input_inventory_sha256']
    class JointAudit(helper.Audit):
        def retained_target(self, target):
            # Only the current archive and the pinned original archive may
            # satisfy a link. Resolve path components in memory, including
            # workspace -> replay view -> original bundle chains.
            roots = {self.guest_base.rstrip('/'): self.inventory,
                     original_manifest['guest_base']: original_inventory}
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in roots if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                relative = target[len(root):].lstrip('/')
                if not relative:
                    return True
                if not helper.safe_relative(relative):
                    return False
                parts = relative.split('/')
                inventory = roots[root]
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = inventory.get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = (link if link.startswith('/') else
                                  posixpath.join(root, posixpath.dirname(name), link))
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return relative in inventory
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    audit=JointAudit(SimpleNamespace(repo=repo,raw=args.raw,report=args.output))
    groups,links=audit.load_archives();audit.windows=[]
    # Bind retained original input manifests and selected records to the previously
    # reviewed original archive; never import or execute a frozen program.
    original={}
    for g in original_manifest['groups']:
        audit.equal('original_archive_hash',helper.hashfile(original_raw/g['file']),g['sha256'],g['file'])
        if g['group'] not in ('metadata','matrix'):continue
        with tarfile.open(original_raw/g['file']) as t:
            for name in ('frozen-inputs.json','harness-inputs.json','matrix/records.json','matrix/host-state.json'):
                try:original[name]=json.load(t.extractfile(original_manifest['archive_prefix']+'/'+name))
                except KeyError:pass
    baseline={r['name']:r for r in original['matrix/records.json']}
    health=audit.jread('final-health.json')
    audit.expect('final_idle',health['idle'] and not health['per_session_kernel_faults'])
    frozen={p:h for b in original['frozen-inputs.json'].values() for p,h in b['files'].items()}
    audit.equal('health_original_files',health['verified_original_files'],frozen)
    expected_host=original['matrix/host-state.json']
    host_results={}
    for run in ('run-1',):
        before=audit.jread(run+'/matrix/host-state.json')
        after=audit.jread('host-evidence/host-after-'+run[-1]+'.json')
        outcome={}
        for label,h in (('before',before),('after',after)):
            for k in ('cpufreq','numa','recovery_snapshot'):
                audit.equal('host_settings',h[k],expected_host[k],[run,label,k])
            for k in ('pid','args'):
                audit.equal('qemu_identity',h['qemu'][0][k],expected_host['qemu'][0][k],[run,label,k])
            expected=sorted(expected_host['qemu'][0]['tasks'],key=lambda t:t['tid'])
            actual=sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
            outcome[label]=dict(captured_utc=h['captured_utc'],threads=len(actual),exact_match=actual==expected,
                                pins_verified=h['pins_verified'],snapshot_listed=h['snapshot_listed'])
            audit.expect('host_receipt_valid',h['pins_verified'] and h['snapshot_listed'],[run,label])
            if label=='before':audit.expect('strict_preflight',actual==expected,run)
        host_results[run]=outcome
    checks=[]
    for name,count in (('checks-1',30),):
        result=audit.jread(name+'/result.json'); manifest=audit.jread(name+'/committed-source.json')
        audit.expect('basic_affected_success',result['passed'] and result['final_idle'] and result['source_unchanged'],name)
        audit.equal('check_revision',manifest['commit'],result['source_revision'],name)
        source=audit.jread(name+'/source-sha256.json')
        # The runner freezes C/Python sources, private includes and build inputs.
        # Its broader commit manifest also binds docs, boot policy and unused
        # admission fixtures; those remain Git evidence, not executed test input.
        excluded={p for p in manifest['files'] if p.endswith('.md')} | {
            'kernel_baseline/nopvspin-grub.cfg',
            'tests/unit/admission/fixtures/xattr-memcpy-caller.bin',
            'tests/unit/admission/fixtures/xattr-memcpy-kernel.bin'}
        audit.equal('snapshot_exact_selected_set',set(source),set(manifest['files'])-excluded,name)
        audit.equal('snapshot_selected_count',len(source),489,name)
        for p,h in manifest['files'].items():
            audit.equal('check_source_git',helper.sha(audit.git_bytes(manifest['commit'],p)),h,[name,p])
            if p in source:
                audit.equal('check_frozen_source',audit.files.get(name+'/source/'+p),h,[name,p])
                audit.equal('check_snapshot_manifest',source[p],h,[name,p])
        audit.equal('basic_count',re.findall(r'Unit tests: (\d+) passed, (\d+) failed',audit.contents[name+'/unit.log'].decode()),[('2','0')],name)
        counts=[int(re.search(r'Ran (\d+) tests',audit.contents[name+'/'+Path(p).stem+'.log'].decode())[1]) for p in result['runner_tests']]
        audit.equal('affected_counts',sum(counts),count,name)
        checks.append(dict(name=name,revision=result['source_revision'],basic=2,affected=sum(counts),
                           commit_manifest_entries=len(manifest['files']),frozen_source_entries=len(source),
                           git_only_paths=sorted(excluded)))
    bindings=('comparison_workload','threads','repeat','comparison_arm','arm','source_identity',
        'caller_shell','cookie_storage','cpus','cpu_nodes','collector_cpu','collector_shared',
        'duration_ms','peak_window_ms','peak_settle_ms','sample_ms','warmup','warmup_ms','entries',
        'value_size','file_descriptions','syscalls_per_op','numa_policy','spin_entry_ratio_limit',
        'delegation_batch_limit','kd_provider_ubsan')
    run='run-1'
    result=audit.jread(run+'/result.json')
    records=audit.jread(run+'/matrix/records.json');plan=audit.jread(run+'/matrix/plan.json')
    audit.equal('fixed_plan_length',[len(records),len(plan)],[24,24])
    audit.expect('run_completed',result['state']=='COMPLETE' and result['final_idle'] and not result['accepted'])
    for tool,h in audit.jread(run+'/tool-sha256.json').items():
        audit.equal('tool_copy',audit.files[run+'/tools/'+tool],h,tool)
        audit.equal('tool_commit',h,helper.sha(audit.git_bytes(result['source_commit'],'bench/mutex_api_compare/'+tool)),tool)
    original_rotation=[]
    for repeat in range(3):
        original_arms=[r['comparison_arm'] for r in original['matrix/records.json']
                       if (r['comparison_workload'],r['threads'],r['repeat'])==('pipecap',1,repeat)]
        for mode in MODES[repeat:]+MODES[:repeat]:
            original_rotation += [(repeat,mode,arm) for arm in original_arms
                                  if mode=='plain' or arm.endswith('-kd')]
    audit.equal('fixed_original_rotations',[(r['repeat'],r['owner_mode'],r['comparison_arm']) for r in records],original_rotation)

    def raw_bytes(name):
        with tarfile.open(args.raw/audit.members[name]['archive']) as t:
            return t.extractfile(audit.prefix+name).read()

    def dist(values):
        values=sorted(values)
        return dict(min=values[0],median=values[len(values)//2],
                    p95=values[math.ceil(.95*len(values))-1],max=values[-1])

    summaries=[];retired=0;observed=0
    for r,p in zip(records,plan):
        tag=r['name'];folder=str(Path(r['evidence_path']).relative_to(audit.guest_base.rstrip('/')))
        audit.equal('plan_fields',{k:r.get(k) for k in p},p,tag)
        audit.equal('session_record',r,audit.jread(folder+'/session.json'),tag)
        audit.expect('session_ok_drained',r['execution_status']=='OK' and r['drained'] and not r.get('cleanup_error'),tag)
        audit.expect('kernel_clean',not helper.FAULT.search(audit.contents[folder+'/kernel.log'].decode()),tag)
        if r['arm']=='kdlock':
            audit.equal('exact_retirement',r['retired'],dict(state=2,modules=0,frames=0,writers=0),tag);retired+=1
            audit.equal('immutable_image',r['published_before'],r['published_after'],tag)
        old=baseline[tag.removesuffix('-'+r['owner_mode'])]
        audit.equal('original_settings',{k:r.get(k) for k in bindings},{k:old.get(k) for k in bindings},tag)
        audit.equal('original_jit_requirement',r['require_jit'],old['require_jit'],tag)
        audit.expect('diagnostic_only',r['diagnostic'] and not r['score_eligible'],tag)
        m=r['measurement'];audit.expect('business_result',m['ok'],tag)
        audit.equal('exact_redirected_work',r['redirected_calls'],m['completed'],tag)
        audit.peak(r,folder)
        audit.equal('zero_jit',[r['jit_bodies'],r['jit_completions']],[0,0],tag)
        row=dict(name=tag,arm=r['comparison_arm'],repeat=r['repeat'],mode=r['owner_mode'],
                 completed=m['completed'],whole_ops_s=m['completed']*1e9/m['wall_ns'],
                 peak_ops_s=m['peak']['throughput_ops_s'],observation=None)
        if r['route_snapshot']:
            observed+=1
            ss=audit.jread(folder+'/route-snapshots.json');b,a=ss['before'],ss['after'];delta=ss['delta']
            audit.equal('before_receipt',b,audit.jread(folder+'/route-before.json'),tag)
            audit.equal('counter_delta_receipt',r['route_delta'],delta,tag)
            for x in (b,a):
                audit.equal('counter_cpu_domain',[v['cpu'] for v in x['cpus']],list(range(64)),tag)
                audit.equal('counter_cpu_sum',x['totals'],{k:sum(v['values'][k] for v in x['cpus']) for k in x['totals']},tag)
                audit.expect('quiescent_reservations',all(v['values']['kd_mutex_active_waiters']==v['values']['kd_mutex_reserved_nodes']==0 for v in x['cpus']),tag)
                audit.equal('timing_disabled',x['timing_enabled'],False,tag)
            d={k:a['totals'][k]-v for k,v in b['totals'].items() if k not in RESIDUAL}
            n={k:a['native'][k]-v for k,v in b['native'].items()}
            timings={phase:{field:a['timings'][phase][field]-v[field] for field in ('samples','ns')} for phase,v in b['timings'].items()}
            audit.equal('counter_delta_arithmetic',delta['counters'],d,tag)
            audit.equal('native_delta_arithmetic',delta['native'],n,tag)
            audit.equal('timing_delta_arithmetic',delta['timings'],timings,tag)
            audit.expect('no_timing_activity',not any(v for t in timings.values() for v in t.values()),tag)
            audit.expect('capture_outside_measurement',b['finished_ns']<=m['started_ns'] and a['started_ns']>=m['finished_ns'],tag)
            audit.equal('public_counter_witness',[d['kd_bench_bodies'],d['kd_bench_completions']],[r['jit_bodies'],r['jit_completions']],tag)
            proc=audit.jread(folder+'/owner-process.json');config=audit.jread(folder+'/owner-config.json')
            binding=audit.jread(folder+'/owner-binding.json');analysis=audit.jread(folder+'/owner-analysis.json')
            audit.equal('owner_analysis_record',r['owner_observation'],analysis,tag)
            audit.equal('binding_config',binding['config'],config,tag)
            for role in ('provider','workload'):
                # The view symlink resolves to the retained original bundle.
                version='baseline' if r['comparison_arm']=='baseline-kd' else 'current'
                relative='build/kdlock_km.ko' if role=='provider' else 'build/kdlock-pipecap/real_api.ko'
                original_path=str(Path(original_manifest['guest_base'])/version/'pipecap'/relative)
                audit.equal('original_observed_elf_hash',config[role+'_sha256'],frozen[original_path],[tag,role])
            live=audit.contents[folder+'/owner-kallsyms.txt'].decode()
            audit.equal('live_symbols_hash',helper.sha(live.encode()),binding['kallsyms_sha256'],tag)
            for key,size in (('owner',32),('reference',1)):
                obj=binding[key]
                matches=[v for line in live.splitlines() if len(v:=line.split())==4 and v[2:]==[obj['name'],'['+obj['module']+']']]
                audit.expect('unique_live_object',len(matches)==1,tag)
                audit.equal('live_object_address',int(matches[0][0],16),obj['address'],tag)
                audit.expect('object_layout',obj['size']==size and obj['section'] in ('.bss','.data')
                             and obj['section_base']+obj['offset']==obj['address'],[tag,key])
            audit.equal('owner_collector_address',binding['owner']['address'],r['lock_addr'],tag)
            audit.equal('owner_native_layout',[binding['owner']['size'],r['lock_addr']%64],[32,32],tag)
            address=r['lock_addr']+7 if r['owner_mode']=='sampled' else binding['reference']['address']
            audit.equal('sample_address',binding['address'],address,tag)
            seg=[s for s in binding['kcore_segments'] if s['address']<=address<s['address']+min(s['size'],s['file_size'])]
            audit.expect('unique_kcore_extent',len(seg)==1,tag)
            audit.equal('unbuffered_read_offset',binding['file_offset'],seg[0]['offset']+address-seg[0]['address'],tag)
            audit.equal('active_paging_mode',binding['paging']['virtual_address_bits'],57,tag)
            audit.equal('sampler_seed',config['seed'],int.from_bytes(hashlib.sha256(tag.encode()).digest()[:8],'little'),tag)
            audit.equal('sampler_fixed_settings',[proc['record_format'],proc['capacity'],proc['cpu']],['<QQQB7x',16384,62],tag)
            audit.expect('sampler_complete_closed',proc['state']=='COMPLETE' and proc['pins_closed'] and r['owner_process']['exit_code']==0,tag)
            audit.expect('sampler_phase_coverage',proc['started_ns']<=m['started_ns']<m['finished_ns']<=proc['stopped_ns']<=proc['finished_ns'],tag)
            data=raw_bytes(folder+'/owner-samples.bin')
            audit.equal('sample_hash',helper.sha(data),proc['samples_sha256'],tag)
            audit.equal('sample_extent',len(data),proc['samples']*32,tag)
            values=list(struct.iter_unpack('<QQQB7x',data))
            rng=random.Random(config['seed']);deadline=proc['started_ns']+rng.randrange(250000,1750001);missed=0;last=0
            for scheduled,begin,end,value in values:
                audit.equal('independent_schedule',scheduled,deadline,tag)
                audit.expect('valid_read_order',last<=begin<=end and scheduled<=begin,tag);last=end
                audit.expect('valid_byte',value in ((0,255) if r['owner_mode']=='sampled' else (0,)),tag)
                deadline+=rng.randrange(250000,1750001)
                while deadline<=end:
                    missed+=1;deadline+=rng.randrange(250000,1750001)
            audit.equal('missed_deadlines',proc['missed_deadlines'],missed,tag)
            inside=[v for v in values if m['started_ns']<=v[1]<=v[2]<=m['finished_ns']]
            count=len(inside);occupied=sum(v[3]==255 for v in inside);fraction=occupied/count
            zeros=('kd_bench_bodies','kd_bench_completions','kd_mutex_slowpath_count','kd_mutex_origin_acquires',
                   'kd_mutex_origin_releases','kd_mutex_nested_lock_count','kd_mutex_handoff_count')
            local=all(d[k]==0 for k in zeros) and not any(n.values())
            audit.expect('local_only_measurement',local,tag)
            audit.equal('local_receipt',analysis['local_only'],local,tag)
            audit.equal('sample_counts',[analysis['samples'],analysis['occupied'],analysis['outside_or_boundary_samples']],
                        [count,occupied,len(values)-count],tag)
            audit.equal('occupied_fraction',analysis['fraction'],fraction,tag)
            scale=m['wall_ns']/m['completed']
            audit.equal('ownership_estimate',analysis['estimated_mean_hold_ns'],fraction*scale if r['owner_mode']=='sampled' else None,tag)
            z=1.959963984540054;center=(fraction+z*z/(2*count))/(1+z*z/count)
            half=z*math.sqrt(fraction*(1-fraction)/count+z*z/(4*count*count))/(1+z*z/count)
            audit.equal('conditional_wilson_arithmetic',analysis['iid_only_wilson95_hold_ns'],
                        [(center-half)*scale,(center+half)*scale] if r['owner_mode']=='sampled' else None,tag)
            blocks=[]
            for i in range(10):
                v=[x[3] for x in inside if (x[1]-m['started_ns'])*10//m['wall_ns']==i]
                blocks.append(dict(index=i,samples=len(v),occupied=sum(x==255 for x in v)))
            audit.equal('temporal_blocks',analysis['blocks'],blocks,tag)
            for label,series in (('read_ns',[x[2]-x[1] for x in inside]),('lateness_ns',[x[1]-x[0] for x in inside]),
                                 ('gap_ns',[y[1]-x[1] for x,y in zip(inside,inside[1:])])):
                audit.equal('read_schedule_distribution',analysis[label],dist(series),[tag,label])
            row['observation']=analysis
        summaries.append(row)

    grouped=[];comparisons=[];overhead=[]
    for mode in MODES:
        for arm in ('native','tclock','baseline-kd','public-kd'):
            rows=[r for r in summaries if (r['mode'],r['arm'])==(mode,arm)]
            if not rows:continue
            audit.equal('three_fixed_repeats',sorted(r['repeat'] for r in rows),[0,1,2],[mode,arm])
            grouped.append(dict(mode=mode,arm=arm,whole=stats([r['whole_ops_s'] for r in rows]),
                                peak=stats([r['peak_ops_s'] for r in rows]),
                                estimated_hold_ns=stats([r['observation']['estimated_mean_hold_ns'] for r in rows]) if mode=='sampled' else None))
        outer=[r for r in summaries if r['mode']==mode and r['arm']=='baseline-kd']
        direct=[r for r in summaries if r['mode']==mode and r['arm']=='public-kd']
        comparisons.append(dict(mode=mode,descriptive_whole_ratio=median(r['whole_ops_s'] for r in direct)/median(r['whole_ops_s'] for r in outer),
            paired_whole_ratios=[b['whole_ops_s']/a['whole_ops_s'] for a,b in zip(outer,direct)],accepted=False,
            paired_estimated_hold_difference_ns=[b['observation']['estimated_mean_hold_ns']-a['observation']['estimated_mean_hold_ns'] for a,b in zip(outer,direct)] if mode=='sampled' else None))
    for arm in ('baseline-kd','public-kd'):
        for mode in MODES[1:]:
            ratios=[]
            for repeat in range(3):
                plain=next(r for r in summaries if (r['arm'],r['mode'],r['repeat'])==(arm,'plain',repeat))
                sample=next(r for r in summaries if (r['arm'],r['mode'],r['repeat'])==(arm,mode,repeat))
                ratios.append(sample['whole_ops_s']/plain['whole_ops_s'])
            overhead.append(dict(arm=arm,mode=mode,paired_throughput_ratios=ratios,stats=stats(ratios),
                                 limits='Includes temporal drift and host activity; no isolated causal overhead claim.'))
    for name,data in (('sessions.json',summaries),('groups.json',grouped),('comparisons.json',comparisons),('observer-effects.json',overhead)):
        save(args.output/name,data)
    with (args.output/'per-repeat.csv').open('x',newline='') as f:
        keys=('name','arm','repeat','mode','completed','whole_ops_s','peak_ops_s')
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in summaries)
    answer=dict(consistent=not audit.issues,issues=audit.issues,checks=sum(audit.counts.values()),check_counts=dict(audit.counts),
        archives=groups,symlinks=len(links),members=len(audit.members),files=len(audit.files),functional_checks=checks,
        completed_sessions=len(summaries),counter_sessions=observed,retired=retired,
        host_checks=host_results,source_sha256=helper.hashfile(Path(__file__)),archives_sha256=helper.hashfile(args.raw/'archives.json'),
        original_archives_sha256=ORIGINAL_SHA,accepted=False,
        limits='Inconclusive owner-interval hypothesis; finite samples, uncalibrated state-dependent probe bias and failed host endpoint. No p95 or causal production fix.')
    save(args.output/'review.json',answer)
    print(json.dumps(answer,indent=2))
    return 0 if answer['consistent'] else 1


if __name__=='__main__':
    raise SystemExit(main())
