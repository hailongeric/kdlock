#!/usr/bin/env python3
"""Source-host receipt capture for the explicitly approved exact25 deletion."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/tmp/kdlock-scope234-deletion-20261111-01')
HELPER = Path('/tmp/kdlock-scope234-delete-20261111-approved-01.py')
ROOT.mkdir(mode=0o700)
payload = HELPER.read_bytes()
argv = ['ssh', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4',
        'root@10.176.26.71', 'nice -n 19 ionice -c 3 python3 -']
command = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               argv=argv, helper=str(HELPER), helper_sha256=hashlib.sha256(payload).hexdigest(),
               authorization='User explicitly confirmed permanent deletion of the listed exact25 historical scope2/3/4 objects after disclosure of loss and remaining dependencies; parent delegated execution. No other paths authorized.')
with (ROOT/'command.json').open('x') as stream:
    json.dump(command,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
start = time.monotonic()
with (ROOT/'raw.jsonl').open('xb') as output, (ROOT/'stderr.log').open('xb') as errors:
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=output, stderr=errors)
    child.stdin.write(payload); child.stdin.close()
    print(json.dumps(dict(receipts=str(ROOT), pid=child.pid, command=command)),flush=True)
    while child.poll() is None:
        time.sleep(1)
    output.flush(); errors.flush(); os.fsync(output.fileno()); os.fsync(errors.fileno())
result = dict(returncode=child.returncode, elapsed_seconds=time.monotonic()-start,
              receipt_root=str(ROOT), helper_sha256=command['helper_sha256'])
for name in ['command.json','raw.jsonl','stderr.log']:
    b=(ROOT/name).read_bytes(); result[name]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
with (ROOT/'controller-result.json').open('x') as stream:
    json.dump(result,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
print(json.dumps(result,sort_keys=True),flush=True)
raise SystemExit(child.returncode)
