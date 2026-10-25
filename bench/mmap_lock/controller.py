#!/usr/bin/env python3
"""Source-host controller: one guest command and one immediate host capture.

Requires separate live-operation approval. Never boots, signals, retries or
waits for quiet. A timeout records uncertain completion, never implied drain.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(out, record):
    (out / 'controller.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


def helper_payload():
    # Stream these exact reviewed bytes; do not execute an unchecked remote copy.
    observer = (HERE / 'host_capture_control.py').read_text()
    helper = (HERE / 'host_state.py').read_text()
    return ("import sys,types\nm=types.ModuleType('host_capture_control')\n" +
            'exec(compile(' + repr(observer) + ", 'host_capture_control.py', 'exec'),m.__dict__)\n" +
            "sys.modules[m.__name__]=m\nexec(compile(" + repr(helper) +
            ", 'host_state.py', 'exec'), {'__name__':'__main__'})\n").encode()


def capture(out, record, payload):
    profile = json.loads((HERE / 'kdmm31.json').read_text())['host']
    command = shlex.join(['sudo', '-n', '/usr/bin/python3', '-', '--pid', str(profile['pid']),
        '--start-ticks', str(profile['start_ticks']), '--cmdline-sha256', profile['command_sha256']])
    record['host_capture_started_monotonic_ns'] = time.monotonic_ns()
    with (out / 'host-endpoint.json').open('wb') as stdout, (out / 'host-capture.stderr').open('wb') as stderr:
        child = subprocess.Popen([*SSH, 'eric@10.176.26.71', command],
                                 stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
        record.update(host_ssh_pid=child.pid, host_completion_unconfirmed=True)
        save(out, record)
        child.communicate(payload, timeout=30)
    record.update(host_returncode=child.returncode, host_completion_unconfirmed=False,
        host_capture_finished_monotonic_ns=time.monotonic_ns(), host_sha256=sha(out / 'host-endpoint.json'))
    # A nonzero/partial helper still has a durable raw receipt. Do not turn it
    # into a second attempt or make a later capture its replacement endpoint.


def execute(out, command, receipt, admission):
    payload = helper_payload()
    record = dict(passed=False, accepted=False, drain_unconfirmed=True,
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        driver_sha256=sha(Path(__file__)), helper_sha256=sha(HERE / 'host_state.py'),
        observer_sha256=sha(HERE / 'host_capture_control.py'),
        streamed_payload_sha256=hashlib.sha256(payload).hexdigest(), remote_command=command,
        guest_result_path=receipt, phase='admission')
    save(out, record)
    try:
        if command is not None:
            host = json.loads(admission.read_text())
            age = (datetime.datetime.now(datetime.timezone.utc) -
                   datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
            if not host['passed'] or not 0 <= age <= 300:
                raise ValueError('fresh successful admission capture required')
            record.update(admission_sha256=sha(admission), admission_path=str(admission),
                          admission_age_seconds=age, phase='guest')
            with (out / 'guest-console.log').open('wb') as log:
                child = subprocess.Popen([*SSH, '-p', '2222', 'root@10.176.26.71', command],
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                record.update(guest_ssh_pid=child.pid, guest_completion_unconfirmed=True)
                save(out, record)
                code = child.wait(timeout=240)
            # The next external action is the capture, with no guest validation,
            # unload, hash scan, result fetch or quiet observation in between.
            record.update(guest_returncode=code, guest_completion_unconfirmed=False,
                          guest_exit_observed_monotonic_ns=time.monotonic_ns())
        record['phase'] = 'host'
        capture(out, record, payload)
        host = json.loads((out / 'host-endpoint.json').read_text())
        if command is not None:
            record['phase'] = 'fetch'
            with (out / 'guest-result.json').open('wb') as output:
                fetch = subprocess.Popen([*SSH, '-p', '2222', 'root@10.176.26.71',
                    'cat -- ' + shlex.quote(receipt)], stdout=output, start_new_session=True)
                record.update(fetch_ssh_pid=fetch.pid, fetch_completion_unconfirmed=True)
                save(out, record)
                fetch.wait(timeout=30)
            record.update(result_fetch_returncode=fetch.returncode, fetch_completion_unconfirmed=False,
                          guest_result_sha256=sha(out / 'guest-result.json'))
            record['immediate'] = 0 <= (record['host_capture_started_monotonic_ns'] -
                record['guest_exit_observed_monotonic_ns']) < 1_000_000_000
            complete = record['guest_returncode'] == record['result_fetch_returncode'] == 0 and record['immediate']
        else:
            complete = True
        record['passed'] = complete and record['host_returncode'] == 0 and host['passed']
        record['phase'] = 'complete' if record['passed'] else 'failed'
    except BaseException as error:
        record.update(passed=False, error=repr(error), failed_phase=record['phase'],
                      failure_monotonic_ns=time.monotonic_ns())
    finally:
        # Success describes capture transport only. Guest drain and timing
        # qualification are established independently by paired.py finish.
        save(out, record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--remote-command')
    p.add_argument('--receipt')
    p.add_argument('--admission', type=Path)
    p.add_argument('--measurement-policy', choices=('mmap-transport-v1', 'mmap-window-v2'),
                   default='mmap-transport-v1')
    p.add_argument('--window-roles', type=Path)
    a = p.parse_args()
    if bool(a.remote_command) != bool(a.receipt) or bool(a.remote_command) != bool(a.admission):
        p.error('measurement requires command, receipt and admission together')
    if a.measurement_policy == 'mmap-window-v2' and (not a.remote_command or not a.window_roles):
        p.error('prepared window requires command, receipt, admission and reviewed role manifest')
    if a.measurement_policy == 'mmap-transport-v1' and a.window_roles:
        p.error('legacy transport does not accept a window role manifest')
    a.output.mkdir(parents=True)
    def interrupted(signum, frame):
        raise InterruptedError('controller received signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if a.measurement_policy == 'mmap-window-v2':
        import sys
        import window_controller
        result = window_controller.execute(sys.modules[__name__], a.output, a.remote_command,
            a.receipt, a.admission, a.window_roles)
    else:
        result = execute(a.output, a.remote_command, a.receipt, a.admission)
    print(json.dumps(result), flush=True)
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
