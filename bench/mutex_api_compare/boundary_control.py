#!/usr/bin/env python3
"""Source-host serial feasibility diagnostic; never sends a timing permit.

Retain one guest connection across setup, one warmup and a bounded hold. Host
captures use the existing observer connection. Every failed gate is evidence;
neither eventual quiescence nor observer rates establish timing equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
from qemu_controls import ROOT, CAPTURE, TRACE, SSH, Stream, stamp
from boundary_protocol import host_hash, validate_reply
import boundary_trigger
import run as scheduler


def original_environment(out):
    archive = ROOT/'bench/results/10.176.26.71/raw/bench/mutex-public-20261020-r2/matrix.tar.gz'
    result = {}
    with tarfile.open(archive) as stream:
        for name, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
            member = stream.getmember('mutex-public-20261020-r2/matrix/'+name)
            assert member.isfile() and member.size < 2*1024*1024
            data = stream.extractfile(member).read()
            assert hashlib.sha256(data).hexdigest() == digest
            (out/('original-'+name)).write_bytes(data)
            result[name] = json.loads(data)
    return result


def host_gate(original, host):
    try:
        assert host['pins_verified'] and host['snapshot_listed'], 'actual pins/snapshot absent'
        tasks = lambda h: sorted(h['qemu'][0]['tasks'], key=lambda r: r['tid'])
        assert len(host['qemu']) == 1 and len(tasks(host)) == 67 and tasks(host) == tasks(original['host-state.json']), 'strict original QEMU thread identities or placement differ'
        env, topology = original['environment.json'], original['topology.json']
        # Guest fields are independently rechecked in the held guest before
        # reporting the combined gate. This screening compares every host field.
        scheduler.same_environment(original['host-state.json'], host, env, env, topology, topology)
        return dict(passed=True, error=None)
    except (AssertionError, ValueError, KeyError) as error:
        return dict(passed=False, error=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--capture-policy', choices=('fixed', 'sample-trigger'), default='fixed')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = dict(accepted=False, score_eligible=False, timing_sent=False, complete=False,
        streams=[], requests=[], phases=[], captures=[], started=stamp(), capture_policy=args.capture_policy,
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), sources={})
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True), 'commit diagnostic source before running'
    for src in (Path(__file__), TRACE, CAPTURE, ROOT/'bench/mutex_api_compare/qemu_controls.py',
                ROOT/'bench/mutex_api_compare/boundary_protocol.py', ROOT/'bench/mutex_api_compare/unlock_run.py',
                ROOT/'bench/mutex_api_compare/boundary_trigger.py',
                ROOT/'bench/mutex_api_compare/run.py', ROOT/'bench/mutex_api_compare/recovery_replay.py'):
        data = src.read_bytes()
        (out/src.name).write_bytes(data)
        receipt['sources'][str(src)] = hashlib.sha256(data).hexdigest()
    original = original_environment(out)

    def save():
        (out/'supervisor.json').write_text(json.dumps(receipt, indent=2)+'\n')

    save()
    command = shlex.join(['sudo', '-n', 'python3', '-u', '-c', TRACE.read_text(),
        '--pid', '257489', '--cmdline-sha256',
        '08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917',
        '--duration', '600', '--interval', '5', '--full-capture'])
    observer = Stream(out, 'observer', SSH+['eric@10.176.26.71', command], receipt, save)
    guest = None
    try:
        observer.until('ready')
        anchor_sample = observer.until('sample')
        anchor = boundary_trigger.reference(original['host-state.json']['qemu'][0]['tasks'], anchor_sample['remote'])
        receipt['trigger_anchor'] = anchor
        save()
        mark = lambda label: observer.request('marker', label, 'marker')

        def capture(label):
            reply = observer.request('capture', label, 'capture', limit=25)
            assert time.monotonic_ns()-reply['sent']['mono_ns'] <= 25*1000000000, 'full capture reply exceeded absolute request budget'
            data = reply['ack']['remote']
            receipt['captures'].append(dict(label=label, error=data['error'],
                host_gate=host_gate(original, data['host']) if data['host'] else None))
            save()
            assert data['error'] is None, data['error']
            (out/(label+'.json')).write_text(json.dumps(data['host'], indent=2)+'\n')
            return reply, receipt['captures'][-1]['host_gate']

        preflight_began = time.monotonic()
        for index, offset in enumerate((0, 15, 30, 60, 120)):
            time.sleep(max(0, preflight_began+offset-time.monotonic()))
            initial, gate = capture('preflight-'+str(index))
            print(json.dumps(dict(preflight=index, offset_s=offset,
                task_count=len(initial['ack']['remote']['host']['qemu'][0]['tasks']), host_gate=gate)), flush=True)
            if gate['passed']:
                break
        assert gate['passed'], 'initial full host gate refused: '+str(gate['error'])
        host = initial['ack']['remote']['host']
        launch = '''import json,subprocess,sys
from pathlib import Path
root=Path('/root/host_fs/kdlock')
base=Path(BASE)
base.mkdir(exist_ok=True)
name=NAME
host_data=json.loads(sys.stdin.readline())
host=base/(name+'-host.json')
with host.open('x') as stream: json.dump(host_data,stream)
runner=base/(name+'-runner.py')
with runner.open('xb') as stream: stream.write((root/'bench/mutex_api_compare/unlock_run.py').read_bytes())
old=base.parent/'pipecap-unlock-20261021'
args=[sys.executable,str(runner),'--mode','timing','--phase-single-outer','--setup-boundary-probe','--inputs',str(old/'inputs-1/inputs.json'),'--inputs-sha256','daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae','--output',str(base/name),'--host-state',str(host),'--unit-checks',str(old/'checks-1/result.json'),'--task-check',str(old/'task-2/result.json'),'--elf-checks',str(old/'elf-checks-2.json'),'--correctness',str(old/'correctness-1/result.json'),'--source-commit',COMMIT]
sys.exit(subprocess.call(args))
'''.replace('NAME', repr(out.name)).replace('COMMIT', repr(receipt['source_commit'])).replace('BASE', repr(
            '/root/kdlock-evidence/10.176.26.71/bench/'+
            ('mutex-boundary-trigger-20261021' if args.capture_policy == 'sample-trigger' else 'mutex-boundary-20261021')))
        (out/'guest-launch.py').write_text(launch)
        command = shlex.join(['env', 'PYTHONDONTWRITEBYTECODE=1', 'LC_ALL=C',
            'PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'KDLOCK_RECOVERY_CONFIRMED=1', 'KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z',
            '/root/kdlock-translation-venv-20261019/bin/python3', '-u', '-c', launch])
        guest = Stream(out, 'workload', SSH+['-p', '2222', 'root@10.176.26.71', command], receipt, save, mixed_output=True)
        guest.proc.stdin.write(json.dumps(host)+'\n')
        guest.proc.stdin.flush()
        while True:
            event = guest.items.get(timeout=180)
            if event is None:
                break
            assert 'reader_error' not in event, event
            row = event['remote']
            if row['event'] == 'phase':
                ack = mark(f"phase{row['sequence']}-{row['label']}-{row['edge']}")
                sent = stamp()
                guest.proc.stdin.write(json.dumps(dict(phase_ack=row['sequence']))+'\n')
                guest.proc.stdin.flush()
                receipt['phases'].append(dict(guest_event=event, host_ack=ack, guest_ack_sent=sent))
                save()
            elif row['event'] == 'boundary':
                assert 'boundary' not in receipt and row['boundary'] == 1
                receipt['boundary'] = dict(request=event, observations=[], sample_decisions=[])
                start = time.monotonic()
                marker = mark('held-boundary-'+row['boundary_token'])['ack']['remote']['mono_ns']
                observations = receipt['boundary']['observations']
                def fixed_points():
                    for offset in (0, 15, 30, 60, 120):
                        time.sleep(max(0, start+offset-time.monotonic()))
                        yield dict(kind='fixed', offset_s=offset)
                points = (boundary_trigger.triggers(observer, anchor, marker, int(start*1000000000),
                          receipt['boundary']['sample_decisions'], save)
                          if args.capture_policy == 'sample-trigger' else fixed_points())
                for index, trigger in enumerate(points):
                    offset = time.monotonic()-start
                    label = f"boundary-{row['boundary_token']}-{index}"
                    reply, gate = capture(label)
                    remote = reply['ack']['remote']
                    freshness = boundary_trigger.capture_age(trigger, remote) if trigger['kind'] == 'sample' else None
                    observations.append(dict(capture=label, offset_s=offset, trigger=trigger, trigger_freshness=freshness,
                        capture_began_ns=remote['capture_began']['mono_ns'],
                        capture_finished_ns=remote['capture_finished']['mono_ns'],
                        boundary_marker_ns=marker, request_sent_ns=reply['sent']['mono_ns'],
                        ack_received_ns=reply['ack']['received']['mono_ns'],
                        host_sha256=host_hash(remote['host']), host_gate=gate))
                    save()
                    print(json.dumps(dict(capture=label, task_count=len(remote['host']['qemu'][0]['tasks']), host_gate=gate)), flush=True)
                    if gate['passed'] and (freshness is None or freshness['qualified']):
                        break
                answer = dict(boundary_ack=1, boundary_token=row['boundary_token'],
                    host_state=remote['host'], observations=observations)
                validate_reply(answer, row['boundary_token'])
                receipt['boundary']['reply_sent'] = stamp()
                receipt['boundary']['host_gate_passed'] = gate['passed']
                save()
                guest.proc.stdin.write(json.dumps(answer)+'\n')
                guest.proc.stdin.flush()
        guest.finish()
        capture('endpoint')
        receipt.update(complete=True, finished=stamp())
    except BaseException as error:
        receipt['error'] = repr(error)
        # Do not signal an in-flight guest or infer drain. Its own bounded
        # coordinator timeout retains uncertain prepared resources.
        receipt['guest_state_uncertain'] = guest is not None and guest.proc.poll() is None
        raise
    finally:
        save()
        if observer.proc.poll() is None:
            observer.request('marker', 'stop', 'marker')
        observer.finish()


if __name__ == '__main__':
    main()
