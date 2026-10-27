#!/usr/bin/env python3
"""Single-round actual shared-mm timing after per-mode Linux 7 correctness.

Runs one explicitly booted backend only. It never builds, installs or boots a
kernel. Both modes must use the same verified kernel image and timed artifacts;
host endpoint/frequency qualification remains a separate controller obligation.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'bench/mmap_writer'))
import shared_platform as platform
common, rt = platform.common, platform.rt
writer = common.module('linux70_shared_writer',Path(__file__).with_name('timing.py'))
WORKERS = tuple(range(1,9))+tuple(range(12,61,4))
PREREQUISITES = ('api','mapping','faults','completed')


def image_identity(binding):
    return {key:binding[key] for key in
            ('release','build_id','configuration_sha256','source_files','build_files')}


def plan(mode):
    rt.require(mode in platform.MODES,'unknown actual-MM backend')
    return [dict(writer.spec(n,'plain',0),arm=mode,backend=mode,
                 peak_policy='optional-positive-window') for n in WORKERS]


def validate(rows,spec):
    rt.require(spec.get('backend') in platform.MODES and spec['observation']=='plain' and
               spec.get('peak_policy')=='optional-positive-window','explicit shared-MM single plan required')
    reason = None
    try:
        strict = writer.validate(rows,spec)
        peak = strict['peak']
    except ValueError as error:
        if type(error) is not ValueError or str(error)!='no positive full-cohort peak window':
            raise
        peak,reason = None,str(error)
    measurement = rows[1]
    rt.require(all(not worker['latency_ns'] for worker in measurement['workers']),
               'plain shared-MM receipt contains latency samples')
    return dict(completed=measurement['completed'],wall_ns=measurement['wall_ns'],
                whole_ops_s=measurement['completed']*1e9/measurement['wall_ns'],
                worker_cpu_ns=measurement['worker_cpu_ns'],peak=peak,peak_unavailable_reason=reason,
                execution='KD_LOCAL_MMAP_LOCK' if spec['backend']=='kd' else 'NATIVE_CONTROL_MMAP_LOCK',
                delegated=False,errors=0,callback_count=measurement['after']['maps'],fault_callbacks=0)


def reject_mutations(rows,spec):
    """Run rejection checks against the actual successful 16-worker receipt."""
    validate(rows,spec)
    rt.require(spec['threads']==16,'sixteen-worker positive oracle receipt required')
    mutations = {
        'different_mm':lambda r:r[1]['workers'][0]['identity'].__setitem__('mm',1),
        'duplicate_tid':lambda r:r[1]['workers'][0]['identity'].__setitem__('tid',r[1]['workers'][1]['identity']['tid']),
        'fault_in_mmap':lambda r:r[1]['after'].__setitem__('faults',1),
        'live_vma':lambda r:r[1]['after'].__setitem__('vmas',1),
        'unexpected_clone':lambda r:r[1]['after'].__setitem__('clones',1),
        'missing_map':lambda r:r[1]['after'].__setitem__('maps',0),
        'queue_observer_enabled':lambda r:r[1]['after'].__setitem__('observe',1),
        'missing_join':lambda r:r[1].__setitem__('joined',15),
        'unexpected_latency':lambda r:r[1]['workers'][0]['latency_ns'].append(1),
        'invalid_progress':lambda r:r[1]['samples'][0]['completed'].__setitem__(0,r[1]['completed']+1),
        'wrong_cpu':lambda r:r[1]['workers'][0].__setitem__('observed_cpu',63),
    }
    rejected = []
    for name,mutate in mutations.items():
        candidate=copy.deepcopy(rows);mutate(candidate)
        try:validate(candidate,spec)
        except (rt.Failure,ValueError):rejected.append(name)
        else:raise RuntimeError('corrupt shared-MM timing receipt accepted: '+name)
    return rejected


def prerequisite_files(paths,binding,boot):
    rt.require(set(paths)==set(PREREQUISITES),'all four actual-MM correctness receipts required')
    files,results = {},{}
    for kind,path in paths.items():
        result = common.load(path)
        rt.require(result.get('passed') is True and result.get('drained') is True and
                   result.get('boot_id')==boot and result.get('mode')==binding['kernel_mmap_backend'] and
                   result.get('kernel_binding')==binding,'current-mode correctness differs: '+kind)
        files[str(path)] = rt.digest(path)
        base = path.parent
        manifests = ['source-sha256.json','runtime-source-sha256.json']
        if kind in ('mapping','completed'):
            manifests.append('binary-sha256.json')
        for name in manifests:
            manifest = base/name
            rt.require(manifest.is_file(),'required correctness manifest missing: '+str(manifest))
            files[str(manifest)] = rt.digest(manifest)
            root = base/'source' if name=='source-sha256.json' and (base/'source').exists() else base
            entries=common.load(manifest)
            rt.require(isinstance(entries,dict) and bool(entries),'empty correctness manifest: '+str(manifest))
            for relative,digest in entries.items():
                target = Path(relative) if name=='runtime-source-sha256.json' else root/relative
                files[str(target)] = digest
        results[kind] = result
    api,mapping,faults,completed = (results[key] for key in PREREQUISITES)
    rt.require(api['probe']['use_kd']==int(binding['kernel_mmap_backend']=='kd') and
               api['probe']['idle']==1 and api['probe']['errors']==0,'actual-MM API state differs')
    rt.require(len(mapping['cases'])==6 and all(row['passed'] for row in mapping['cases']) and
               mapping['api_result_sha256']==rt.digest(paths['api']),'exact mapping prerequisites differ')
    rt.require(faults['children_joined']==faults['fault_threads_joined']==16 and
               len(faults['cases'])==18,'fault/remote-mm joins differ')
    rt.require(completed['observation']['completed']==64 and completed['health']=='opened=0 closes=1 errors=0',
               'completed-fault lifetime prerequisite differs')
    files[str(paths['api'].parent/'source/tests/kernel/mmap_lock/payload/kd_mmap_probe.ko')] = api['probe_sha256']
    files[str(paths['faults'].parent/'fault_cases')] = faults['binary_sha256']
    common.verify_maps(files)
    return files


def session(out,spec,inputs,verify,*,check_oracles=False):
    writer.check.idle(out.parent);verify();out.mkdir()
    result = dict(**spec,state='RUNNING',passed=False,drained=False,accepted=False)
    rt.write_json(out/'result.json',result)
    fd = os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END)
    messages = ''
    def logs():
        nonlocal messages
        while True:
            try:messages += os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages),'kernel fault; retain payload')
    try:
        rt.command(['insmod',inputs['payload'],'observe=0'],out/'load-payload.log')
        data = rt.command([inputs['client'],str(spec['threads']),'plain'],out/'client.jsonl',timeout=120)
        rows=[json.loads(line) for line in data.splitlines()]
        logs();result['measurement'] = validate(rows,spec)
        health = Path('/sys/module/kd_mmap_writer_native/parameters/health').read_text().strip()
        rt.require(health=='files=0 mm_refs=0 destroyed=1 release_errors=0','exact file/mm lifetime did not drain')
        result['health'] = health
        rt.command(['rmmod','kd_mmap_writer_native'],out/'unload-payload.log')
        logs();verify();writer.check.idle(out.parent)
        if check_oracles:
            result['rejected_mutations']=reject_mutations(rows,spec)
        result.update(state='COMPLETE',passed=True,drained=True)
    except BaseException as error:
        result.update(state='FAILED',error=repr(error));raise
    finally:
        common.finish_logs(out,result,logs,fd)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','measure'))
    parser.add_argument('--mode',choices=tuple(platform.MODES),required=True)
    parser.add_argument('--output',type=Path,required=True)
    for kind in PREREQUISITES:
        parser.add_argument('--'+kind+'-result',type=Path)
    parser.add_argument('--inputs',type=Path)
    parser.add_argument('--reuse-inputs',type=Path,
                        help='reuse the exact first-mode timed artifacts on the other boot')
    parser.add_argument('--other-preparation',type=Path,
                        help='required successful other-mode timing preparation before measurement')
    parser.add_argument('--exploratory-host',action='store_true')
    platform.arguments(parser)
    args = parser.parse_args();platform.guest(args)
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence output required')
    writer.check.idle(out.parent);out.mkdir(parents=True)
    result = dict(state='PREPARATION',passed=False,drained=False,accepted=False,mode=args.mode,
                  boot_id=args.boot_id,sessions=[],single_round=True,action=args.action)
    rt.write_json(out/'result.json',result)
    try:
        result.update(platform.admit(args,out,strict=args.action=='measure' and not args.exploratory_host))
        support = platform.freeze_support(out)
        binding = result['kernel_binding']
        if args.action=='prepare':
            paths = {kind:getattr(args,kind+'_result') for kind in PREREQUISITES}
            rt.require(all(paths.values()),'all same-boot correctness paths required')
            prerequisites = prerequisite_files(paths,binding,args.boot_id)
            if args.reuse_inputs:
                prior = common.load(args.reuse_inputs.parent/'result.json')
                inputs = common.load(args.reuse_inputs)
                rt.require(prior['passed'] and prior['drained'] and prior['mode']!=args.mode and
                           image_identity(prior['kernel_binding'])==image_identity(binding)==inputs['image_identity'],
                           'first-mode prepared image identity differs')
                common.verify_maps(inputs['files'])
            else:
                rt.require(args.mode=='native','first artifact preparation must use Native control mode')
                source = out/'source';files = {}
                for name in ('bench/mmap_writer/timed_client.c','bench/mmap_writer/control.h',
                             'workload_modules/mmap_writer/mmap_writer_uapi.h'):
                    dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
                    files[str(ROOT/name)]=files[str(dest)]=rt.digest(dest)
                client=out/'timed-client'
                rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-pthread',
                            '-I'+str(source/'workload_modules/mmap_writer'),source/'bench/mmap_writer/timed_client.c',
                            '-o',client],out/'build-client.log',timeout=60)
                payload=paths['mapping'].parent/'source/workload_modules/mmap_writer/kd_mmap_writer_native.ko'
                files[str(client)]=rt.digest(client);files[str(payload)]=rt.digest(payload)
                files.update(support)
                inputs=dict(files=files,client=str(client),payload=str(payload),image_identity=image_identity(binding))
            result['prerequisites']={kind:dict(path=str(path),sha256=rt.digest(path)) for kind,path in paths.items()}
            rt.write_json(out/'inputs.json',inputs)
            work=[dict(writer.spec(n,'plain',0),arm=args.mode,backend=args.mode,
                       peak_policy='optional-positive-window') for n in (1,16)]
        else:
            rt.require(args.inputs and args.other_preparation,'both validated mode preparations required')
            paths={kind:getattr(args,kind+'_result') for kind in PREREQUISITES}
            rt.require(all(paths.values()),'fresh same-boot correctness required before measurement')
            prerequisites=prerequisite_files(paths,binding,args.boot_id)
            result['prerequisites']={kind:dict(path=str(path),sha256=rt.digest(path)) for kind,path in paths.items()}
            inputs=common.load(args.inputs);prior=common.load(args.inputs.parent/'result.json')
            other=common.load(args.other_preparation)
            rt.require(prior.get('kernel_binding')==binding,'selected-mode runtime policy differs from preparation')
            for receipt,mode in ((prior,args.mode),(other,'kd' if args.mode=='native' else 'native')):
                rt.require(receipt['passed'] and receipt['drained'] and receipt['mode']==mode and
                           len(receipt['sessions'])==2 and all(row['passed'] and row['drained'] for row in receipt['sessions']) and
                           len(receipt['sessions'][1].get('rejected_mutations',[]))==11 and
                           image_identity(receipt['kernel_binding'])==inputs['image_identity']==image_identity(binding),
                           'both exact-image timed-client validations required')
            other_inputs=common.load(args.other_preparation.parent/'inputs.json')
            rt.require(other_inputs==inputs,'Native/KD timed artifacts differ')
            prerequisites.update({str(args.inputs.parent/'result.json'):rt.digest(args.inputs.parent/'result.json'),
                                  str(args.other_preparation):rt.digest(args.other_preparation)})
            shutil.copyfile(args.inputs,out/'inputs.json');work=plan(args.mode)
        def verify():
            platform.verify_boot(args)
            common.verify_maps(support);common.verify_maps(prerequisites);common.verify_maps(inputs['files'])
        verify();rt.write_json(out/'plan.json',work)
        result.update(state='RUNNING',planned=len(work),image_identity=inputs['image_identity'])
        for index,spec in enumerate(work):
            name=f'{index:02d}-shared-mm-{args.mode}-t{spec["threads"]}-r00'
            print('START',name,flush=True)
            row=session(out/name,spec,inputs,verify,
                        check_oracles=args.action=='prepare' and spec['threads']==16);row['name']=name
            result['sessions'].append(row);rt.write_json(out/'result.json',result)
            print('FINISH',name,'PASS',flush=True)
        verify();writer.check.idle(out.parent)
        result.update(state='COMPLETE',passed=True,drained=True,final_idle=True,host_endpoint='PENDING')
    except BaseException as error:
        result.update(state='FAILED',error=repr(error));raise
    finally:
        rt.write_json(out/'result.json',result)
    print(json.dumps({key:result[key] for key in ('state','passed','drained','mode','planned')}))


if __name__=='__main__':
    main()
