import datetime,json,os,re,socket
from pathlib import Path
out={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
qemus=[]
for proc in Path('/proc').glob('[0-9]*'):
    try:
        args=(proc/'cmdline').read_bytes().split(b'\0')
        if not args or Path(os.fsdecode(args[0])).name!='qemu-system-x86_64': continue
        tasks=[]
        for task in (proc/'task').iterdir():
            tasks.append({'tid':int(task.name),'comm':(task/'comm').read_text().strip(),'affinity':sorted(os.sched_getaffinity(int(task.name)))})
        qemus.append({'pid':int(proc.name),'args':[os.fsdecode(a) for a in args if a],'tasks':tasks})
    except (FileNotFoundError,ProcessLookupError): pass
out['qemu']=qemus
for qemu in qemus:
    qemu['numa_maps'] = Path('/proc', str(qemu['pid']), 'numa_maps').read_text()
out['cpufreq']={p.name:{f:p.joinpath(f).read_text().strip() for f in ['scaling_driver','scaling_governor','scaling_min_freq','scaling_max_freq','affected_cpus'] if p.joinpath(f).exists()} for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')}
out['numa']={p.name:(p/'cpulist').read_text().strip() for p in Path('/sys/devices/system/node').glob('node[0-9]*')}
out['serial_pv_boot_lines']=[]
p=Path('/tmp/qemu-serial.log')
if p.exists():
    with p.open(errors='replace') as f:
        for line in f:
            if 'PV spinlocks disabled' in line: out['serial_pv_boot_lines'].append(line.strip())
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(8);s.connect('/tmp/qemu-monitor.sock')
def read_prompt():
    b=b''
    while not b.endswith(b'(qemu) '): b+=s.recv(65536)
    return b.decode(errors='replace')
out['monitor_banner']=read_prompt();s.sendall(b'info snapshots\n');out['snapshots']=read_prompt();s.close()
tag='before-mutex-kdonly-20261017T140354Z';out['recovery_snapshot']=tag;out['snapshot_listed']=tag in out['snapshots']
assert len(qemus)==1 and out['snapshot_listed']
vcpu={int(m[1]):t['affinity'] for t in qemus[0]['tasks'] if (m:=re.fullmatch(r'CPU (\d+)/KVM',t['comm']))}
assert vcpu=={i:[i] for i in range(64)}, vcpu
assert all(t['affinity']==[63] for t in qemus[0]['tasks'] if not t['comm'].startswith('CPU '))
out['pins_verified']=True
print(json.dumps(out,indent=2))
