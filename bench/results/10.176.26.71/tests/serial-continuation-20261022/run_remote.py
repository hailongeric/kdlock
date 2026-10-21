#!/usr/bin/env python3
"""Run one guest command, then immediately capture its original host endpoint."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT=Path(__file__).resolve().parents[5]
CAPTURE=ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--remote-command',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--receipt',required=True,help='exact guest result path to fetch after the immediate capture')
    p.add_argument('--admission',type=Path,help='fresh local host capture bound to this candidate session')
    a=p.parse_args();a.output.mkdir()
    capture=CAPTURE.read_bytes()
    assert hashlib.sha256(capture).hexdigest()=='b0ad0d1854a0f0d60487fa9afea4d044aacf7b9fa86ec3c700d66a150cd4be1b'
    record=dict(passed=False,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                remote_command=a.remote_command,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        if a.admission:
            host=json.loads(a.admission.read_text())
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
            assert 0<=age<=300
            record.update(admission_sha256=hashlib.sha256(a.admission.read_bytes()).hexdigest(),
                          admission_age_seconds=age,admission_path=str(a.admission))
        with (a.output/'guest-console.log').open('wb') as log:
            child=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222',
                                    'root@10.176.26.71',a.remote_command],stdout=log,stderr=subprocess.STDOUT)
            record['ssh_pid']=child.pid
            # A timeout preserves the running SSH/guest process. It is never a
            # cancellation, drain receipt or permission to start another run.
            code=child.wait(timeout=900)
        exited=time.monotonic_ns()
        capture_started=time.monotonic_ns()
        with (a.output/'host-endpoint.json').open('wb') as output, (a.output/'host-capture.stderr').open('wb') as errors:
            observer=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
                'eric@10.176.26.71','sudo -n python3 -'],stdin=subprocess.PIPE,stdout=output,stderr=errors)
            observer.communicate(capture,timeout=30)
        record.update(guest_returncode=code,host_returncode=observer.returncode,
            guest_exit_observed_monotonic_ns=exited,host_capture_started_monotonic_ns=capture_started,
            host_capture_finished_monotonic_ns=time.monotonic_ns(),
            immediate=capture_started-exited<1_000_000_000,
            host_sha256=hashlib.sha256((a.output/'host-endpoint.json').read_bytes()).hexdigest(),
            passed=code==0 and observer.returncode==0)
        with (a.output/'guest-result.json').open('wb') as output:
            fetch=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222',
                'root@10.176.26.71','cat -- '+shlex.quote(a.receipt)],stdout=output)
            fetch.wait(timeout=30)
        record.update(guest_result_path=a.receipt,result_fetch_returncode=fetch.returncode,
            guest_result_sha256=hashlib.sha256((a.output/'guest-result.json').read_bytes()).hexdigest())
        record['passed']=record['passed'] and fetch.returncode==0
    except BaseException as error:
        record.update(error=repr(error),drain_unconfirmed=True)
        raise
    finally:
        (a.output/'controller.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    print(json.dumps(record))
    return 0 if record['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
