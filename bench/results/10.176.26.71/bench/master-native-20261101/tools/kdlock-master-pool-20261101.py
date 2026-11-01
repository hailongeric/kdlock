#!/usr/bin/env python3
"""Reactivate the existing main-loop facade for one new measured cohort."""
import argparse
import base64
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import sys
import time

sys.dont_write_bytecode = True
INVENTORY_SHA = 'b9df559437c245e55162948e62384ea745aaa713a7474c6696092a04450af380'
CAPTURE_SHA = 'e9417457c4d33eea2a84f70af0ed2839ce5b07abbd4dd70bb84ea66fdaf9bb74'
EXE_SHA = '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854'
PRIOR_RESTORE_SHA = '9a7485caa6d49322d338765c8079e42d16167d346616ef502e97a6ebb218c978'
PRIOR_CONTROLLER_SHA = 'efc8a6bbed7d20a21e46f8612665af83e899ff3fe58192df361733e3ba1dc0e8'
OBJECT = '/objects/kdlock-main-loop'
MONITOR = '/tmp/qemu-monitor.sock'
PROPS = ('thread-pool-min', 'thread-pool-max', 'aio-max-batch')
TARGET = dict(zip(PROPS, (64, 64, 0)))
RESTORED = dict(zip(PROPS, (0, 64, 0)))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_json(path, obj):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(obj, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def task_key(row):
    return {key: row[key] for key in ('tid', 'start_ticks', 'comm', 'affinity')}


class Action:
    def __init__(self, args):
        self.args = args
        args.output.mkdir(parents=True, exist_ok=False)
        self.result = dict(
            schema=1, kind='kdlock-qemu-main-loop-pool-policy', action=args.action,
            cohort=args.cohort, started_utc=utc(), completed=False,
            controller_sha256=sha(__file__), capture_helper_sha256=CAPTURE_SHA,
            inventory_sha256=INVENTORY_SHA, mutation_attempted=False,
            mutation_confirmed=False, policy_state_unknown=False,
            performance_accepted=False, guest_drain_proved=False,
            idle_confirmed_by_operator=args.idle_confirmed,
            previous_nano_archived_by_operator=args.nano_archived,
            monitor=[], captures={}, observations=[],
            required_before={'values': RESTORED,
                'qualification': 'Completed previous campaign restore plus fresh live QOM '
                'readback of the existing main-loop object.'})
        self.save()

    def save(self):
        atomic_json(self.args.output / 'result.json', self.result)

    def load_inputs(self):
        require(os.geteuid() == 0, 'run as root on the QEMU host')
        require(sorted(os.sched_getaffinity(0)) == [63], 'collector must be pinned to CPU 63')
        require(sha(self.args.inventory) == INVENTORY_SHA, 'saved inventory bytes differ')
        require(sha(self.args.capture_helper) == CAPTURE_SHA, 'maintained capture helper differs')
        self.inventory = json.loads(self.args.inventory.read_text())
        require(self.inventory.get('completed') is True, 'inventory did not complete')
        self.identity = self.inventory['before']
        self.original_tasks = [task_key(row) for row in self.inventory['tasks_before']]
        require(len(self.original_tasks) == 67, 'saved original task count differs')
        require(self.original_tasks == [task_key(row) for row in self.inventory['tasks_after']],
                'saved inventory endpoints differ')
        spec = importlib.util.spec_from_file_location('kd_pool_capture', self.args.capture_helper)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.process_check()
        if self.args.action in ('verify', 'restore'):
            require(self.args.prior_restore is None and self.args.prior_restore_sha256 is None,
                    'historical restore input belongs only to activation')
            require(self.args.policy is not None and self.args.policy_sha256 is not None,
                    'exact successful activation receipt required')
            require(sha(self.args.policy) == self.args.policy_sha256, 'activation receipt differs')
            self.policy = json.loads(self.args.policy.read_text())
            require(self.policy.get('kind') == self.result['kind'] and
                    self.policy.get('action') == 'activate', 'activation receipt required')
            if self.args.action == 'verify':
                require(self.policy.get('completed') is True,
                        'successful activation receipt required for a policy endpoint')
            else:
                require(self.policy.get('mutation_attempted') is True,
                        'restore requires a receipt from an attempted activation')
            require(self.policy['controller_sha256'] == self.result['controller_sha256'] and
                    self.policy['inventory_sha256'] == INVENTORY_SHA and
                    self.policy['capture_helper_sha256'] == CAPTURE_SHA,
                    'activation receipt implementation/input binding differs')
            require(self.policy['cohort'] == self.args.cohort, 'activation receipt cohort differs')
            if self.args.action == 'verify':
                require(self.policy['final_properties'] == TARGET, 'activation receipt settings differ')
            self.result['activation_receipt_sha256'] = self.args.policy_sha256
        else:
            require(self.args.policy is None and self.args.policy_sha256 is None,
                    'activation must not reuse another policy receipt')
            require(self.args.prior_restore is not None and
                    self.args.prior_restore_sha256 == PRIOR_RESTORE_SHA and
                    sha(self.args.prior_restore) == PRIOR_RESTORE_SHA,
                    'exact completed previous campaign restore receipt required')
            prior = json.loads(self.args.prior_restore.read_text())
            require(prior.get('kind') == self.result['kind'] and
                    prior.get('action') == 'restore' and prior.get('completed') is True and
                    prior.get('restored_settings') is True and
                    prior.get('policy_state_unknown') is False and
                    prior.get('confirmed_properties') == RESTORED and
                    prior.get('final_properties') == RESTORED and
                    prior.get('controller_sha256') == PRIOR_CONTROLLER_SHA and
                    prior.get('inventory_sha256') == INVENTORY_SHA and
                    prior.get('capture_helper_sha256') == CAPTURE_SHA,
                    'historical completed restore identity/settings differ')
            (self.args.output / 'prior-restore.json').write_bytes(self.args.prior_restore.read_bytes())
            self.result['prior_restore_sha256'] = PRIOR_RESTORE_SHA
        if self.args.action != 'verify':
            require(self.args.idle_confirmed and self.args.nano_archived,
                    'idle and original nano archive acknowledgements required before mutation')
        self.save()

    def process_check(self):
        proc = Path('/proc') / str(self.identity['pid'])
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
                self.inventory['host_boot_id'], 'host boot differs')
        require(self.helper.start_ticks(proc / 'stat') == self.identity['start_ticks'],
                'QEMU process start differs')
        require((proc / 'cmdline').read_bytes() ==
                base64.b64decode(self.identity['cmdline_b64']), 'QEMU launch arguments differ')
        require(os.readlink(proc / 'exe') == self.identity['exe'] and
                sha(proc / 'exe') == EXE_SHA, 'running executable differs')
        require(sorted(os.sched_getaffinity(self.identity['pid'])) == [63],
                'main-loop affinity differs; this controller does not repin it')

    def capture(self, label):
        self.process_check()
        host = self.helper.capture(self.args.snapshot, Path(MONITOR))
        path = self.args.output / (label + '.host.json')
        atomic_json(path, host)
        self.result['captures'][label] = dict(path=str(path), sha256=sha(path))
        tasks = host['qemu'][0]['tasks']
        originals = {row['tid']: row for row in self.original_tasks}
        current = {row['tid']: row for row in tasks}
        require(all(current.get(tid) == row for tid, row in originals.items()),
                'an original permanent task changed identity or placement')
        extras = [row for row in tasks if row['tid'] not in originals]
        require(all(row['comm'] == 'worker' and row['affinity'] == [63] for row in extras),
                'unexpected additional task or worker affinity')
        require(host['qemu'][0]['pid'] == self.identity['pid'] and
                host['qemu'][0]['start_ticks'] == self.identity['start_ticks'],
                'capture process differs')
        self.result['observations'].append(dict(label=label, tasks=len(tasks), workers=len(extras)))
        self.save()
        return host

    def prompt(self, conn):
        raw = bytearray()
        deadline = time.monotonic() + 8
        while not raw.endswith(b'(qemu) '):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'monitor deadline expired')
            conn.settimeout(remaining)
            block = conn.recv(65536)
            require(bool(block), 'monitor closed before prompt')
            raw.extend(block)
            require(len(raw) <= 2 * 1024 * 1024, 'monitor output exceeded bound')
        return bytes(raw)

    def command(self, conn, command, mutate=False):
        entry = dict(command=command, started_utc=utc(), mutation=mutate, send_started=False)
        self.result['monitor'].append(entry)
        self.save()
        if mutate:
            self.result.update(mutation_attempted=True, policy_state_unknown=True)
        entry['send_started'] = True
        self.save()
        conn.sendall(command.encode('ascii') + b'\n')
        raw = self.prompt(conn)
        entry.update(raw_b64=base64.b64encode(raw).decode(),
                     sha256=hashlib.sha256(raw).hexdigest(), finished_utc=utc())
        # HMP readline echoes/redraws its input before its first CRLF. Preserve
        # those raw bytes, but parse only the subsequent command response.
        require(b'\r\n' in raw, 'HMP echoed-line delimiter missing')
        body = raw.split(b'\r\n', 1)[1][:-len(b'(qemu) ')].decode('utf-8').strip()
        entry['body'] = body
        self.save()
        if mutate:
            require(body == '', 'unexpected mutation response; state must be reviewed')
            self.result['mutation_confirmed'] = True
            self.save()
        return body

    def observe(self, label, expected_object, mutation=None, expected_properties=TARGET):
        self.process_check()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(8)
            conn.connect(MONITOR)
            banner = self.prompt(conn)
            self.result['monitor'].append(dict(label=label, banner_b64=base64.b64encode(banner).decode()))
            listing = self.command(conn, 'qom-list /objects')
            objects = {}
            for line in listing.splitlines():
                match = re.fullmatch(r'([A-Za-z0-9_.-]+) \(([^\r\n]+)\)', line)
                require(match is not None, 'unexpected QOM object listing row')
                require(match[1] not in objects, 'duplicate QOM object listing row')
                objects[match[1]] = match[2]
            expected = {'type': 'string', 'mem0': 'child<memory-backend-ram>',
                        'mem1': 'child<memory-backend-ram>'}
            if expected_object:
                expected['kdlock-main-loop'] = 'child<main-loop>'
            require(objects == expected, 'object inventory differs; no automatic duplicate creation')
            tree = self.command(conn, 'info qom-tree /')
            loops = re.findall(r'^\s*/([^\s]+) \((main-loop|iothread)\)\s*$', tree, re.M)
            require(loops == ([('kdlock-main-loop', 'main-loop')] if expected_object else []),
                    'unexpected main-loop/IOThread in complete QOM tree')
            require(self.command(conn, 'info iothreads') == '', 'unexpected IOThread')
            require(json.loads(self.command(conn, 'qom-get /machine/peripheral/scsi0/virtio-backend iothread')) == '',
                    'SCSI IOThread assignment differs')
            require(json.loads(self.command(conn, 'qom-get /machine/peripheral/scsi0/virtio-backend num_queues')) == 64,
                    'SCSI queue count differs')
            self.command(conn, 'info block')
            properties = None
            if expected_object:
                properties = {p: json.loads(self.command(conn, 'qom-get ' + OBJECT + ' ' + p)) for p in PROPS}
                require(properties == expected_properties, 'current main-loop policy differs')
            if mutation is not None:
                self.command(conn, mutation, mutate=True)
                properties = {p: json.loads(self.command(conn, 'qom-get ' + OBJECT + ' ' + p)) for p in PROPS}
                expected_properties = RESTORED if self.args.action == 'restore' else TARGET
                require(properties == expected_properties, 'mutation readback differs')
                self.result.update(policy_state_unknown=False, confirmed_properties=properties)
            self.result['observations'].append(dict(label=label, objects=objects, properties=properties))
            self.save()
            return properties

    def execute(self):
        self.load_inputs()
        before = self.capture('before')
        if self.args.action == 'activate':
            original = {row['tid']: row for row in self.original_tasks}
            current = {row['tid']: row for row in before['qemu'][0]['tasks']}
            require(all(current.get(tid) == row for tid, row in original.items()),
                    'original QEMU task identity or placement changed')
            extra = [row for tid, row in current.items() if tid not in original]
            require(len(extra) <= 64 and all(row['comm'] == 'worker' and
                    row['affinity'] == [63] for row in extra),
                    'unexpected task outside original cohort and pool')
            self.result['retained_pool_tasks_before'] = extra
            self.observe('activate', True, 'qom-set ' + OBJECT + ' thread-pool-min 64',
                         expected_properties=RESTORED)
            time.sleep(30)
            first = self.capture('settled-a')
            require(len(first['qemu'][0]['tasks']) == 131, 'expected 64 workers after fixed settlement')
            self.observe('settled-a-properties', True)
            time.sleep(12)
            second = self.capture('settled-b')
            require(first['qemu'][0]['tasks'] == second['qemu'][0]['tasks'],
                    'complete settled task map differs')
            require(self.helper.memory_bindings(first['qemu'][0]) == self.helper.memory_bindings(second['qemu'][0]),
                    'settled memory bindings differ')
            self.result['final_properties'] = self.observe('settled-b-properties', True)
            self.result.update(reference_tasks=first['qemu'][0]['tasks'],
                               candidate_reference=self.result['captures']['settled-a'],
                               stable_worker_cohort_observed=True)
        elif self.args.action == 'verify':
            require(before['qemu'][0]['tasks'] == self.policy['reference_tasks'],
                    'task map differs from successful new policy reference')
            self.result['final_properties'] = self.observe('verify', True)
            after = self.capture('after')
            require(after['qemu'][0]['tasks'] == before['qemu'][0]['tasks'],
                    'task map changed during property observation')
        else:
            self.observe('restore', True, 'qom-set ' + OBJECT + ' thread-pool-min 0')
            time.sleep(30)
            after = self.capture('restored')
            # Restored workers may still be alive due to real I/O; property
            # restoration must not claim the old task map has returned.
            properties = self.observe('restored-properties', True, expected_properties=RESTORED)
            self.result.update(final_properties=properties, restored_settings=True,
                               original_task_map_restored=after['qemu'][0]['tasks'] == self.original_tasks,
                               original_qom_absence_restored=False)
        self.process_check()
        self.result['completed'] = True
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('activate', 'verify', 'restore'))
    parser.add_argument('--capture-helper', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--cohort', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--policy-sha256')
    parser.add_argument('--prior-restore', type=Path)
    parser.add_argument('--prior-restore-sha256')
    parser.add_argument('--idle-confirmed', action='store_true')
    parser.add_argument('--nano-archived', action='store_true')
    args = parser.parse_args()
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', args.cohort), 'invalid cohort name')
    action = Action(args)
    def timeout(signum, frame):
        raise TimeoutError('180-second total action deadline expired')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        action.execute()
    except BaseException as error:
        action.result.update(completed=False, error=repr(error), automatic_rollback=False)
    finally:
        signal.alarm(0)
        action.result['finished_utc'] = utc()
        action.save()
    print(json.dumps(dict(completed=action.result['completed'],
                          result=str(args.output / 'result.json'),
                          sha256=sha(args.output / 'result.json'),
                          mutation_attempted=action.result['mutation_attempted'],
                          policy_state_unknown=action.result['policy_state_unknown']), sort_keys=True))
    return 0 if action.result['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
