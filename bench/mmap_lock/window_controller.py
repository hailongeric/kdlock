#!/usr/bin/env python3
"""Source-host prepared-window transport, called explicitly by controller.py."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import subprocess
import time
import uuid

import window

HERE = Path(__file__).resolve().parent
MAX_HOST = 16 * 1024**2


def observer_payload():
    pieces = ['import sys,types']
    for name in ('window', 'host_capture_control', 'host_state', 'window_host'):
        code = (HERE / (name + '.py')).read_bytes()
        pieces += [f'm=types.ModuleType({name!r})', f'm.__file__={str(HERE / (name + ".py"))!r}',
                   f'm._STREAM_SHA256={hashlib.sha256(code).hexdigest()!r}',
                   f'sys.modules[{name!r}]=m', f'exec(compile({code.decode()!r},{name!r},"exec"),m.__dict__)']
    pieces.append('raise SystemExit(m.main())')
    return '\n'.join(pieces)


def inventory(host):
    tasks = host['qemu'][0]['tasks']
    core = [t for t in tasks if re.fullmatch(r'CPU (\d+)/KVM', t['comm']) or
            t['tid'] in (257489, 257490, 257560)]
    window.require(len(core) == 67, 'original 64 vCPU and three service identities required')
    return core


def guest_command(command, nonce):
    # The public interface accepts a shell program, including cd/&&/quotes.
    # Give that whole program the nonce instead of asking env to execute cd.
    window.Protocol(nonce)
    return shlex.join(['env', 'KDLOCK_WINDOW_NONCE=' + nonce, 'sh', '-c', command])


def execute(api, out, command, receipt_path, admission, roles_path):
    """One attempt. No signals, retries, new guest transport or disk I/O in hold."""
    nonce = uuid.uuid4().hex
    protocol = window.Protocol(nonce)
    record = dict(**window.binding(), nonce=nonce, events=protocol.events, passed=False,
                  accepted=False, drain_unconfirmed=True, guest_result_path=receipt_path,
                  driver_sha256=api.sha(Path(api.__file__)),
                  window_controller_sha256=api.sha(Path(__file__)),
                  helper_sha256=api.sha(HERE / 'host_state.py'),
                  observer_sha256=api.sha(HERE / 'host_capture_control.py'),
                  window_observer_sha256=api.sha(HERE / 'window_host.py'),
                  admission_sha256=api.sha(admission), admission_path=str(admission),
                  roles_sha256=api.sha(roles_path), phase='setup')
    roles = json.loads(roles_path.read_text())
    # Explicit evidence files are reviewed inputs, not a role inferred from S/comm.
    admission_version = window.role_manifest(roles)
    record.update(window.admission_fields(roles))
    for path, digest in roles['evidence'].items():
        window.require(api.sha(Path(path)) == digest, 'role/configuration evidence changed')
        if admission_version == window.WORKER_ADMISSION:
            target = out / 'role-evidence' / digest
            target.parent.mkdir(exist_ok=True)
            data = Path(path).read_bytes()
            window.require(hashlib.sha256(data).hexdigest() == digest, 'role evidence changed during copy')
            target.write_bytes(data)
    window.require(all(r['evidence'] in roles['evidence'].values() for r in roles['roles']),
                   'role lacks bound independent evidence')
    (out / 'window-roles.json').write_bytes(roles_path.read_bytes())
    guest = observer = None
    api.save(out, record)
    buffers = {name: bytearray() for name in ('guest', 'guest_error', 'host', 'host_error')}
    consumed = {name: 0 for name in buffers}
    streams = {}
    try:
        host = json.loads(admission.read_text())
        age = (api.datetime.datetime.now(api.datetime.timezone.utc) -
               api.datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
        window.require(host['passed'] and 0 <= age <= 300, 'fresh full environment capture required')
        core = inventory(host)
        record['core'] = core
        profile = json.loads((HERE / 'kdmm31.json').read_text())['host']
        if admission_version == window.WORKER_ADMISSION:
            expected = {k: profile[k] for k in ('pid', 'start_ticks', 'command_sha256')}
            window.require(host['capture']['identity_before'] == host['capture']['identity_after'] ==
                           host['final_identity'] == expected, 'admission QEMU membership identity differs')
            window.resolve_roles(host['qemu'][0]['tasks'], core, roles['roles'],
                                 admission=admission_version, qemu_identity=expected)
        remote = guest_command(command, nonce)
        guest = subprocess.Popen([*api.SSH, '-p', '2222', 'root@10.176.26.71', remote],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
        record.update(guest_ssh_pid=guest.pid, guest_completion_unconfirmed=True,
                      remote_command=remote, phase='prepare')
        deadline = time.monotonic() + 240
        with selectors.DefaultSelector() as selector:
            def register(child, prefix):
                selector.register(child.stdout, selectors.EVENT_READ, prefix)
                selector.register(child.stderr, selectors.EVENT_READ, prefix + '_error')
            register(guest, 'guest')
            while True:
                window.require(time.monotonic() < deadline, 'window controller deadline; completion uncertain')
                for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                    name = key.data
                    block = os.read(key.fd, 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    consumed[name] += len(block)
                    window.require(consumed[name] <= (MAX_HOST if name == 'host' else window.MAX_ERROR),
                                   'transport output exceeds bound: ' + name)
                    with (out / (name + '.stream')).open('ab') as log:
                        log.write(block)
                    buffers[name].extend(block)
                    if name.endswith('_error'):
                        continue
                    while b'\n' in buffers[name]:
                        raw, _, rest = buffers[name].partition(b'\n')
                        buffers[name] = bytearray(rest)
                        event = json.loads(raw)
                        window.require(event.get('nonce') == nonce and
                                       all(event.get(k) == v for k, v in window.binding().items()),
                                       'transport source/policy/nonce differs')
                        kind = event['event']
                        if name == 'guest':
                            protocol.receive(event, kind)
                            if kind == 'prepared':
                                payload = observer_payload()
                                record['streamed_window_payload_sha256'] = hashlib.sha256(payload.encode()).hexdigest()
                                observer = subprocess.Popen([*api.SSH, 'eric@10.176.26.71',
                                    shlex.join(['sudo', '-n', '/usr/bin/python3', '-u', '-c', payload])],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True)
                                record.update(host_window_pid=observer.pid, host_window_completion_unconfirmed=True,
                                              phase='guard')
                                register(observer, 'host')
                                request = dict(nonce=nonce, profile=profile, core=core, roles=roles['roles'],
                                               **window.admission_fields(roles))
                                window.write_all(observer.stdin.fileno(), (json.dumps(request) + '\n').encode(), time.monotonic()+10)
                                deadline = time.monotonic() + 30
                            elif kind == 'started':
                                record['phase'] = 'measurement'
                            elif kind == 'finished':
                                window.require(re.fullmatch('[0-9a-f]{16}', event.get('completion_token', '')),
                                               'invalid completion token')
                                record['completion_token'] = event['completion_token']
                                record['finished_observed_monotonic_ns'] = time.monotonic_ns()
                                window.write_all(observer.stdin.fileno(),
                                    (json.dumps(dict(event='endpoint', nonce=nonce)) + '\n').encode(), time.monotonic()+1)
                                record['endpoint_requested_monotonic_ns'] = time.monotonic_ns()
                                record['phase'] = 'endpoint'
                                deadline = time.monotonic() + 30
                            else:
                                raise ValueError('unexpected guest event')
                        elif kind == 'guard':
                            window.require(len(protocol.events) == 1, 'duplicate/out-of-order guard')
                            protocol.add('go')
                            window.write_all(guest.stdin.fileno(), window.frame('go', nonce), time.monotonic()+1)
                            record['go_sent_monotonic_ns'] = time.monotonic_ns()
                            deadline = time.monotonic() + 30
                        elif kind == 'endpoint':
                            endpoint = event['receipt']
                            window.require(endpoint['nonce'] == nonce and endpoint['passed'], 'endpoint failed')
                            (out / 'window-endpoint.json').write_text(json.dumps(endpoint, sort_keys=True) + '\n')
                            record['window_endpoint_sha256'] = api.sha(out / 'window-endpoint.json')
                            protocol.add('endpoint', endpoint_sha256=record['window_endpoint_sha256'])
                            record['endpoint_observed_monotonic_ns'] = time.monotonic_ns()
                            protocol.add('export', endpoint_sha256=record['window_endpoint_sha256'],
                                         completion_token=record['completion_token'])
                            window.write_all(guest.stdin.fileno(), window.frame('export', nonce,
                                endpoint_sha256=record['window_endpoint_sha256'],
                                completion_token=record['completion_token']), time.monotonic()+1)
                            record['export_sent_monotonic_ns'] = time.monotonic_ns()
                            record['phase'] = 'publication'
                            deadline = time.monotonic() + 30
                        elif kind != 'sample':
                            raise ValueError('host window failed: ' + repr(event))
                names = {key.data for key in selector.get_map().values()}
                code = guest.poll()
                if code is not None and not names.intersection(('guest', 'guest_error')):
                    record.update(guest_returncode=code, guest_completion_unconfirmed=False,
                                  guest_exit_observed_monotonic_ns=time.monotonic_ns())
                    protocol.add('exited')
                    window.require(code == 0 and not buffers['guest'] and not buffers['guest_error'],
                                   'guest failed or partial control')
                    # Keep the later transport endpoint distinct. The next external
                    # action after observing SSH exit is the original full capture.
                    api.capture(out, record, api.helper_payload())
                    break
        window.require(observer is not None and observer.wait(timeout=30) == 0 and
                       not buffers['host'] and not buffers['host_error'], 'host observer incomplete')
        record.update(host_window_completion_unconfirmed=False, host_window_returncode=0)
        with (out / 'guest-result.json').open('wb') as output:
            fetch = subprocess.Popen([*api.SSH, '-p', '2222', 'root@10.176.26.71',
                'cat -- ' + shlex.quote(receipt_path)], stdout=output, start_new_session=True)
            record.update(fetch_ssh_pid=fetch.pid, fetch_completion_unconfirmed=True)
            code = fetch.wait(timeout=30)
        record.update(result_fetch_returncode=code, fetch_completion_unconfirmed=False,
                      guest_result_sha256=api.sha(out / 'guest-result.json'))
        record['passed'] = code == record['host_returncode'] == 0
        record['phase'] = 'complete' if record['passed'] else 'failed'
    except BaseException as error:
        record.update(error=repr(error), failed_phase=record['phase'], passed=False)
    finally:
        # EOF cancels pre-start holds. It never implies client exit or safe unload.
        for child in (guest, observer):
            if child is not None and child.stdin is not None:
                child.stdin.close()
        record['transport_bytes'] = consumed
        record['stream_sha256'] = {name: api.sha(out / (name + '.stream')) for name in buffers
                                  if (out / (name + '.stream')).exists()}
        api.save(out, record)
    return record
