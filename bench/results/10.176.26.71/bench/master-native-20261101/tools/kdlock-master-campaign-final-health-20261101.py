from pathlib import Path
import json,shlex,subprocess
out=Path('/tmp/kdlock-master-campaign-final-health-20261101');out.mkdir(exist_ok=False)
code='''from pathlib import Path
import json,os,runpy,shutil,sys
root=Path('/root/host_fs/kdlock');sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
print(json.dumps(dict(idle=True,release=os.uname().release,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),source_bound=root.is_mount(),free_bytes={p:shutil.disk_usage(p).free for p in ['/','/mnt/kdlock-builds','/mnt/kdlock-builds2']})))
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh','taskset -c 63 python3 -'])],input=code.encode(),capture_output=True,timeout=60)
(out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr.decode();d=json.loads(r.stdout);(out/'result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d))
