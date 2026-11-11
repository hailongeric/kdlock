#!/usr/bin/env python3
"""Restore exact cycle1 host provenance before ordinary shutdown/settlement.

Reconstruction lowers saved source through the unchanged compiler. It requires
byte identity with the actual staged artifact; it does not assemble, publish,
ACK coverage, execute source or repeat any original kernel command.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import runpy
import select
import signal
import struct
import subprocess
import sys
import time

BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
LIVE=BASE/'managed-killable-live-02'
REPO=BASE/'host-checks-de76da8a-01/input'
INPUT=BASE/'killable-cycle-recovery-input-01'
OUT=BASE/'recovery-killable-cycle-01'
NAME='kd_rwsem_killable_fixture'
record=None
transport=None


def need(value,message):
    if not value:raise RuntimeError(message)


def read(path,bound):
    with Path(path).open('rb') as f:data=f.read(bound+1)
    need(len(data)<=bound,'read bound: '+str(path));return data


def sha(data):return hashlib.sha256(data).hexdigest()


def put(name,data):
    p=OUT/name
    with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def save():
    with (OUT/'.result-new').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write(chr(10));f.flush();os.fsync(f.fileno())
    os.replace(OUT/'.result-new',OUT/'result.json')
    fd=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def identity():
    return {'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release':os.uname().release,'taint':int(Path('/proc/sys/kernel/tainted').read_text())}


def parent(argv):
    p=Path('/proc/8108');raw=read(p/'stat',8192).decode();words=raw[raw.rfind(')')+2:].split()
    need(int(words[19])==587777 and read(p/'cmdline',16384).rstrip(b'\0').decode().split('\0')==argv and
         (p/'wchan').read_text().strip()=='__do_sys_pause','original paused controller lifetime differs')
    fds={x.name:os.readlink(x) for x in (p/'fd').iterdir()}
    need(fds.get('4')=='/dev/'+NAME+'_ctl' and fds.get('5')=='/dev/'+NAME+'_events' and
         fds.get('6')=='/dev/'+NAME,'original controller fd/session identity differs')
    return {'stat':raw,'fd_targets':fds,'argv':argv}


def status(fd,label):
    raw=os.pread(fd,8192,0);put(label+'.json',raw);return json.loads(raw)


def clear(value):
    need(value['setup_error']==value['cleanup_error']==value['overflow']==value['native_scopes']==0 and
         value['pool_idle']==1 and all(value[k]==0 for k in ('readers','writer_pending','writer','tail','owner')) and
         all(not r['active'] and (not r['task'] or (r['done'] and r['exit_state'])) for r in value['roles']),
         'actual source/task/gate/pool drain differs')


def elf_text(raw,address):
    need(len(raw)>=64 and raw[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',raw,18)[0]==62,
         'saved GNU output is not ELF64 x86_64 little endian')
    off=struct.unpack_from('<Q',raw,40)[0];size,count,names=struct.unpack_from('<3H',raw,58)
    need(size==64 and 0<names<count and off+size*count<=len(raw),'bounded saved GNU section table differs')
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,off+size*i) for i in range(count)]
    strings=sections[names];need(strings[4]+strings[5]<=len(raw),'ELF section-name extent differs')
    names_data=raw[strings[4]:strings[4]+strings[5]];found=[]
    for row in sections:
        need(row[0]<len(names_data),'ELF section name offset differs')
        end=names_data.find(b'\0',row[0]);need(end>=0,'ELF section name unterminated')
        if names_data[row[0]:end]==b'.text':found.append(row)
    need(len(found)==1,'exact one saved GNU .text required');row=found[0]
    need(row[1]==1 and row[2]&6==6 and row[3]==address and row[4]+row[5]<=len(raw),'actual GNU .text address/extent differs')
    return raw[row[4]:row[4]+row[5]]


def tool_pins():
    python=Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3')
    need(Path(sys.executable)==python and sys.prefix==str(python.parent.parent) and sys.flags.dont_write_bytecode,
         'exact translation-venv invocation with -B required')
    values={}
    for name,alias,resolved,expected in (
        ('python',python,Path('/usr/bin/python3.14'),'52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41'),
        ('objdump',Path('/usr/bin/objdump'),Path('/usr/bin/x86_64-linux-gnu-objdump'),
         '44f07f8da860b15bd4dec909f229dec536595fb170a616fe3ab29c7b21c9736f')):
        need(alias.resolve(strict=True)==resolved,'actual tool alias differs: '+name)
        data=read(resolved,32*1024**2);need(sha(data)==expected,'actual tool bytes differ: '+name)
        values[name]={'alias':str(alias),'resolved':str(resolved),'bytes':len(data),'sha256':sha(data)}
    return values


def main():
    global record,transport
    expected={'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096}
    need(os.geteuid()==0 and identity()==expected,'exact candidate identity required')
    need(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True)==BASE,'fresh output required')
    for path,floor in (('/',1024**3),(BASE,4*1024**3)):
        s=os.statvfs(path);need(s.f_bavail*s.f_frsize>=floor,'headroom floor: '+str(path))
    need(not any(k in os.environ for k in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE','LD_PRELOAD','LD_LIBRARY_PATH',
              'GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')),'inherited execution override refused')
    tools_before=tool_pins()
    old=BASE/'transport/build.py'
    need(sha(read(old,1048576))=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb','reviewed metadata helper differs')
    ns=runpy.run_path(str(old));ns['environment']()
    manifest=BASE/'host-support-de76da8a-input-01/source-sha256.json';state=BASE/'host-support-de76da8a-input-01/source-state.json'
    need(sha(read(manifest,1048576))=='71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60' and
         sha(read(state,4096))=='3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f','exact frozen de76 source identities differ')
    files=json.loads(manifest.read_text());need(len(files)==143,'exact143 snapshot required');ns['source_files'](REPO,files)
    phase1_path=BASE/'recovery-killable-exit-ack-01/result.json';phase1=read(phase1_path,1048576)
    need(sha(phase1)=='bc55fb499055250590bf9bbbdb3a325e19ca0a087ca9e231ec883bb584672d82' and
         json.loads(phase1)['status']=='EXIT_ACK_DRAIN_COMPLETE','actual phase1 must precede phase2')
    pins_path=INPUT/'history-pins.json';pins_data=read(pins_path,1048576)
    need(sha(pins_data)=='9c3f2e665cd3ddef068397edf4b509a31012ee3104fddfb25eb0dff8dafb504f','retained history manifest differs')
    pins=json.loads(pins_data);paths=list(LIVE.rglob('*'))
    need(not any(p.is_symlink() for p in paths) and {str(p.relative_to(LIVE)) for p in paths if p.is_file()}==set(pins),
         'original runtime history membership differs')
    history={};total=0
    for name,row in pins.items():
        raw=read(LIVE/name,4*1024**2);total+=len(raw)
        need(len(raw)==row['bytes'] and sha(raw)==row['sha256'] and total<=8*1024**2,'original raw history bytes differ: '+name)
        history[name]={'bytes':len(raw),'sha256':sha(raw),'data_hex':raw.hex()}
    failure=json.loads(bytes.fromhex(history['result.json']['data_hex']))
    need(failure['status']=='failed_retained' and failure['wire']['attempts']==8 and len(failure['cycles'])==1 and
         failure['cycles'][0]['published'] is True and failure['cycles'][0]['acknowledged']==0,'exact original single-cycle history differs')
    outer=read(BASE/'managed-killable-receipts-02/result.json',1048576)
    need(sha(outer)=='90b5dc2f94262b5fd41eb816c95b9737954e94793bf89ae051bdba55ac3a192a','original outer failure differs')
    argv=json.loads(outer)['commands'][0]['argv'];pidfd=os.pidfd_open(8108,0);before_parent=parent(argv)
    OUT.mkdir(mode=0o700);(OUT/'wire').mkdir();record={'status':'RESTORING_HOST_PROVENANCE','identity_before':expected,
        'phase1_sha256':sha(phase1),'history_manifest_sha256':sha(pins_data),'history_files':len(history),'history_bytes':total,
        'source_git_head':'de76da8aa2031d73f185f5864071f316c1150c08','process_before':before_parent,
        'actions':[],'wire':[],'tools_before':tools_before};save()
    ctl=os.open('/dev/'+NAME+'_ctl',os.O_RDWR|os.O_CLOEXEC);clear(status(ctl,'before'))
    bp,built=ns['checked_json']('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/full-01/result.json',
         '024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
    ip,linked=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
    build=Path(built['build']);source=Path(built['source']);core_pins={n:r['sha256'] for n,r in linked['files'].items()}
    need(len(core_pins)==16 and ns['pins'](build,core_pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'],'protected/core/source identities differ')
    boot_before=ns['boot_files']();record['boot_before']=boot_before;save()
    sys.path[:0]=[str(REPO),str(REPO/'tests/kernel')]
    from disassem.archive import ArchiveConfig,ShutdownSession
    from disassem.compiler import DiscoveryLimits
    from disassem.image_builder import flat_metadata
    from disassem.learning import (LearningCoordinator,LearningLimits,CandidateBinding,CommittedUpdateReceipt,
        PublicationReceipt,AcknowledgmentReceipt,FactKey,candidate_input_keys)
    from disassem.lowering import EntryMetadata,CodegenLimits
    from disassem.session import FdTransport,ProducerCatalog,ProducerMetadata,copied_claim,source_export_from_frame
    from disassem.wire import WireLimits,SourceExportLimits,Operation,decode_source,decode,encode,token,token_word
    from run_runtime_fixture import scan_operation_calls
    limits_raw=read(BASE/'managed-killable-input-02/limits.json',16384)
    need(sha(limits_raw)=='23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8','original39 limits differ')
    b=json.loads(limits_raw);limits=WireLimits(b['frame_capacity'],b['wire_rows'],b['wire_version_bytes'],b['wire_symbol_bytes'],b['wire_artifact_bytes'])
    raw_source=read(LIVE/'source-export.bin',b['total_source_byte_limit']+65536)
    frame=decode_source(raw_source,SourceExportLimits(3+b['dependency_page_limit'],b['entry_capacity'],b['total_source_byte_limit']),limits)
    exported=source_export_from_frame(frame,raw_source);(OUT/'saved-source').mkdir()
    snapshot,roots,calls,indirect=scan_operation_calls(exported,'/usr/bin/objdump',OUT/'saved-source',30)
    old_metadata=json.loads(read(LIVE/'source-metadata.json',1048576))
    need(list(calls)==old_metadata['calls'] and list(roots)==old_metadata['roots'] and list(indirect)==old_metadata['near_indirect_call_sites'],
         'saved source CALL/entry classification differs')
    coordinator=LearningCoordinator(exported.epoch,snapshot,LearningLimits(b['feedback_capacity'],b['cycle_capacity'],b['image_capacity'],b['image_capacity'],b['image_capacity']))
    producers=ProducerCatalog(b['image_capacity'],())
    def raw(number,name):return read(LIVE/'wire'/('attempt-'+str(number).zfill(8))/name,4*1024**2)
    claim=copied_claim(raw(3,'reply.bin'),Operation.CLAIM,coordinator,producers,0x1001,b['claim_capacity'],limits)
    need(not claim.records,'initial claim must have no prior producer/fact history');coordinator.record_claim(claim)
    need(raw(3,'request.bin')==encode(Operation.CLAIM,(token_word(exported.epoch.identity),0x1001,b['claim_capacity']),(),(),(),limits),
         'actual original CLAIM request differs')
    build_frame=decode(raw(4,'reply.bin'),Operation.BUILD_START,12,0,(limits.symbol_bytes,)*4,limits)
    candidate_id,slot,image,inputs,producer,update,owner,old_image,emission,epoch,code_base,code_capacity=build_frame.fixed
    need(slot==exported.slot_identity and old_image==exported.expected_old_image_identity==0 and token(epoch)==exported.epoch.identity,
         'actual BUILD slot/base/epoch differs')
    binding=CandidateBinding(*(token(x) for x in (candidate_id,slot,image,inputs,producer,update,owner)),None)
    need(raw(4,'request.bin')==encode(Operation.BUILD_START,(token_word(claim.identity),token_word(claim.holder_identity),epoch,slot,0),(),(),(),limits),
         'actual original BUILD request differs')
    token(emission)
    symbols=tuple(x.decode() for x in build_frame.blobs);need(symbols[3]=='kd_fixture_entry','actual entry symbol differs')
    candidate=coordinator.construct_candidate(binding,(claim.identity,),entry=roots[0],
        discovery_limits=DiscoveryLimits(*(b[k] for k in ('decode_sites','decode_window_bytes','cfg_work_steps','direct_call_edges'))),
        entry_metadata=EntryMetadata(symbols[3],tuple(sorted({c['site']+c['length'] for c in calls if c.get('operation') in ('lock','unlock','mode_change','query')})),
                                     exported.epoch.current_task_gs_offset),
        codegen_limits=CodegenLimits(b['lowered_sites'],b['lowered_text_bytes'],b['runtime_block_visits']),
        descriptor_symbol=symbols[0],source_identity_symbol=symbols[1],feedback_producer_symbol=symbols[2])
    stage=decode(raw(5,'request.bin'),Operation.STAGE_LOAD,1,0,(limits.artifact_bytes,)*3+(b['build_code_bytes'],b['build_flat_bytes']),limits)
    need(stage.fixed==(candidate_id,) and stage.blobs[:3]==tuple(x.encode() for x in
         (candidate.artifact.assembly,candidate.artifact.c_metadata,candidate.artifact.manifest_json)),
         'reconstructed textual artifact differs from actual STAGE bytes')
    for name,data in zip(('image.S','metadata.c','manifest.json'),stage.blobs[:3]):
        need(read(LIVE/'cycle-1'/name,4*1024**2)==data,'retained cycle artifact differs: '+name)
    need(flat_metadata(candidate,b['build_flat_bytes'])==stage.blobs[4] and
         read(LIVE/'cycle-1/build/image.bin',b['build_code_bytes'])==stage.blobs[3] and
         elf_text(read(LIVE/'cycle-1/build/image.elf',b['build_metadata_bytes']),code_base)==stage.blobs[3] and
         len(stage.blobs[3])<=code_capacity and read(LIVE/'cycle-1/build/image.S',4*1024**2)==stage.blobs[0],
         'actual GNU machine/ELF text/flat construction differs')
    need(decode(raw(5,'reply.bin'),Operation.STAGE_LOAD,1,0,(),limits).fixed==(candidate_id,), 'actual STAGE result differs')
    producers.register(ProducerMetadata(exported.epoch,binding.producer_identity,binding.image_identity,candidate.lowered))
    pub=decode(raw(6,'reply.bin'),Operation.PUBLISH,14,2,(),limits)
    publication,pclaim,holder,pslot,pupdate,powner,pold,pimage,retired,pepoch,pemission,pinputs,pproducer,pcandidate=pub.fixed
    need((pclaim,holder,pslot,pupdate,powner,pold,pimage,pepoch,pemission,pinputs,pproducer,pcandidate)==
         (token_word(claim.identity),token_word(claim.holder_identity),slot,update,owner,0,image,epoch,emission,inputs,producer,candidate_id),
         'actual PUB binding differs')
    keys=tuple(FactKey(exported.epoch.identity,token(r),i) for r,i in pub.rows)
    receipt=PublicationReceipt(token(publication),binding,exported.epoch,claim.identity,claim.holder_identity,keys,candidate.artifact.receipt,
        CommittedUpdateReceipt(token(publication),token(slot),token(update),token(owner),None,token(image),token(retired) if retired else None))
    need(raw(6,'request.bin')==encode(Operation.PUBLISH,(candidate_id,token_word(claim.identity),token_word(claim.holder_identity)),
         tuple((token_word(k.record_identity),k.incarnation) for k in candidate_input_keys(candidate,claim.identity)),(),(),limits),
         'actual original PUB request differs')
    coordinator.record_publication(receipt)
    ack=decode(raw(7,'reply.bin'),Operation.ACK,5,2,(),limits)
    aid,apub,aclaim,aholder,aepoch=ack.fixed
    need((apub,aclaim,aholder,aepoch)==(publication,token_word(claim.identity),token_word(claim.holder_identity),epoch) and not ack.rows and
         raw(7,'request.bin')==encode(Operation.ACK,(publication,),(),(),(),limits),'actual original empty ACK differs')
    coordinator.confirm_ack(AcknowledgmentReceipt(token(aid),token(publication),claim.identity,claim.holder_identity,()))
    end_payload=encode(Operation.CLAIM_END,(token_word(claim.identity),token_word(claim.holder_identity)),(),(),(),limits)
    need(raw(8,'request.bin')==raw(8,'reply.bin')==end_payload and
         read(LIVE/'cycle-1/claim.bin',1048576)==raw(3,'reply.bin') and read(LIVE/'cycle-1/commit.bin',1048576)==raw(6,'reply.bin') and
         read(LIVE/'cycle-1/ack.bin',1048576)==raw(7,'reply.bin'),'actual CLAIM/PUB/ACK/END correspondence differs')
    coordinator.end_claim(claim.identity,claim.holder_identity)
    proof={'producer':producer,'image':image,'epoch':epoch,'candidate':candidate_id,'code_base':code_base,
        'source_version':snapshot.version,'assembly_sha256':sha(stage.blobs[0]),'metadata_sha256':sha(stage.blobs[1]),
        'manifest_sha256':sha(stage.blobs[2]),'machine_sha256':sha(stage.blobs[3]),'flat_sha256':sha(stage.blobs[4]),
        'actual_publication':publication,'actual_ack':aid,'actual_acknowledged_keys':0,'actual_end_sequence':7}
    put('restored-producer-proof.json',(json.dumps(proof,indent=2,sort_keys=True)+chr(10)).encode())
    record['restored_producer']=proof;record['status']='HOST_PROVENANCE_RESTORED';save()
    # Every assertion above runs before the only original-controller signal.
    clear(status(ctl,'pre-signal'));record['process_pre_signal']=parent(argv)
    record['actions'].append({'action':'SIGTERM','pid':8108,'startticks':587777,'dispatched_unix':time.time()});save()
    signal.pidfd_send_signal(pidfd,signal.SIGTERM,None,0);poll=select.poll();poll.register(pidfd,select.POLLIN)
    need(poll.poll(20000),'controller actual exit not observed; no signal retry');os.close(pidfd)
    p=Path('/proc/8108');need(not p.exists() or not (p/'fd').exists() or not list((p/'fd').iterdir()),'controller fd release not observed')
    record['actions'][-1]['pidfd_exit_and_fd_release_observed']=True;save()
    class RecordedTransport(FdTransport):
        def _ioctl(self,flight):
            reserved=len(flight.request)+len(flight.output_buffer)+len(flight.header)+4096
            need(sum(x['reserved_bytes'] for x in record['wire'])+reserved<=b['wire_log_bytes'],'wire receipt bound before ioctl')
            index=len(record['wire'])+1;folder=OUT/'wire'/('attempt-'+str(index).zfill(8));folder.mkdir()
            directory=os.open(folder.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
            row={'operation':int(flight.operation),'sequence':flight.sequence,'reserved_bytes':reserved};record['wire'].append(row)
            put(str(folder.relative_to(OUT)/'request.bin'),flight.request);save()
            try:reply=super()._ioctl(flight)
            except BaseException as error:
                put(str(folder.relative_to(OUT)/'observed-envelope.bin'),bytes(flight.header))
                put(str(folder.relative_to(OUT)/'observed-output-capacity.bin'),bytes(flight.output_buffer));row['error']=repr(error);save();raise
            put(str(folder.relative_to(OUT)/'returned-envelope.bin'),bytes(flight.header));put(str(folder.relative_to(OUT)/'reply.bin'),reply.payload)
            row.update(status=reply.status,reply_bytes=len(reply.payload));save();return reply
    transport=RecordedTransport.open('/dev/'+NAME,limits,b['recovery_bytes']);cached=transport.query()
    need(cached.operation==int(Operation.CLAIM_END) and cached.sequence==7 and cached.status==0 and
         cached.request==end_payload and cached.response==end_payload,'actual cache differs from restored END7 history')
    transport.adopt_recovery(cached)
    context=(('scope','ordinary recovery; no coverage ACK or body replay'),
        ('original_runtime_history',json.dumps(history,sort_keys=True,separators=(',',':'))),
        ('phase1_receipt',phase1.decode()),('restored_producer',json.dumps(proof,sort_keys=True)))
    workflow=ShutdownSession(transport,coordinator,producers,ArchiveConfig(0x2000,b['claim_capacity'],
        str(OUT/'shutdown-archive.json'),b['archive_bytes'],0o600,context));deadline=time.monotonic()+120
    while workflow.phase.name!='COMPLETE':
        need(time.monotonic()<deadline,'shutdown observer deadline; current exact command/state retained')
        record['protocol_phase']=workflow.phase.name;save();workflow.advance()
    result=workflow.result
    need(result.archive.identity==bytes.fromhex(ns['sha'](OUT/'shutdown-archive.json')) and
         tuple(record['wire'][i]['sequence'] for i in range(len(record['wire'])))==(0,8,9,10,11),
         'durable archive/actual monotone protocol correspondence differs')
    record['archive']={'sha256':result.archive.identity.hex(),'bytes':result.archive.byte_length,
        'settled_keys':len(result.settlement.keys),'claim_keys':len(result.claim.records)};save()
    transport.close();transport=None
    record['actions'].append({'action':'RETIRE','command':0x5305,'dispatched_unix':time.time()});save()
    fcntl.ioctl(ctl,0x5305,struct.pack('<4Q',0,0,0,0));record['actions'][-1]['returncode']=0;save()
    final=status(ctl,'after-retire');clear(final)
    need(final['retired']==1 and final['setup_complete']==0 and all(final[k]==0 for k in
         ('binding_live','trace_live','runtime_live','source_live','self_held')) and all(not r['task'] for r in final['roles']),
         'ordinary runtime/provider/binding/trace retirement incomplete')
    os.close(ctl)
    need(sha(read('/usr/bin/kmod',1048576))=='6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7','ordinary module tool differs')
    record['actions'].append({'action':'rmmod','argv':['/usr/sbin/rmmod',NAME],'dispatched_unix':time.time()});save()
    with (OUT/'rmmod.stdout').open('xb') as output,(OUT/'rmmod.stderr').open('xb') as errors:
        child=subprocess.Popen(record['actions'][-1]['argv'],stdout=output,stderr=errors,stdin=subprocess.DEVNULL,start_new_session=True)
        record['actions'][-1]['pid']=child.pid;save()
        try:code=child.wait(timeout=20)
        except subprocess.TimeoutExpired:record['actions'][-1]['status']='CHILD_RETAINED';save();raise
    record['actions'][-1]['returncode']=code;save();need(code==0,'ordinary rmmod failed; no retry')
    need(not (Path('/sys/module')/NAME).exists() and all(not (Path('/dev')/(NAME+s)).exists() for s in ('','_ctl','_events')),
         'module or controls remain')
    ns['source_files'](REPO,files)
    need(identity()==expected and ns['pins'](build,core_pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'] and ns['boot_files']()==boot_before and
         sha(read(LIVE/'result.json',1048576))==sha(bytes.fromhex(history['result.json']['data_hex'])),
         'original failure/kernel/source/protected identities changed')
    need({x.split()[0] for x in Path('/proc/modules').read_text().splitlines()}<={'nls_iso8859_1'},'experimental module remains')
    need(tool_pins()==tools_before,'translation/GNU tool identity changed')
    record.update(status='ORDINARY_CLEANUP_COMPLETE',identity_after=identity(),retired_status=final,
                  original_failure_preserved=True,modules_after=Path('/proc/modules').read_text());save()
    print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json')}))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if record is not None:
            record['error']=repr(error);record['controller_pid']=os.getpid()
            record['status']='FAILED_RETAINED' if record['actions'] else 'FAILED_BEFORE_MUTATION';save()
            if record['actions']:
                while True:signal.pause()
        raise
