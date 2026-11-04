from pathlib import Path
import json,shlex,subprocess
code="from pathlib import Path;print(Path('/proc/sys/kernel/random/boot_id').read_text().strip())"
r=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh','python3 -c '+shlex.quote(code)])],capture_output=True,text=True,timeout=45)
assert r.returncode==0,r.stderr
boot=r.stdout.strip();assert boot=='ab2bb986-b894-480b-8a5d-a88b9ca97368';print('plain KD boot',boot,flush=True)
transfer=json.loads(Path('/tmp/kdlock-reached-mm-indexed-code-private-20261103/transfer.stdout').read_text())
collection=json.loads(Path('/tmp/kdlock-mm-jit-proof-artifacts/collection.json').read_text())
provider='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reached-mm-indexed-code-units-20261103/cold/build/provider/kernel_module/kdlock_km.ko'
code="from pathlib import Path;import hashlib;print(hashlib.sha256(Path("+repr(provider)+").read_bytes()).hexdigest())"
r=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh','python3 -c '+shlex.quote(code)])],capture_output=True,text=True,timeout=45)
assert r.returncode==0,r.stderr
collection.update(provider=provider,provider_sha256=r.stdout.strip())

for model in ('threads','processes'):
 c=json.loads(Path('/tmp/kdlock-mm-perf-fetch-'+model+'-n02-config.json').read_text())
 c.update(root=transfer['root'],source_commit=transfer['source_commit'],state_sha256=transfer['source_state_sha256'],manifest_sha256=transfer['source_manifest_sha256'],boot_id=boot,provider=collection['provider'],provider_sha256=collection['provider_sha256'])
 c['delegation_proof']={k:collection['files'][model+'/delegated-proof.json'][k] for k in ('path','sha256')}
 c['metadata']='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/mm-jit-indexed-20261104/'+model+'-n02/inputs'
 c['output']='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/mm-jit-indexed-20261104/'+model+'-n02/run'
 c['local_output']='/tmp/kdlock-mm-jit-indexed-'+model+'-n02'
 path=Path('/tmp/kdlock-mm-jit-indexed-'+model+'-n02-config.json');path.write_text(json.dumps(c,indent=2)+'\n')
 r=subprocess.run(['python3','/tmp/kdlock-mm-perf-launch.py',str(path)],timeout=600)
 assert r.returncode==0,(model,r.returncode)
