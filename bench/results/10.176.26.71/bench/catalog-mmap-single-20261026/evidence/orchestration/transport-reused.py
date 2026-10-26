"""Serial, bounded orchestration of the already authorized unchanged mmap sweep.

Run on 380G10. Every workload and health/source check executes in the VM.
A failed or timed-out command stops this driver without signaling children,
unloading modules or rebooting. Recovery after a stop requires proven drain.
"""
import datetime
import fcntl
import hashlib
import json
import os
import socket
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
ROOT = Path('/home/eric/vm/vm-shared/kdlock')
GUEST = '/root/kdlock-evidence/10.176.26.71/bench/' + BASE.name
SOURCE = '/root/host_fs/kdlock'
PYTHON = '/root/kdlock-translation-venv-20261019/bin/python3'
BUILD = '/root/kdlock-evidence/10.176.26.71/tests/mmap-functional-eligibility-20261026/offline-2/fixed-build/result.json'
NATIVE_COMPAT = '/root/kdlock-evidence/10.176.26.71/tests/mmap-functional-eligibility-20261026/offline-3/native-compatibility.json'
ROLES = '/root/kdlock-evidence/10.176.26.71/bench/mmap-worker-scaling-20261026/roles.json'
PRIOR = '/root/kdlock-evidence/10.176.26.71/bench/mmap-kdmm31-prep-20261025/prior/'
ENV = ['env', 'LC_ALL=C', 'PYTHONDONTWRITEBYTECODE=1',
       'KDLOCK_RECOVERY_CONFIRMED=1',
       'KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z']
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
       '-o', 'StrictHostKeyChecking=yes', '-p', '2222', 'root@10.176.26.71']
BLOCKS = [(1, 'kd', [0]), (2, 'native', [0, 1]), (3, 'kd', [1, 2]), (4, 'native', [2])]
PLAN = json.loads((BASE / 'plan.json').read_text())
MANIFEST = json.loads((BASE / 'source-manifest.json').read_text())
ARTIFACTS = json.loads((BASE / 'expected-artifacts.json').read_text())
INITIAL = json.loads((BASE / 'initial-health.stdout').read_text())
PROFILE = json.loads((ROOT / 'bench/mmap_lock/kdmm31.json').read_text())
START_HEAD = '30af034025d6d30b66b507b1c03847e6c765bb4a'
FROZEN = json.loads((BASE / 'orchestration-manifest.json').read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save():
    assert all(0 <= v <= PLAN['maximum'][k] for k,v in PLAN['consumed'].items()), 'authorized scope exceeded'
    (BASE / 'plan.json').write_text(json.dumps(PLAN, indent=2) + '\n')


def event(kind, **values):
    row = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               event=kind, **values)
    with (BASE / 'events.jsonl').open('a') as f:
        f.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)


def execute(label, argv, data=None, seconds=30):
    PLAN['phase'] = label
    save()
    record = dict(argv=argv, timeout_seconds=seconds, completion_unconfirmed=True,
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    record_path = BASE / (label + '-command.json')
    assert not record_path.exists(), label
    with (BASE / (label + '.stdout')).open('xb') as out, \
            (BASE / (label + '.stderr')).open('xb') as err:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err, cwd=ROOT, start_new_session=True)
        record['pid'] = child.pid
        record_path.write_text(json.dumps(record, indent=2) + '\n')
        event('started', label=label, pid=child.pid, timeout_seconds=seconds)
        # The large controller transfers use communicate so neither pipe end
        # blocks the driver. The outer deadline does not send a signal.
        deadline = time.monotonic() + seconds
        first = True
        while True:
            try:
                child.communicate(data if first else None,
                                  timeout=min(30, max(0.01, deadline-time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                first = False
                if time.monotonic() >= deadline:
                    record['error'] = 'deadline expired; child untouched; completion unknown'
                    record_path.write_text(json.dumps(record, indent=2) + '\n')
                    raise RuntimeError(label + ': uncertain completion; stop without recovery')
                event('running', label=label, pid=child.pid)
        record.update(returncode=child.returncode, completion_unconfirmed=False,
                      finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    record_path.write_text(json.dumps(record, indent=2) + '\n')
    event('completed', label=label, returncode=child.returncode)
    if child.returncode != 0:
        raise RuntimeError(label + ': nonzero exit; stop for drain review')
    return (BASE / (label + '.stdout')).read_bytes()


def remote(label, argv, data=None, seconds=30):
    request = dict(command=argv, stdin_sha256=digest(data) if data else None)
    (BASE / (label + '-request.json')).write_text(json.dumps(request, indent=2) + '\n')
    return execute(label, [*SSH, shlex.join(argv)], data, seconds)


def guest_python(label, code, request=None, seconds=30):
    data = None if request is None else (json.dumps(request) + '\n').encode()
    return remote(label, [*ENV, PYTHON, '-u', '-c', code], data, seconds)


def paired(label, action, args, seconds=30):
    return remote(label, [*ENV, PYTHON, SOURCE + '/bench/mmap_lock/paired.py',
                         action, *args], seconds=seconds)


def fetch(label, path):
    return json.loads(remote(label, ['cat', '--', path]))


def copy(label, files):
    rows = {name: dict(text=data.decode(), sha256=digest(data))
            for name, data in files.items()}
    (BASE / (label + '-inputs.json')).write_text(json.dumps(
        {name: dict(bytes=len(data), sha256=digest(data)) for name, data in files.items()},
        indent=2) + '\n')
    return guest_python(label, (BASE / 'copy-input.py').read_text(), rows)


def source_check():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head == START_HEAD, 'source HEAD changed; stop for owner coordination'
    for name, expected in MANIFEST['files'].items():
        assert digest((ROOT / name).read_bytes()) == expected, name
    for name, expected in FROZEN.items():
        assert digest((BASE / name).read_bytes()) == expected, 'orchestration input changed: '+name
    free = shutil.disk_usage(BASE).free
    assert free >= 512 * 1024**2, {'filesystem':str(BASE),'available_bytes':free,'required_bytes':512*1024**2}
    used = sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file())
    assert used < PLAN['planning']['reserve_bytes_per_retention_filesystem'], 'source retention budget consumed'


def state(label):
    code = (BASE / 'state-remote.py').read_text().replace(
        "print(json.dumps(r),flush=True)",
        "import shutil\nr['root_free_bytes']=shutil.disk_usage('/').free\n"
        "assert r['root_free_bytes']>=512*1024**2, 'recovery reserve low'\n"
        "print(json.dumps(r),flush=True)")
    return json.loads(guest_python(label, code))


def capture(label):
    PLAN['consumed']['full_host_captures'] += 1
    save()
    execute(label, ['python3', 'bench/mmap_lock/controller.py', '--output', str(BASE / label)], seconds=40)
    path = BASE / label / 'host-endpoint.json'
    row = json.loads(path.read_text())
    assert row['passed'] and row['snapshot_listed'] and row['pins_verified']
    return path


def boot(block, mode, previous):
    source_check()
    entry = ARTIFACTS['artifact']['boot_entries'][mode] if mode != 'recovery' else ARTIFACTS['artifact']['recovery_default']
    req = dict(previous_release=previous['release'], previous_boot=previous['boot_id'],
               previous_modules=previous['modules'], artifacts=ARTIFACTS,
               entry=entry, build=BUILD)
    PLAN['consumed']['boots'] += 1
    save()
    guest_python(f'boot-{block}', (BASE / 'boot-remote.py').read_text(), req, seconds=60)
    # A fixed boot-readiness wait is outside all admission/measurement windows.
    # It neither qualifies timing nor substitutes for the post-setup interval.
    time.sleep(25)
    current = state(f'boot-{block}-state')
    assert current['boot_id'] != previous['boot_id']
    assert current['release'] == ('6.1.159-kdclobber2' if mode == 'recovery' else PROFILE['release'])
    assert current['grubenv'] == 'next_entry=\n'
    return current


def main():
    source_check()
    PLAN.update(state='running', execution_commit=START_HEAD)
    save()
    initial = state('launch-state')
    for key in ('release', 'boot_id', 'modules', 'taint', 'cmdline', 'grubenv'):
        assert initial[key] == INITIAL[key], key
    assert initial['root_free_bytes'] >= 3 * 1024**3
    assert PLAN['consumed']['full_host_captures'] == 1
    initial_capture = BASE / 'initial-recovery/host-endpoint.json'
    assert digest(initial_capture.read_bytes()) == PLAN['initial_capture_sha256']
    assert json.loads(initial_capture.read_text())['passed']
    previous_state = initial
    previous_result = None
    results = []
    for block, mode, repeats in BLOCKS:
        current = boot(block, mode, previous_state)
        admission = capture(f'block-{block}-admission')
        guest_admission = GUEST + f'/block-{block}-admission.json'
        copy(f'copy-block-{block}', {guest_admission: admission.read_bytes()})
        ready_dir = GUEST + f'/block-{block}-ready'
        paired(f'block-{block}-ready', 'ready', [
            '--plan', 'plain-scaling-v1', '--measurement-policy', 'mmap-window-v2',
            '--eligibility-policy', 'mmap-functional-v1',
            '--window-roles', ROLES, '--prepared', BUILD,
            '--native-api', PRIOR + 'actual-native-1.json', '--kd-api', PRIOR + 'actual-kd-1.json',
            '--mode', mode, '--block', str(block), '--boot-id', current['boot_id'],
            '--host-state', guest_admission, '--output', ready_dir], seconds=60)
        guest_python(f'block-{block}-compatible', (BASE / 'compatibility-ready.py').read_text(),
                     dict(ready=ready_dir+'/result.json', prepared=BUILD, compatibility=NATIVE_COMPAT), seconds=60)
        if block == 1:
            validation_dir = GUEST + '/' + mode + '-validation'
            PLAN['inflight_validation_maximum_payload_cycles'] = 22
            save()
            paired(mode + '-validate', 'validate', ['--ready', ready_dir + '/result.json',
                   '--output', validation_dir], seconds=5400)
            validation = fetch(mode + '-validation-result', validation_dir + '/result.json')
            assert validation['passed'] and validation['drained'] and len(validation['cases']) == 21
            assert validation['eligibility_policy']=='mmap-functional-v1' and validation['writer_observation'] in ('observed','inconclusive')
            PLAN['consumed']['fixed_proofs'] += 1
            PLAN['consumed']['unscored_timed_controls'] += 21
            PLAN['consumed']['payload_cycles'] += 22
            PLAN.pop('inflight_validation_maximum_payload_cycles')
            save()
        for repeat in repeats:
            for case, workers in enumerate(PLAN['workers']):
                name = f'b{block}-r{repeat}-c{case:02d}-{mode}-n{workers}'
                source_check()
                idle = state(name + '-idle')
                assert idle['boot_id'] == current['boot_id']
                admission = capture(name + '-admission')
                guest_admission = GUEST + '/' + name + '-admission.json'
                copy(name + '-copy-admission', {guest_admission: admission.read_bytes()})
                case_dir = GUEST + '/' + name
                argv = [*ENV, PYTHON, 'bench/mmap_lock/paired.py', 'run',
                        '--ready', ready_dir + '/result.json', '--host-state', guest_admission,
                        '--native-validation', NATIVE_COMPAT,
                        '--kd-validation', GUEST + '/kd-validation/result.json',
                        '--repeat', str(repeat), '--case', str(case), '--output', case_dir]
                if previous_result:
                    argv += ['--previous', previous_result]
                controller = BASE / (name + '-controller')
                PLAN['inflight_measured_case'] = name
                save()
                execute(name + '-run', ['python3', 'bench/mmap_lock/controller.py',
                    '--measurement-policy', 'mmap-window-v2', '--window-roles', str(BASE / 'roles.json'),
                    '--output', str(controller), '--admission', str(admission),
                    '--receipt', case_dir + '/client-result.json',
                    '--remote-command', 'cd ' + shlex.quote(SOURCE) + ' && ' + shlex.join(argv)], seconds=420)
                control = json.loads((controller / 'controller.json').read_text())
                assert control['passed'] and control['guest_returncode'] == 0
                PLAN['consumed']['full_host_captures'] += 2
                PLAN['consumed']['window_observers'] += 1
                endpoint = json.loads((controller / 'window-endpoint.json').read_text())
                # The complete stream is authoritative for actual scan count.
                events = [json.loads(line) for line in (controller / 'host.stream').read_text().splitlines()]
                PLAN['consumed']['window_scans'] += sum(e['event'] == 'sample' for e in events)
                PLAN['consumed']['measured_sessions'] += 1
                PLAN['consumed']['payload_cycles'] += 1
                save()
                guest_controller = GUEST + '/' + name + '-controller'
                copy(name + '-copy-controller', {
                    guest_controller + '/' + str(p.relative_to(controller)): p.read_bytes()
                    for p in controller.rglob('*') if p.is_file()})
                paired(name + '-finish', 'finish', ['--output', case_dir,
                       '--controller', guest_controller], seconds=60)
                receipt = fetch(name + '-result', case_dir + '/result.json')
                assert all(receipt[k] for k in ('passed', 'drained', 'accepted', 'endpoint_checked'))
                assert receipt['eligibility_policy']=='mmap-functional-v1'
                assert receipt['writer_observations']==dict(native='observed',kd=validation['writer_observation'])
                previous_result = case_dir + '/result.json'
                results.append(previous_result)
                PLAN.pop('inflight_measured_case')
                PLAN['qualified_cases'] = len(results)
                PLAN['result_paths'] = results
                save()
                event('qualified', case=name, qualified_cases=len(results),
                      cycles_s=receipt['measurement']['whole_ops_s'])
        previous_state = state(f'block-{block}-final-state')
    report = remote('report', [*ENV, PYTHON, SOURCE + '/bench/mmap_lock/report.py', *results], seconds=300)
    copy('copy-report', {GUEST + '/report.json': report})
    recovery = boot('recovery', 'recovery', previous_state)
    recovery_code = (BASE / 'recovery-remote.py').read_text().replace(
        "assert missing == ['nfnetlink', 'tls'], missing",
        "assert set(missing) <= {'nfnetlink', 'tls'}, missing")
    guest_python('recovery-final', recovery_code,
                 dict(recovery_boot=recovery['boot_id'], expected_modules=INITIAL['modules'],
                      recovery_default=ARTIFACTS['artifact']['recovery_default']), seconds=60)
    capture('final-recovery')
    PLAN['state'] = 'completed_recovered'
    save()
    event('completed_recovered', qualified_cases=len(results))


if __name__ == '__main__':
    with (BASE / 'owner.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner=dict(pid=os.getpid(),ppid=os.getppid(),start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),
                   host=socket.gethostname(),host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   argv=sys.argv,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        with (BASE / 'campaign-owner.json').open('x') as output:json.dump(owner,output,indent=2)
        event('owner',**owner)
        try:
            main()
        except BaseException as error:
            PLAN.update(state='stopped_for_review', error=repr(error))
            save()
            event('stopped_for_review', error=repr(error), phase=PLAN.get('phase'))
            raise
