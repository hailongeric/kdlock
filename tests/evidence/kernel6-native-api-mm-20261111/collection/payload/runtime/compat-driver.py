
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
