#!/usr/bin/env python3
"""VM-only ordinary rwsem compatibility followed by a native-local MM check.

Inputs require actual future kernel6 postboot and binary identities. Failed or
outstanding actors are retained. No forced cleanup, signal retry, reboot or JIT
activation is present. The companion plan defines the caller's object-wide lane.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

RELEASE = '7.0.0-38-kdrebuild6'
CORE = '532b68a65bdf96504e2cede6c23a5bc1476d94e9'
FIXTURE = '80c272e5f134d9a499c03782f71064d04fae25c3'
WORK = Path('/mnt/kdlock-builds/kdlock-main-work')
MODULES = ('kd_rwsem_api_fixture', 'kd_mmap_api_provider')
DEVICES = ('kd_rwsem_api', 'kd_mmap_api')
TAINT_MODULE_BITS = (1 << 12) | (1 << 13)
MAX_LOG = 8 * 1024 * 1024
out = None
record = None

COMPAT_DRIVER = r'''
import fcntl, json, os, signal, sys, time
from pathlib import Path
root = Path(sys.argv[1])
value = {'pid':os.getpid(),'phase':'OPENING','run_errno':None,'stop_errno':None,'drained':False}
def save():
    temporary = root/'.compat-result.new'
    with temporary.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,root/'compat-result.json')
    descriptor=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
def status(label):
    with open('/dev/kd_rwsem_api','rb',buffering=0) as stream:
        raw=stream.read(4097)
    with (root/(label+'.json')).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if len(raw)>4096:
        raise RuntimeError('status read exceeds source page bound')
    return json.loads(raw)
def drained(state):
    return state['pool_idle']==1 and state['module_hold']==0 and state['created']==state['joined'] and all(
        worker['task']==0 and worker['nonowner_open']==0 for worker in state['workers'])
def passed(state):
    return drained(state) and state['state']==2 and state['error']==0 and state['case_index']==11 and \
        state['created']>0 and state['count_overflow']==0 and state['turn_wait_proved']==1 and \
        state['turn_cleanup_proved']==1 and state['try_returns']==[1,1,0,0] and \
        len(state['cases'])==12 and all(case['ran']==1 and case['result']==0 for case in state['cases'])
fd=os.open('/dev/kd_rwsem_api',os.O_RDWR|os.O_CLOEXEC)
value['fd']=fd
save()
try:
    value['before']=status('compat-before')
    if value['before']['state']!=0:
        raise RuntimeError('compatibility module is not cold')
    value['phase']='RUN_ENTERED'
    save()
    try:
        fcntl.ioctl(fd,0x5101,0)
        value['run_errno']=0
    except OSError as error:
        value['run_errno']=error.errno
    value['after']=status('compat-after-run')
    if value['run_errno']==0 and passed(value['after']):
        value.update(phase='COMPAT_PASS',drained=True)
    else:
        value['phase']='STOP_ENTERED'
        save()
        try:
            fcntl.ioctl(fd,0x5102,0)
            value['stop_errno']=0
        except OSError as error:
            value['stop_errno']=error.errno
        value['after_stop']=status('compat-after-stop')
        value['drained']=value['stop_errno']==0 and drained(value['after_stop'])
        value['phase']='COMPAT_FAILED_DRAINED' if value['drained'] else 'COMPAT_FAILED_RETAINED'
except Exception as error:
    value.update(phase='COMPAT_FAILED_RETAINED',error=repr(error),drained=False)
save()
if not value['drained']:
    # Retain the open fd and its code reference. A later operator can inspect
    # actual controls and request ordinary STOP through another privileged fd.
    while True:
        signal.pause()
os.close(fd)
value['fd_closed']=True
save()
sys.exit(0 if value['phase']=='COMPAT_PASS' else 1)
'''


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pin(row):
    path = Path(row['path'])
    require(path.is_absolute() and path.resolve(strict=True) == path and path.is_file() and
            re.fullmatch('[0-9a-f]{64}', row['sha256']) and digest(path) == row['sha256'],
            'actual canonical file pin differs: ' + str(path))
    return path


def pin_tool(row):
    path = Path(row['path'])
    require(path.is_absolute() and path.is_file() and
            re.fullmatch('[0-9a-f]{64}', row['sha256']) and digest(path.resolve(strict=True))==row['sha256'],
            'actual tool alias/binary pin differs: ' + str(path))
    # kmod uses its invocation basename to distinguish insmod/rmmod/modinfo.
    return path


def pinned_json(row):
    return json.loads(pin(row).read_text())


def save(name, value):
    target = out/name
    temporary = target.with_name('.' + target.name + '.new')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def available(path):
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def identity():
    return {'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release':os.uname().release,
            'taint':int(Path('/proc/sys/kernel/tainted').read_text())}


def idle():
    loaded = Path('/proc/modules').read_text()
    require(not any(line.split()[0] in MODULES or 'fixture' in line.split()[0]
                    for line in loaded.splitlines()), 'experimental module remains loaded')
    require(not any((Path('/dev')/name).exists() for name in DEVICES), 'experimental device remains')
    rows = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            name = (process/'comm').read_text().strip()
            arguments = (process/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            if name in ('make','gmake','gcc','gcc-15','cc1','cc1plus','clang','ld','ld.bfd','as',
                        'objtool','fstrim','insmod','rmmod') or name.startswith(
                        ('kd-rwapi/','kd-fixture/','kd-scene/','kd-reader/')) or any(
                        token in arguments for token in ('run_runtime_fixture.py','run_rwsem_runtime_fixture.py',
                                                         'run_rwlock_runtime_fixture.py')):
                rows.append({'pid':int(process.name),'comm':name,'argv':arguments})
            for task in (process/'task').iterdir():
                if '\nState:\tD ' in '\n' + (task/'status').read_text():
                    rows.append({'pid':int(process.name),'tid':int(task.name),'blocked':True})
        except (FileNotFoundError, ProcessLookupError):
            continue
    require(not rows, 'workload/build/blocked actor remains: ' + repr(rows))
    return {'identity':identity(),'modules':loaded,'activity':rows}


def running_notes():
    with Path('/sys/kernel/notes').open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024, 'running note extent exceeds bound')
    found, offset = [], 0
    while offset < len(raw):
        require(offset + 12 <= len(raw), 'partial running note header')
        names, size, kind = struct.unpack_from('<III',raw,offset)
        offset += 12
        name_end, value_start = offset + names, offset + ((names+3)&~3)
        value_end = value_start + size
        require(name_end <= len(raw) and value_end <= len(raw), 'partial running note payload')
        if raw[offset:name_end].rstrip(b'\0') == b'GNU' and kind == 3:
            found.append(raw[value_start:value_end].hex())
        offset = value_start + ((size+3)&~3)
    require(offset == len(raw) and len(found) == 1, 'exact one running GNU Build ID required')
    return raw, found[0]


def recovery(row, floor):
    value = pinned_json(row)
    require(value['hostname']=='Super-Server' and value['pid']==257489 and
            value['exe']=='/usr/bin/qemu-system-x86_64', 'actual QEMU host identity differs')
    captured = datetime.datetime.fromisoformat(value['utc']).timestamp()
    require(0 <= time.time()-captured <= 900, 'fresh recovery observation required')
    images = value['images']
    require(len(images)==3 and all(item['open_fds'] and item['path']==item['realpath'] for item in images),
            'three actual attached image references absent')
    replies = {item['command']:item['output'] for item in value['hmp']}
    marker = 'List of snapshots present on all disks:'
    require('VM status: running' in replies.get('info status','') and marker in replies.get('info snapshots',''),
            'running all-disk snapshot listing absent')
    require('kdlock-builddisk-clean-20261031' in replies['info snapshots'].split(marker,1)[1].split('List of partial',1)[0],
            'complete recovery snapshot absent')
    require(min(item['host_available'] for item in images) >= floor, 'host headroom below explicit floor')
    return {'sha256':row['sha256'],'captured_unix':captured}


def execute(label, argv, deadline, environment, retained_report=None):
    require(time.monotonic() < deadline, 'observer deadline expired before dispatch')
    row = {'label':label,'argv':list(map(str,argv)),'started_unix':time.time()}
    record['commands'].append(row)
    save('result.json',record)
    stdout, stderr = out/(label+'.stdout'), out/(label+'.stderr')
    with stdout.open('xb') as output, stderr.open('xb') as errors:
        child = subprocess.Popen(row['argv'],stdout=output,stderr=errors,env=environment,
                                 cwd=out,start_new_session=True)
        row['pid'] = child.pid
        try:
            row['proc_start'] = Path('/proc',str(child.pid),'stat').read_text()
        except (FileNotFoundError, ProcessLookupError):
            row['proc_start'] = None
        save('result.json',record)
        while child.poll() is None:
            retained = retained_report and retained_report.exists() and json.loads(retained_report.read_text()).get('phase') == 'COMPAT_FAILED_RETAINED'
            if retained or time.monotonic() >= deadline or stdout.stat().st_size > MAX_LOG or stderr.stat().st_size > MAX_LOG:
                row['status'] = 'CHILD_RETAINED_DRAIN_UNVERIFIED'
                row['elapsed_seconds'] = time.time()-row['started_unix']
                save('result.json',record)
                raise RuntimeError('child retained, no termination/retry/unload: ' + str(child.pid))
            time.sleep(0.1)
        row['returncode'] = child.returncode
        row['elapsed_seconds'] = time.time()-row['started_unix']
    row['stdout_sha256'], row['stderr_sha256'] = digest(stdout), digest(stderr)
    save('result.json',record)
    require(stdout.stat().st_size <= MAX_LOG and stderr.stat().st_size <= MAX_LOG, 'command output exceeds bound')
    return row, stdout


def absent(name, device):
    require(not (Path('/sys/module')/name).exists() and not (Path('/dev')/device).exists() and
            name not in {line.split()[0] for line in Path('/proc/modules').read_text().splitlines()},
            'module/control remains after ordinary unload')


def compat_ok(value):
    state = value['after']
    return value['phase']=='COMPAT_PASS' and value['run_errno']==0 and value.get('fd_closed') is True and value['drained'] and \
        state['state']==2 and state['error']==0 and state['pool_idle']==1 and state['module_hold']==0 and \
        state['joined']==state['created'] and len(state['cases'])==12 and \
        all(case['ran']==1 and case['result']==0 for case in state['cases']) and \
        state['turn_wait_proved']==1 and state['turn_cleanup_proved']==1 and not state['count_overflow']


def mmap_ok(value):
    require(value['status']=='syscall_completion_pass' and value['overall_pass'] is True and
            value['threads']==4 and value['created_threads']==4 and value['iterations_per_thread']==64 and
            value['deadline_ms']==60000 and value['completed_iterations']==256 and
            not value['deadline_exceeded'] and not value['worker_errors'] and not value['arena_cleanup_errno'] and
            value['kd_observations']=='native_gate_only', 'actual mmap syscall completion failed')
    page = value['page_bytes']
    require(page > 0 and len(value['workers'])==4, 'actual worker/page metadata differs')
    for index, worker in enumerate(value['workers']):
        require(worker['id']==index and worker['tid']>0 and worker['completed']==64 and
                worker['mmap_attempts']==worker['mmap_successes']==192 and
                worker['munmap_attempts']==worker['munmap_successes']==128 and
                worker['mincore_attempts']==worker['unmapped_page_checks']==256 and worker['reuse_successes']==64 and
                worker['fresh_zero_bytes']==worker['written_bytes']==worker['readback_bytes']==256*page and
                worker['error']=='none' and not worker['deadline_reached'], 'per-worker syscall bytes/counts differ')
    selected = value['selected_gate']
    require(selected['requested'] and not selected['cleanup_required'] and not selected['cleanup_failed'] and
            selected['native_counts_balanced'] and all(selected[key]==0 for key in
            ('open_errno','start_errno','end_errno','query_errno','close_errno','wait_errno')), 'MM cleanup/result failed')
    first, final = selected['start'], selected['final']
    require(final['state']==2 and final['cleanup_required']==0 and final['native_capacity']==64 and
            final['pool_idle']==1 and not final['gate_locked'] and not final['gate_write_locked'] and
            not final['gate_contended'] and not final['source_calls'] and not final['count_overflow'] and
            final['native_read_acquires']>0 and final['native_write_acquires']>0 and final['native_downgrades']>0,
            'MM final gate/native observations differ')
    require(first['owner_is_current']==final['owner_is_current']==1 and
            first['owner_pid']==first['owner_tgid']==value['pid'], 'MM actual original owner differs')
    require(all(first[key]==final[key] and final[key] != 0 for key in
            ('owner_pid','owner_tgid','mm_identity','object_identity','gate_identity')), 'MM exact binding identity changed')
    require(final['native_write_acquires']==final['native_write_releases']+final['native_downgrades'] and
            final['native_read_releases']==final['native_read_acquires']+final['native_downgrades'],
            'MM actual native event balance differs')


def main():
    global out, record
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--seconds',required=True,type=int)
    args = parser.parse_args()
    require(os.geteuid()==0 and 1 <= args.seconds <= 600, 'guest root and explicit observer bound required')
    config = pinned_json({'path':args.config,'sha256':args.config_sha256})
    require(config['format']=='kdlock.native-api-live.v1' and config['core_git_head']==CORE and
            config['fixture_git_head']==FIXTURE and config['object_contract']==
            'all_selected_users_ordinary_irq_enabled_task_context_no_external_mm_observers',
            'reviewed source/object-wide context contract differs')
    for key in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH'):
        require(key not in os.environ, 'execution environment override: ' + key)
    root = Path(args.output)
    require(root.is_absolute() and root.resolve()==root and WORK in root.parents and not os.path.lexists(root),
            'fresh isolated output required')
    files = config['kernel_files']
    require(set(files)=={'vmlinux','.config','System.map','Module.symvers','bzImage','kernel.release','utsrelease.h'},
            'exact future kernel artifact set required')
    for row in files.values(): pin(row)
    require(set(config['source_files'])=={'compatibility','provider','client','abi'}, 'exact fixture source set required')
    for row in config['source_files'].values(): pin(row)
    for row in config['provenance'].values(): pin(row)
    require(config['source_files']['compatibility']['sha256']=='42648850979577360d88a2fd4066f48ea31e0ac46f29e5666de6ca0b6ac0f50a',
            'twelve-scene compatibility source differs')
    for key in ('compatibility','provider','client'): pin(config['binaries'][key])
    tools = {name:str(pin_tool(row)) for name,row in config['tools'].items()}
    require(set(tools)=={'insmod','rmmod','modinfo','dmesg'}, 'explicit actual module/diagnostic tools required')
    current = identity()
    require(current=={'boot':config['boot_id'],'release':RELEASE,'taint':0}, 'actual fresh untainted kernel6 boot required')
    require(pin(files['kernel.release']).read_text().strip()==RELEASE, 'actual generated release differs')
    notes, build_id = running_notes()
    require(build_id==config['build_id'], 'running GNU Build ID differs from future linked identity')
    proof, gs, helper_return = map(pinned_json,(config['postboot_result'],config['gs_proof'],config['postboot_return']))
    require(proof['phase']=='POSTBOOT_IDENTITY_VERIFIED' and proof['boot_id']==current['boot'] and
            proof['running_build_id']==build_id and int(proof['tainted'])==0 and helper_return['returncode']==0,
            'actual postboot helper0 and saved success phase required')
    require(gs['verified_for_running_kernel'] is True and gs['boot_id']==current['boot'] and
            gs['build_id']==build_id and gs['kernel_release']==RELEASE and
            gs['kernel_elf_sha256']==files['vmlinux']['sha256'] and
            gs['kernel_config_sha256']==files['.config']['sha256'], 'actual full linked/running proof differs')
    require(config['root_floor']>=1024**3 and config['output_floor']>=4*1024**3 and config['host_floor']>=4*1024**3,
            'explicit live headroom floors differ')
    before = idle()
    rec = recovery(config['recovery'],config['host_floor'])
    require(available('/')>=config['root_floor'] and available(WORK)>=config['output_floor'], 'guest headroom')
    out = root
    out.mkdir(mode=0o700)
    record = {'status':'PREPARED','configuration':config,'config_sha256':args.config_sha256,
              'identity_before':before,'recovery':rec,'commands':[],
              'scope':'Native-local ordinary APIs and actual syscalls. No JIT or performance claim.'}
    save('result.json',record)
    with (out/'running-notes.bin').open('xb') as stream:
        stream.write(notes)
        stream.flush()
        os.fsync(stream.fileno())
    environment = dict(os.environ,LC_ALL='C',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    deadline = time.monotonic()+args.seconds
    row, unused = execute('dmesg-before',[tools['dmesg']],deadline,environment)
    require(row['returncode']==0, 'initial kernel log capture failed')
    for kind,name in (('compatibility',MODULES[0]),('provider',MODULES[1])):
        row, text = execute(kind+'-modinfo',[tools['modinfo'],'-F','name',pin(config['binaries'][kind])],deadline,environment)
        require(row['returncode']==0 and text.read_text().strip()==name, 'module name differs')
        row, text = execute(kind+'-vermagic',[tools['modinfo'],'-F','vermagic',pin(config['binaries'][kind])],deadline,environment)
        require(row['returncode']==0 and text.read_text().split()[0]==RELEASE, 'future module vermagic differs')
    row, unused = execute('compat-insmod',[tools['insmod'],pin(config['binaries']['compatibility']),
                         'native_capacity=3','wait_timeout_ms=2000'],deadline,environment)
    require(row['returncode']==0, 'compatibility load failed, retained actual outcome')
    driver = out/'compat-driver.py'
    with driver.open('x') as stream:
        stream.write(COMPAT_DRIVER)
        stream.flush()
        os.fsync(stream.fileno())
    compat_row, unused = execute('compat-run',[sys.executable,'-B',driver,out],deadline,environment,out/'compat-result.json')
    compatibility = json.loads((out/'compat-result.json').read_text())
    require(compatibility['drained'] and compatibility.get('fd_closed'), 'compatibility controls/fd not drained')
    row, unused = execute('compat-rmmod',[tools['rmmod'],MODULES[0]],deadline,environment)
    require(row['returncode']==0, 'ordinary compatibility unload failed')
    absent(MODULES[0],DEVICES[0])
    record['compat_driver_returncode'] = compat_row['returncode']
    record['compatibility_pass'] = compat_row['returncode']==0 and compat_ok(compatibility)
    save('result.json',record)
    require(record['compatibility_pass'], 'compatibility failed, ordinary drain/unload recorded')
    between = idle()
    record['between_fixtures'] = between
    save('result.json',record)
    require(between['identity']['boot']==current['boot'] and between['identity']['release']==RELEASE and
            not between['identity']['taint'] & ~TAINT_MODULE_BITS, 'kernel changed or unexpected taint after compatibility')
    recovery(config['recovery'],config['host_floor'])
    require(available('/')>=config['root_floor'] and available(WORK)>=config['output_floor'], 'MM headroom')
    row, unused = execute('provider-insmod',[tools['insmod'],pin(config['binaries']['provider'])],deadline,environment)
    require(row['returncode']==0, 'provider load failed, retained actual outcome')
    client_row, output = execute('mmap-client',[pin(config['binaries']['client']),'--threads','4','--iterations','64',
                         '--deadline-ms','60000','--control-device','/dev/kd_mmap_api',
                         '--native-capacity','64','--quiescent-mm'],deadline,environment)
    lines = [line for line in output.read_text().splitlines() if line.strip()]
    require(lines, 'no actual client outcome')
    mm = json.loads(lines[-1])
    save('mmap-result.json',mm)
    # Retired/clear state, not a subprocess exit or zero counter, authorizes
    # normal provider unload. Failed syscall verdicts remain failures afterward.
    selected = mm['selected_gate']
    final = selected['final']
    require(selected['requested'] and not selected['cleanup_required'] and final['state']==2 and
            final['cleanup_required']==0 and final['pool_idle']==1 and not final['gate_locked'] and
            not final['gate_contended'], 'provider is not actually retired, retain selection/module')
    row, unused = execute('provider-rmmod',[tools['rmmod'],MODULES[1]],deadline,environment)
    require(row['returncode']==0, 'ordinary provider unload failed')
    absent(MODULES[1],DEVICES[1])
    record['client_returncode'] = client_row['returncode']
    require(client_row['returncode']==0, 'client failed after recorded ordinary retirement/unload')
    mmap_ok(mm)
    for row in files.values(): pin(row)
    for row in config['source_files'].values(): pin(row)
    for key in ('compatibility','provider','client'): pin(config['binaries'][key])
    record['identity_after'] = idle()
    after = record['identity_after']['identity']
    require(after['boot']==current['boot'] and after['release']==RELEASE and not after['taint'] & ~TAINT_MODULE_BITS,
            'unexpected final running identity/taint')
    final_notes, final_build_id = running_notes()
    require(final_build_id==build_id, 'final running Build ID changed')
    record['running_build_id_after']=final_build_id
    with (out/'running-notes-after.bin').open('xb') as stream:
        stream.write(final_notes)
        stream.flush()
        os.fsync(stream.fileno())
    for row in config['tools'].values(): pin_tool(row)
    row, unused = execute('dmesg-after',[tools['dmesg']],deadline,environment)
    require(row['returncode']==0, 'final kernel log capture failed')
    record['status']='NATIVE_API_AND_MM_COMPLETE'
    record['mmap_scope']='Original-task real syscalls and selected native-gate observations only.'
    save('result.json',record)
    print(json.dumps({'status':record['status'],'receipt':str(out/'result.json')},indent=2))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if record is not None:
            record['status']='FAILED_OR_INCOMPLETE'
            record['error']=repr(error)
            record['last_observed_identity']=identity()
            record['modules_at_failure']=Path('/proc/modules').read_text()
            record['devices_at_failure']={name:(Path('/dev')/name).exists() for name in DEVICES}
            save('result.json',record)
            try:
                diagnostic = record['configuration']['tools']['dmesg']['path']
                execute('dmesg-failure',[diagnostic],time.monotonic()+10,
                        dict(os.environ,LC_ALL='C',PYTHONDONTWRITEBYTECODE='1'))
            except Exception as diagnostic_error:
                record['failure_diagnostic_error']=repr(diagnostic_error)
                save('result.json',record)
        raise
