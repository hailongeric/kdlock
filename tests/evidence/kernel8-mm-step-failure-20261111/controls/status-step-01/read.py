from pathlib import Path
import json,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
result={'observed_unix':time.time(),'files':{}}
for name in ['mm-mmap-step-receipts-0798c1ab-01/result.json','mm-mmap-step-receipts-0798c1ab-01/runner.log','mm-mmap-step-live-0798c1ab-01/result.json','mm-mmap-step-live-0798c1ab-01/client.stdout','mm-mmap-step-live-0798c1ab-01/client.stderr']:
 p=base/name
 if not p.exists(): result['files'][name]={'exists':False};continue
 s=p.stat();row={'exists':True,'bytes':s.st_size,'mtime':s.st_mtime}
 if name.endswith('result.json') and s.st_size<32*1024*1024:
  r=json.loads(p.read_text());row['fields']={k:r[k] for k in ['status','error','phase','child_pid','client_pid','child_returncode','controller_pid','elapsed_seconds','client_returncode'] if k in r}
 elif name.endswith('.log'):
  with p.open('rb') as f:f.seek(max(0,s.st_size-4096));row['tail']=f.read(4096).decode(errors='replace')
 result['files'][name]=row
p=base/'mm-mmap-step-live-0798c1ab-01';result['output_members']=sorted(x.name for x in p.iterdir()) if p.exists() else []
print(json.dumps(result,sort_keys=True))
