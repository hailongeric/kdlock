#!/usr/bin/env python3
"""Ordinary cleanup after a source-classification-only managed-killable stop.

Only the retained original controller receives one SIGTERM. No workload role is
signaled, and no source/image operation or internal state repair is performed.
"""
from pathlib import Path
import ctypes
import fcntl
import hashlib
import json
import os
import select
import signal
import struct
import subprocess
import time

BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
LIVE=BASE/'managed-killable-live-01'
OUT=BASE/'recovery-killable-regions-01'
NAME='kd_rwsem_killable_fixture'
PID=5412
START=426228
record=None


def need(value,message):
    if not value:raise RuntimeError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def read(path,limit):
    with Path(path).open('rb') as f:b=f.read(limit+1)
    need(len(b)<=limit,'read bound: '+str(path));return b


def put(name,data):
    with (OUT/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    fd=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def save():
    p=OUT/'.result-new'
    with p.open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write(chr(10));f.flush();os.fsync(f.fileno())
    os.replace(p,OUT/'result.json')
    fd=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def identity():
    return {'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release':os.uname().release,'taint':int(Path('/proc/sys/kernel/tainted').read_text())}


def process():
    p=Path('/proc')/str(PID);s=read(p/'stat',8192).decode();words=s[s.rfind(')')+2:].split()
    need(int(words[19])==START and (p/'comm').read_text().strip()=='python3','retained PID lifetime differs')
    argv=read(p/'cmdline',16384).rstrip(b'\0').decode().split('\0')
    expected=json.loads(read(BASE/'managed-killable-receipts-01/result.json',1048576))['commands'][0]['argv']
    need(argv==expected,'retained runner exact argv differs')
    fds={x.name:os.readlink(x) for x in (p/'fd').iterdir()}
    need(fds.get('4')=='/dev/'+NAME+'_ctl' and fds.get('5')=='/dev/'+NAME+'_events' and
         fds.get('6')=='/dev/'+NAME and (p/'wchan').read_text().strip()=='__do_sys_pause',
         'retained controller fd/paused identity differs')
    return {'stat':s,'argv':argv,'fd_targets':fds,'status':read(p/'status',16384).decode()}


def status(fd,label):
    raw=os.pread(fd,8192,0);put(label+'.json',raw);return json.loads(raw)


def clear(value):
    need(value['setup_error']==value['cleanup_error']==value['overflow']==0 and value['events']==46 and
         all(value[k]==0 for k in ('readers','writer_pending','writer','tail','owner','native_scopes')) and value['pool_idle']==1,
         'exact gate/queue/native/overflow preconditions differ')
    need(all(not r['active'] and (not r['task'] or (r['done'] and r['exit_state'])) for r in value['roles']),
         'actual role completion/exit preconditions differ')


def main():
    global record
    need(os.geteuid()==0 and identity()=={'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0',
         'release':'7.0.0-38-kdrebuild8','taint':4096},'exact candidate identity required')
    need(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True)==BASE,'fresh output required')
    for mount,floor in (('/',1024**3),(BASE,4*1024**3)):
        s=os.statvfs(mount);need(s.f_bavail*s.f_frsize>=floor,'headroom floor: '+str(mount))
    failed=read(LIVE/'result.json',1048576)
    need(sha(failed)=='ffd70cfe0dbc43302a9e49d3bea79d1c5467f144db714e504bee1982452ecac7','original retained failure differs')
    result=json.loads(failed)
    need(result['status']=='failed_retained' and result['error']=="AssertionError('killable body lacks one exact typed source CALL')" and
         result['controller_pid']==PID and result['live_children']=={} and result['wire']['attempts']==2 and
         [x['name'] for x in result['cases']]==['ready-before-fatal-cancel','reader-drain-cancel','queued-exit-before-holder-release'] and
         not result.get('cycles') and not result.get('fixed_image'),'only saved cold cases/SOURCE stop permitted')
    need(sha(read(BASE/'managed-killable-receipts-01/result.json',1048576))==
         '17634f4dbec9d680e885f11cedc6a2ea877b8581cd6d717fe181b2d7994a9f32','outer failure differs')
    wire=LIVE/'wire';need({p.name for p in wire.iterdir()}=={'attempt-00000001','attempt-00000002'},'unexpected wire operation history')
    query=json.loads(read(wire/'attempt-00000001/result.json',8192));source=json.loads(read(wire/'attempt-00000002/result.json',8192))
    need(query['operation']==query['sequence']==query['returned_sequence']==query['status']==0 and query['completed_response'] is True and
         source['operation']==8 and source['sequence']==source['returned_sequence']==1 and source['status']==0 and
         source['completed_response'] is True,'cached preflight/SOURCE receipts differ')
    request=read(wire/'attempt-00000002/request.bin',1024);reply=read(wire/'attempt-00000002/reply.bin',16384)
    need(sha(request)=='8820465cd3023f7864c0b641c7f65d2fd6d7dada86df40a627ebcd2f43bd6011' and
         sha(reply)=='d7751fd6e99af063d21f29d8cc327578f45ea912c963b31e43cbc2058b996a89' and
         struct.unpack('<4Q',request)==(1,8,32,0) and struct.unpack_from('<11Q',reply)[10]==0 and
         read(LIVE/'source-export.bin',16384)==reply,'exact SOURCE request/reply/current_image0 differs')
    events=read(LIVE/'observations-failure.bin',1048576)
    need(sha(events)=='e439cbf021e994101c2efc81fb7ab7605465ac8a5a92feb20bf2f5ff72583f19' and
         struct.unpack_from('<5Q',events)==(1,20,131072,46,0) and len(events)==7400 and
         all(row[0] not in (23,24,25) and row[10]==0 for row in struct.iter_unpack('<20Q',events[40:])),
         'saved events include unexpected image/JIT work')
    for child in result['children']:need(not (Path('/proc')/str(child['pid'])).exists(),'recorded child PID still exists')
    need(sha(read(BASE/'build-01/signed'/ (NAME+'.ko'),1048576))==
         '74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8','signed module differs')
    pidfd=os.pidfd_open(PID,0);before=process()
    OUT.mkdir(mode=0o700);record={'status':'PREFLIGHT','identity_before':identity(),'process_before':before,
        'original_failure_sha256':sha(failed),'source_request_sha256':sha(request),'source_reply_sha256':sha(reply),
        'raw_event_sha256':sha(events),'wire_operations':[[0,0,0],[8,1,0]],'actions':[]};save()
    ctl=os.open('/dev/'+NAME+'_ctl',os.O_RDWR|os.O_CLOEXEC)
    current=status(ctl,'before');clear(current)
    need(current['setup_complete']==1 and all(current[k]==1 for k in
         ('binding_live','trace_live','runtime_live','source_live','self_held')) and current['retired']==0,'retained setup roles differ')
    record['status_before']=current;record['process_pre_dispatch']=process();save()
    action={'action':'SIGTERM','pid':PID,'startticks':START,'dispatched_unix':time.time()};record['actions'].append(action);save()
    signal.pidfd_send_signal(pidfd,signal.SIGTERM,None,0)
    poll=select.poll();poll.register(pidfd,select.POLLIN);need(poll.poll(20000),'original task exit not observed; no signal retry')
    action['pidfd_exit_observed']=True
    p=Path('/proc')/str(PID)
    need(not p.exists() or not (p/'fd').exists() or not list((p/'fd').iterdir()),'original descriptor release not observed')
    os.close(pidfd);action['closed_file_descriptors']=True;save()
    # Reopening the existing exclusive channel after actual file release does
    # not adopt/replay a source command. QUERY only reads its retained cache.
    channel=os.open('/dev/'+NAME,os.O_RDWR|os.O_CLOEXEC)
    buffer=ctypes.create_string_buffer(16384)
    header=bytearray(struct.pack('<9Q',1,0,0,0,0,ctypes.addressof(buffer),len(buffer),0,0))
    fcntl.ioctl(channel,0xC0484B00,header,True);words=struct.unpack('<9Q',header)
    need(words[7]<=len(buffer),'QUERY exceeds explicit capacity');actual=buffer.raw[:words[7]]
    put('query-envelope.bin',bytes(header));put('query-reply.bin',actual)
    need(words[:3]==(1,0,0) and words[8]==0 and actual==struct.pack('<6Q',1,8,1,0,len(request),len(reply))+request+reply,
         'actual cache differs; no RETIRE or replay')
    os.close(channel);record['cached_SOURCE_verified']=True;save()
    action={'action':'RETIRE','command':0x5305,'dispatched_unix':time.time()};record['actions'].append(action);save()
    fcntl.ioctl(ctl,0x5305,struct.pack('<4Q',0,0,0,0));action['returncode']=0;save()
    final=status(ctl,'after-retire');clear(final)
    need(final['retired']==1 and final['setup_complete']==0 and all(final[k]==0 for k in
         ('binding_live','trace_live','runtime_live','source_live','self_held')) and all(not r['task'] for r in final['roles']),
         'ordinary teardown did not end exact remaining roles')
    os.close(ctl);record['retired_status']=final;save()
    need(sha(read('/usr/bin/kmod',1048576))=='6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7','ordinary rmmod tool differs')
    action={'action':'rmmod','argv':['/usr/sbin/rmmod',NAME],'dispatched_unix':time.time()};record['actions'].append(action);save()
    with (OUT/'rmmod.stdout').open('xb') as output,(OUT/'rmmod.stderr').open('xb') as errors:
        child=subprocess.Popen(action['argv'],stdin=subprocess.DEVNULL,stdout=output,stderr=errors,start_new_session=True)
        action['pid']=child.pid;save()
        try:code=child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            action['status']='CHILD_RETAINED';save();raise
    action['returncode']=code;save();need(code==0,'ordinary rmmod failed; no retry')
    need(not (Path('/sys/module')/NAME).exists() and all(not (Path('/dev')/(NAME+suffix)).exists() for suffix in ('','_ctl','_events')),
         'fixture module/devices still present')
    need(identity()==record['identity_before'],'kernel identity changed')
    need({row.split()[0] for row in Path('/proc/modules').read_text().splitlines()}<={'nls_iso8859_1'},'experimental module remains')
    record.update(status='ORDINARY_CLEANUP_COMPLETE',identity_after=identity(),modules_after=Path('/proc/modules').read_text(),
                  original_failure_preserved=sha(read(LIVE/'result.json',1048576))==record['original_failure_sha256'])
    need(record['original_failure_preserved'],'original failed result changed');save()
    print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json')}))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if record is not None:record['status']='FAILED_OR_INCOMPLETE';record['error']=repr(error);save()
        raise
