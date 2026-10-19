#!/usr/bin/env python3
"""Finalize already-completed VM evidence; no live workload or source changes."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

root=Path('/root/host_fs/kdlock')
base=Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-opt-20261019')
assert Path.cwd()==root and os.uname().release=='6.1.159-kdclobber2'
sys.dont_write_bytecode=True
def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
local=runpy.run_path(str(root/'tests/kernel/mutex/local/run.py'))
local['idle']()
archive=runpy.run_path(str(root/'bench/archive_run.py'))
archive['idle'](base,local['idle'])
comparison=read(base/'comparison.json')
profiles=read(base/'profile-analysis.json')
assert comparison['complete'] and comparison['valid_sessions']==69 and comparison['scored_plain_sessions']==63
assert profiles['complete'] and len(profiles['profiles'])==6
before,after=(read(base/name) for name in ('host-before.json','host-after.json'))
assert before['snapshot_listed'] and after['snapshot_listed'] and before['recovery_snapshot']==after['recovery_snapshot']
assert before['cpufreq']==after['cpufreq'] and before['numa']==after['numa']
bq,aq=before['qemu'][0],after['qemu'][0]
assert bq['pid']==aq['pid'] and bq['args']==aq['args']
bt={t['tid']:t for t in bq['tasks']};at={t['tid']:t for t in aq['tasks']}
assert {k:v for k,v in bt.items() if v['comm'].startswith('CPU ')}=={k:v for k,v in at.items() if v['comm'].startswith('CPU ')}
assert all(bt[k]==at[k] for k in bt.keys()&at.keys())
assert all(t['affinity']==[63] for t in list(bt.values())+list(at.values()) if not t['comm'].startswith('CPU '))
first=read(base/'checks/commands.json')
retry=read(base/'checks-retry/result.json')
assert [r['exit_code'] for r in first]==[0,0,0,2] and retry['passed'] and retry['source_unchanged']
for name in ('local','rwsem','instruction-exit'):
    result=read(base/'checks-retry'/name/'result.json')
    assert result['passed'] and result['drained'],name
faults=[];logs={}
for path in base.rglob('kernel.log'):
    messages=path.read_text(errors='replace')
    matches=[line for line in messages.splitlines() if local['rt'].FAULT.search(line)]
    if matches:faults.append({'path':str(path.relative_to(base)),'matches':matches})
    logs[str(path.relative_to(base))]=digest(path)
assert not faults
validation=dict(passed=True,source_revision='fcbacbe04d470b7ccfaa2a0db48dccfd3a85685e',
    unit_basic=2,unit_affected_drivers=12,unit_final_passed=14,full_suite=False,
    first_attempt=dict(passed=13,failed=1,reason='Frozen test bundle omitted tests/kernel/execution/exec_relay_exit_probe.c',
        source='checks/source',log='checks/unit.log'),
    retry=dict(passed=1,failed=0,production_or_test_changes=False,source='checks-retry/source',log='checks-retry/unit.log'),
    provider=dict(passed=True,flags='W=1 UBSAN_SANITIZE=n',log='checks/provider.log',warning_free=False),
    daemon=dict(passed=True,flags='-O2 -Wall -Wextra -Werror',log='checks/daemon.log'),
    dependencies=dict(passed=True,log='checks/dependencies.log'),
    live={name:read(base/'checks-retry'/name/'result.json') for name in ('local','rwsem','instruction-exit')},
    note='Synthetic timing has JIT entry witnesses; API timing and instruction-exit checks measure matching completions. No full-suite claim.')
(base/'validation.json').write_text(json.dumps(validation,indent=2,sort_keys=True)+'\n')
postprocess=dict(summary=dict(exit_code=0,script_sha256=digest(base/'summarize.py'),log='summary-command.log'),
    profiles=dict(exit_code=0,script_sha256=digest(base/'profile-analysis.py'),log='profile-analysis-command.log'),
    plot=dict(exit_code=0,script_sha256=digest(base/'plot.py'),log='plot-command.log'),
    pipe_admission=dict(input_collector_sha256=digest(root/'bench/results/10.176.26.71/bench/mutex32-api-screen-20261019/collect_admission.py'),
        result='pipe-admission.json',errors=sum(len(r['errors']) for r in read(base/'pipe-admission.json'))))
(base/'postprocess.json').write_text(json.dumps(postprocess,indent=2,sort_keys=True)+'\n')
local['idle']()
health=dict(idle=True,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    kernel_release=os.uname().release,captured_unix=time.time(),
    per_session_kernel_faults=faults,kernel_logs=logs,valid_timing_sessions=63,valid_profiles=6,
    source_unchanged_checks=True,host_pins_frequency_policy_snapshot_unchanged=True,
    added_host_service_threads=[at[k] for k in at.keys()-bt.keys()],
    removed_host_service_threads=[bt[k] for k in bt.keys()-at.keys()],
    snapshot=after['recovery_snapshot'],comparison_sha256=digest(base/'comparison.json'),
    validation_sha256=digest(base/'validation.json'),profile_analysis_sha256=digest(base/'profile-analysis.json'))
assert health['boot_id']=='b65f0205-c8f9-4385-8b13-039cbce243a6'
(base/'health.json').write_text(json.dumps(health,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(idle=True,kernel_logs=len(logs),faults=len(faults),timing=63,profiles=6,checks=True)))
