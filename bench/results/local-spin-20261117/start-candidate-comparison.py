from rpc import rpc
from pathlib import Path
import hashlib,json,time
R=Path('/tmp/kdlock-local-spin-20261117');commit='200c4effb5dce0c0baa7283cb061da1ea8defc50';s=(R/'run-local.py').read_text().replace("variant='local-baseline'","variant='local-candidate'").replace("B=R/'repo'; E=R/'evidence-baseline'", "B=R/'candidate-repo'; E=R/'evidence-candidate'").replace('7.0.0-38-kdlocalspin1','7.0.0-38-kdlocalspin2').replace('4669a0855c625a791731224c8fd13b87711a2a8c',commit).replace("kernel_core='20e9db0c'", "kernel_core='"+commit+"'");(R/'run-candidate.py').write_text(s);h=hashlib.sha256(s.encode()).hexdigest()
code='''import pathlib,subprocess,time,json,hashlib,os
R=pathlib.Path('/mnt/kdlock-builds2/main-spin-local-4669a085-20261117');boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert hashlib.sha256((R/'run-candidate.py').read_bytes()).hexdigest()==HASH
check=json.loads((R/'entry-check-result.json').read_text());assert check['status']=='passed' and check['unloaded'] and check['boot_id']==boot
assert not (R/'evidence-candidate').exists()
time.sleep(5);t=time.time()
with (R/'run-candidate.log').open('x') as f:
 p=subprocess.run(['python3','-B',str(R/'run-candidate.py')],stdout=f,stderr=subprocess.STDOUT)
r={'rc':p.returncode,'start':t,'finish':time.time(),'boot_id':boot};(R/'run-candidate-result.json').write_text(json.dumps(r))
f=os.open('/dev/ttyS0',os.O_WRONLY|os.O_NOCTTY);os.write(f,('\nKDLOCAL_COMPARE_DONE '+json.dumps(r)+'\n').encode());os.close(f)
raise SystemExit(p.returncode)
'''.replace('HASH',repr(h))
r=rpc({'id':'local-spin-candidate-comparison','action':'start','argv':['python3','-B','-c',code]});print(json.dumps(r));(R/'candidate-comparison-start.json').write_text(json.dumps({'receipt':r,'host_time':time.time(),'runner_sha256':h},indent=2))
