#!/usr/bin/env python3
"""End the exact fixture C exit barrier after completed C/W bodies.

The original controller, channel, published image and feedback remain retained.
This phase sends one C EXIT_ACK and observes actual task/storage completion only.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import select
import struct
import time

BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
LIVE=BASE/'managed-killable-live-02'
OUT=BASE/'recovery-killable-exit-ack-01'
NAME='kd_rwsem_killable_fixture'
STARTS={8108:587777,8134:587939,8135:587940}
record=None


def need(value,message):
    if not value:raise RuntimeError(message)


def read(path,bound):
    with Path(path).open('rb') as f:data=f.read(bound+1)
    need(len(data)<=bound,'read bound: '+str(path));return data


def sha(data):return hashlib.sha256(data).hexdigest()


def put(name,data):
    with (OUT/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    descriptor=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def save():
    with (OUT/'.result-new').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write(chr(10));f.flush();os.fsync(f.fileno())
    os.replace(OUT/'.result-new',OUT/'result.json')
    descriptor=os.open(OUT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def identity():
    return {'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release':os.uname().release,'taint':int(Path('/proc/sys/kernel/tainted').read_text())}


def process(pid,argv):
    p=Path('/proc')/str(pid);raw=read(p/'stat',8192).decode();words=raw[raw.rfind(')')+2:].split()
    need(int(words[19])==STARTS[pid] and read(p/'cmdline',16384).rstrip(b'\0').decode().split('\0')==argv,
         'exact process lifetime/argv differs: '+str(pid))
    fds={entry.name:os.readlink(entry) for entry in (p/'fd').iterdir()}
    need(fds.get('4')=='/dev/'+NAME+'_ctl','exact control fd differs: '+str(pid))
    if pid==8108:
        need((p/'wchan').read_text().strip()=='__do_sys_pause' and fds.get('5')=='/dev/'+NAME+'_events' and
             fds.get('6')=='/dev/'+NAME,'retained controller/channel differs')
    else:need(int(words[1])==8108,'original child parent differs')
    return {'stat':raw,'argv':argv,'fd_targets':fds,'status':read(p/'status',16384).decode(),'wchan':(p/'wchan').read_text()}


def status(fd,label):
    data=os.pread(fd,8192,0);put(label+'.json',data);return json.loads(data)


def events(label):
    fd=os.open('/dev/'+NAME+'_events',os.O_RDONLY|os.O_CLOEXEC)
    try:
        header=os.pread(fd,40,0);need(len(header)==40,'event header truncated')
        abi,words,capacity,count,overflow=struct.unpack('<5Q',header)
        need((abi,words,capacity,overflow)==(1,20,131072,0) and count<=capacity,'bounded exact event prefix differs')
        data=bytearray(header)
        for index in range(count):
            row=os.pread(fd,160,40+index*160);need(len(row)==160,'event row truncated');data.extend(row)
    finally:os.close(fd)
    put(label+'.bin',bytes(data));return bytes(data)


def clear(value,scopes):
    need(value['setup_error']==value['cleanup_error']==value['overflow']==0 and value['pool_idle']==1 and
         all(value[k]==0 for k in ('readers','writer_pending','writer','tail','owner')) and value['native_scopes']==scopes,
         'gate/pool/storage state differs')
    need(value['setup_complete']==1 and value['retired']==0 and
         all(value[k]==1 for k in ('binding_live','trace_live','runtime_live','source_live','self_held')),
         'runtime/source/channel ownership must remain retained')
    c,w=value['roles'][2],value['roles'][3]
    need(c['pid']==8134 and w['pid']==8135 and all(r[k]==1 for r in (c,w) for k in ('done','effects','steps')) and
         all(r['error']==r['result']==0 for r in (c,w)) and w['helper_entered']==w['helper_returned']==1,
         'completed C/W effects/helper identity differs')


def main():
    global record
    need(os.geteuid()==0 and identity()=={'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0',
         'release':'7.0.0-38-kdrebuild8','taint':4096},'exact candidate identity required')
    need(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True)==BASE,'fresh output required')
    for path,floor in (('/',1024**3),(BASE,4*1024**3)):
        s=os.statvfs(path);need(s.f_bavail*s.f_frsize>=floor,'headroom floor: '+str(path))
    failure=read(LIVE/'result.json',1048576)
    need(sha(failure)=='e63803abd5888a13f5e624b4272ce4b5819dcc5695be416a0c7df339c9e884ce','original K02 failure differs')
    prior=json.loads(failure)
    need(prior['status']=='failed_retained' and prior['controller_pid']==8108 and prior['live_children']=={'2':8134,'3':8135} and
         prior['error']=="TimeoutError('actual child exit is unverified; holder remains unchanged')" and
         prior['before_exit_ack'][-1]['role']==3 and prior['before_exit_ack'][-1]['status']['roles'][3]['helper_returned']==1,
         'exact W ACK/order failure differs')
    outer=read(BASE/'managed-killable-receipts-02/result.json',1048576);outer_value=json.loads(outer)
    need(sha(outer)=='90b5dc2f94262b5fd41eb816c95b9737954e94793bf89ae051bdba55ac3a192a','actual original outer failure differs')
    argv=outer_value['commands'][0]['argv']
    need(prior['wire']['attempts']==8 and len(prior['cycles'])==1 and prior['cycles'][0]['published'] is True and
         prior['cycles'][0]['acknowledged']==0,'original published-image/feedback history differs')
    for child in prior['children']:
        if child['pid'] not in (8134,8135):need(not (Path('/proc')/str(child['pid'])).exists(),'another original child PID remains')
    pidfds={pid:os.pidfd_open(pid,0) for pid in STARTS};procs={pid:process(pid,argv) for pid in STARTS}
    OUT.mkdir(mode=0o700);record={'status':'PREFLIGHT','identity_before':identity(),'processes_before':procs,
        'original_failure_sha256':sha(failure),'outer_failure_sha256':sha(outer),'actions':[],
        'scope':'One completed C EXIT_ACK and exact C/W task/storage drain only; controller/channel/image/facts remain live.'};save()
    ctl=os.open('/dev/'+NAME+'_ctl',os.O_RDWR|os.O_CLOEXEC)
    before=status(ctl,'before');clear(before,2)
    need(before['roles'][2]['active']==1 and before['roles'][3]['active']==0 and
         before['roles'][2]['exit_state']==before['roles'][3]['exit_state']==0,'exact C barrier/W exit state differs')
    raw=events('events-before');need(sha(raw)=='876a0ac991b0f8bb8667fd41687fb290442979d1763db003ae915dee4a733d95' and
         struct.unpack_from('<5Q',raw)[3]==88,'actual saved current88 event identity differs')
    rows=list(struct.iter_unpack('<20Q',raw[40:]));need(rows[72][0]==19 and rows[72][14]==2 and rows[72][15]==0 and
         rows[87][0]==16 and rows[72][7]==rows[87][7] and rows[87][1]==before['roles'][3]['task'],
         'actual W physical ACK/source-drop proof differs')
    record['status_before']=before;record['event_before_sha256']=sha(raw)
    record['processes_pre_dispatch']={pid:process(pid,argv) for pid in STARTS};save()
    action={'action':'C_EXIT_ACK','command':0x5306,'role':2,'dispatched_unix':time.time()};record['actions'].append(action);save()
    fcntl.ioctl(ctl,0x5306,struct.pack('<4Q',2,0,0,0));action['returncode']=0;save()
    poll=select.poll()
    for pid in (8134,8135):poll.register(pidfds[pid],select.POLLIN)
    pending={pidfds[8134],pidfds[8135]};deadline=time.monotonic()+30
    while pending:
        need(time.monotonic()<deadline,'C/W exit observation timed out; no ACK retry or signal')
        for fd,mask in poll.poll(250):
            if mask & select.POLLIN:pending.discard(fd)
    action['pidfd_exit_observed']=[8134,8135];save()
    final=status(ctl,'after');clear(final,0)
    need(all(not final['roles'][i]['active'] and final['roles'][i]['exit_state'] for i in (2,3)),
         'actual task exit/source observer completion differs')
    after_raw=events('events-after');need(after_raw[40:40+len(raw)-40]==raw[40:] and
         not any(row[0] in (6,23,24,25) for row in struct.iter_unpack('<20Q',after_raw[len(raw):])),
         'prefix changed or new grant/source execution appeared after metadata exit ACK')
    parent=process(8108,argv);os.close(ctl)
    for fd in pidfds.values():os.close(fd)
    need(identity()==record['identity_before'] and read(LIVE/'result.json',1048576)==failure and
         read(BASE/'managed-killable-receipts-02/result.json',1048576)==outer,'original identity/failure changed')
    record.update(status='EXIT_ACK_DRAIN_COMPLETE',identity_after=identity(),status_after=final,
                  controller_after=parent,event_after_sha256=sha(after_raw),runtime_retained=True)
    save();print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json')}))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if record is not None:record['status']='FAILED_OR_INCOMPLETE';record['error']=repr(error);save()
        raise
