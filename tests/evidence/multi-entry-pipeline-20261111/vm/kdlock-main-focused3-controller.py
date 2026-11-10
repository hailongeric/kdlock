import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

base = Path(sys.argv[1])
repo = base / 'input'
receipts = base / 'receipts'
receipts.mkdir(mode=0o700)
scratch = base / 'scratch'
scratch.mkdir(mode=0o700)
manifest = json.loads((base / 'source-manifest.json').read_text())

def verify_source():
    actual = {}
    for path in sorted(p for p in repo.rglob('*') if p.is_file()):
        data = path.read_bytes()
        actual[path.relative_to(repo).as_posix()] = {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
    if actual != manifest:
        raise ValueError('frozen source differs from its exact manifest')
    return len(actual)

def identity():
    return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release':os.uname().release, 'taint':Path('/proc/sys/kernel/tainted').read_text().strip(),
            'modules':Path('/proc/modules').read_text(),
            'activity':subprocess.run(['ps','-eo','pid,ppid,stat,args'],capture_output=True,text=True,timeout=10,check=True).stdout}

before = identity()
if any(line.startswith('kd_runtime_fixture ') for line in before['modules'].splitlines()):
    raise ValueError('fixture module remains loaded')
if any(Path('/dev').glob('kd_runtime_fixture*')):
    raise ValueError('fixture devices remain')
if before['release'] != '7.0.0-38-kdrebuild2' or before['taint'] != '12288':
    raise ValueError('unexpected pre-check kernel identity')
verified_before = verify_source()
old = '/mnt/kdlock-builds/kdlock-main-work/run-c6becf81-01a1bc4f'
raw_config = (repo / 'tests/evidence/runtime-pipeline-20261110/pipeline-config.json').read_text()
config = json.loads(raw_config.replace(old, str(base)))
config_path = receipts / 'pipeline-config.json'
config_path.write_text(json.dumps(config,indent=2,sort_keys=True)+'\n')
gs = Path('/mnt/kdlock-builds/kdlock-main-work/gs-9d06c451-01a1bc4f/kdlock-main-gs-9d06c451.gs-config.json')
(receipts / 'gs-config.json').write_bytes(gs.read_bytes())
env = dict(os.environ)
overrides = {'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','LC_ALL':'C','LANG':'C',
             'KDLOCK_PIPELINE_TEST_CONFIG':str(config_path),
             'KDLOCK_KERNEL_GS_TEST_CONFIG':str(receipts/'gs-config.json')}
env.update(overrides)
python = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
patterns = json.loads((base/'test-patterns.json').read_text())
for test in patterns:
    if test['count'] <= 0 or not (repo/'tests'/test['pattern']).is_file():
        raise ValueError('exact focused test file and positive expected count required')
commands = [[python,'-m','unittest','discover','-s','tests','-p',test['pattern'],'-v'] for test in patterns]
record = {'before':before,'source_state':json.loads((base/'source-state.json').read_text()),
          'verified_files_before':verified_before, 'commands':commands,
          'environment_overrides':overrides, 'timeout_seconds_per_command':180,
          'scope':'Basic and directly affected multi-entry, runtime-pipeline and GS checks only; no generated machine code or kernel operations.'}
(receipts/'command.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
results=[]
for i,args in enumerate(commands,1):
    start=time.monotonic()
    item={'argv':args,'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with (receipts/f'check-{i}.log').open('x') as log:
        try:
            run=subprocess.run(args,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=False)
            item['returncode']=run.returncode
        except subprocess.TimeoutExpired:
            item.update(returncode=None,status='timeout; no drain or pass inferred')
    item['elapsed_seconds']=time.monotonic()-start
    data=(receipts/f'check-{i}.log').read_bytes()
    item['log']={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    text=data.decode('utf-8',errors='replace')
    counts=re.findall(r'^Ran ([0-9]+) tests? in ',text,re.MULTILINE)
    item['expected_tests']=patterns[i-1]['count']
    item['reported_tests']=int(counts[0]) if len(counts)==1 else None
    item['check_pass']=(item['returncode']==0 and item['reported_tests']==item['expected_tests']
                        and re.search(r'^OK$',text,re.MULTILINE) is not None
                        and re.search(r'(?:skipped=|\.\.\. skipped )',text) is None)
    results.append(item)
    (receipts/'partial-result.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
    if not item['check_pass']:
        break
record.update(results=results, after=identity(), verified_files_after=verify_source())
record['status']='focused_pass' if len(results)==len(commands) and all(r['check_pass'] for r in results) else 'failed_or_incomplete'
(receipts/'result.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
print(json.dumps(record,indent=2,sort_keys=True))
for i in range(1,len(results)+1):
    print((receipts/f'check-{i}.log').read_text())
raise SystemExit(0 if record['status']=='focused_pass' else 1)
