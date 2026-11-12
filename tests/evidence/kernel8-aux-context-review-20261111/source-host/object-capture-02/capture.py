#!/usr/bin/env python3
"""VM-only inspection of the exact existing objects in one reviewed plan.

Only the fresh capture directory receives writes. No input is executed or
modified, and no command outside the pinned objdump plan is dispatched.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import selectors
import stat
import subprocess
import sys
import time

PLAN_SHA = 'af42fd1972f7809deec96ecb763b8fd898fb72e55f5023d4650996d1ece3e505'
BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
KERNEL = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
record = None
output = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def facts(path, limit):
    path = Path(path)
    before = path.lstat()
    need(path.resolve(strict=True) == path and stat.S_ISREG(before.st_mode)
         and before.st_size <= limit, 'nonregular, noncanonical or oversized input: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    value = hashlib.sha256()
    try:
        need(identity(os.fstat(descriptor)) == identity(before), 'input changed on open')
        for block in iter(lambda: os.read(descriptor, 1048576), b''):
            value.update(block)
        need(identity(os.fstat(descriptor)) == identity(before)
             and identity(path.lstat()) == identity(before), 'input changed during hash')
    finally:
        os.close(descriptor)
    return {'path': str(path), 'bytes': before.st_size, 'sha256': value.hexdigest(),
            'identity': identity(before)}


def read_json(path, expected, limit=4 * 1024**2):
    row = facts(path, limit)
    need(row['sha256'] == expected, 'receipt identity differs: ' + str(path))
    return json.loads(Path(path).read_bytes())


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def usage():
    return sum(path.stat().st_size for path in output.iterdir() if path.is_file())


def write(name, data, limit):
    need('/' not in name and name not in ('.', '..'), 'flat output name required')
    need(usage() + len(data) <= limit, 'total capture byte limit reached before write')
    with (output / name).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(output)


def document(name, value, limit):
    write(name, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode(), limit)


def update(limit):
    raw = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode()
    temporary = '.result-new'
    write(temporary, raw, limit)
    os.replace(output / temporary, output / 'result.json')
    sync_directory(output)


def checked_helper(path, expected):
    need(facts(path, 1024**2)['sha256'] == expected, 'reviewed metadata helper differs')
    return runpy.run_path(str(path))


def main():
    global output, record
    need(os.geteuid() == 0 and len(sys.argv) == 2, 'designated VM root and exact encoded plan required')
    raw = base64.b64decode(sys.argv[1], validate=True)
    need(sha(raw) == PLAN_SHA and len(raw) <= 65536, 'exact reviewed finite plan required')
    plan = json.loads(raw)
    started = time.monotonic()
    deadline = started + plan['overall_seconds']
    need(plan['overall_seconds'] == 180 and plan['output_total_bytes'] == 32*1024**2
         and len(plan['objects']) == 36 and len(plan['commands']) == 144
         and len(plan['sources']) == 2
         and len({row['label'] for row in plan['commands']}) == 144,
         'closed object/command/source bounds differ')
    limit = plan['output_total_bytes']
    ns = checked_helper(BASE/'transport/build.py',
                        '56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb')
    native = checked_helper(BASE/'native-api-input-01/controller.py',
                            '2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074')
    control = checked_helper(BASE/'mm-provider-ioctl-input-0798c1ab-01/controller.py',
                             '6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136')
    recipe = read_json(BASE/'mm-provider-ioctl-input-0798c1ab-01/recipe.json',
                       'ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7')
    before_idle = control['idle'](native, recipe)
    build_id = native['running_notes']()[1]
    need(build_id == recipe['build_id'], 'actual running Build ID differs')
    built = read_json(KERNEL/'receipts/full-01/result.json',
                      '024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    focused = read_json(Path(built['focused_receipt']), built['focused_sha256'])
    linked = read_json(KERNEL/'receipts/full-01/final-identity.json', built['final_identity_sha256'])
    pins = {name: row['sha256'] for name, row in linked['files'].items()}

    def preserved():
        rows = {'linked16': ns['pins'](KERNEL/'build', pins),
                'source': ns['source_pins'](focused, KERNEL/'source'),
                'protected': ns['protected'](focused), 'boot': ns['boot_files']()}
        need(len(rows['linked16']) == 16 and len(focused['package_after']) == 78
             and rows['source'] == built['source_after'] and rows['protected'] == built['protected_after'],
             'kernel/source/protected pins differ')
        return rows

    before_pins = preserved()
    need(facts(KERNEL/'source/kernel/kdlock/Kbuild', 65536)['sha256'] == plan['kbuild_sha256'],
         'frozen built-in object membership differs')
    provider = read_json(BASE/'mm-provider-ioctl-build-0798c1ab-01/receipts/result.json',
                         plan['provider_build_receipt_sha256'])
    need(provider['status'] == 'MM_PROVIDER_MODULE_BUILD_COMPLETE', 'completed provider build required')
    evidence = {
        'managed-killable-receipts-04/result.json': 'd7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488',
        'managed-killable-live-03/result.json': '56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a',
        'recovery-killable-final-01/result.json': '40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0',
    }
    for name, expected in evidence.items():
        read_json(BASE/name, expected)
    objects = {row['path']: facts(row['path'], plan['object_each_bytes']) for row in plan['objects']}
    sources = {name: facts(name, plan['source_each_bytes']) for name in plan['sources']}
    need(len(objects) == 36 and sum(row['bytes'] for row in objects.values()) <= plan['object_input_total_bytes'],
         'exact object input extent differs')
    tools = {}
    aliases = {'cpp': '/usr/bin/cpp', 'as': '/usr/bin/as', 'ld': '/usr/bin/ld',
               'objcopy': '/usr/bin/objcopy', 'objdump': '/usr/bin/objdump',
               'insmod': '/usr/sbin/insmod', 'rmmod': '/usr/sbin/rmmod', 'dmesg': '/usr/bin/dmesg'}
    for name, alias in aliases.items():
        resolved = Path(alias).resolve(strict=True)
        tools[name] = {'alias': alias, 'resolved': str(resolved), **facts(resolved, 32*1024**2)}
    prior = read_json(BASE/'build-01/receipts/result.json',
                     '223392b879bd1aaad6ffc3e40f322706be8bd94039abd0a50c16afe238ffa37c')
    client = prior['client_reuse']
    read_json(Path(client['compile_receipt']), client['compile_receipt_sha256'])
    client_inputs = {name: facts(row['path'], 1048576) for name, row in client['source_files'].items()}
    need(len(client_inputs) == 3 and all(
        all(client_inputs[name][key] == row[key] for key in ('path', 'bytes', 'sha256'))
        for name, row in client['source_files'].items()), 'original client input bytes differ')
    client_binary = facts(prior['client']['path'], 1048576)
    need(all(client_binary[key] == prior['client'][key] for key in ('path', 'bytes', 'sha256')),
         'exact reused client binary differs')
    tool = plan['tool']
    need({key: tools['objdump'][key] for key in ('alias', 'resolved', 'bytes', 'sha256')} == tool,
         'actual pinned objdump differs')
    output = Path(plan['output_leaf'])
    need(output.parent.resolve(strict=True) == BASE and not os.path.lexists(output), 'fresh canonical capture leaf required')
    output.mkdir(mode=0o700)
    write('plan.json', raw, limit)
    record = {'status': 'CAPTURING', 'plan_sha256': PLAN_SHA, 'started_unix': time.time(),
              'identity_before': before_idle, 'running_build_id': build_id, 'tools_before': tools,
              'objects_before': objects, 'sources_before': sources, 'pins_before': before_pins,
              'package78': focused['package_after'], 'commands': [], 'debug_frame': {},
              'client_binary': client_binary, 'client_inputs': client_inputs,
              'client_compile_receipt': client['compile_receipt'],
              'client_compile_receipt_sha256': client['compile_receipt_sha256'],
              'scope': plan['scope']}
    update(limit)
    for number, (name, row) in enumerate(sources.items()):
        data = Path(name).read_bytes()
        need(len(data) == row['bytes'] and sha(data) == row['sha256'], 'native source changed during capture')
        label = f'source-{number:02d}.bin'
        write(label, data, limit)
        row['capture'] = label
    for index, command in enumerate(plan['commands']):
        need(time.monotonic() < deadline, 'overall capture deadline expired before dispatch')
        argv = command['argv']
        need(argv[0] == tool['alias'] and argv[-1] in objects and len(argv) <= 6
             and command['per_command_seconds'] == 15, 'exact planned objdump input required')
        label = command['label']
        need('/' not in label and index == len(record['commands']), 'ordered flat command labels required')
        stdout, stderr = output/(label+'.stdout'), output/(label+'.stderr')
        seconds = min(command['per_command_seconds'], deadline-time.monotonic())
        need(seconds > 0 and usage() + command['stdout_bytes'] + command['stderr_bytes']
             + 1048576 <= limit, 'capture capacity or deadline exhausted before dispatch')

        row = {'label': label, 'argv': argv, 'started_unix': time.time(),
               'stdout': stdout.name, 'stderr': stderr.name}
        record['commands'].append(row)
        update(limit)
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     start_new_session=True,
                                     env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'})
            row['pid'] = child.pid
            update(limit)
            stop = min(deadline, time.monotonic() + seconds)
            observed = {'stdout': 0, 'stderr': 0}
            overrun = False
            selector = selectors.DefaultSelector()
            selector.register(child.stdout, selectors.EVENT_READ, ('stdout', out, command['stdout_bytes']))
            selector.register(child.stderr, selectors.EVENT_READ, ('stderr', err, command['stderr_bytes']))
            try:
                while selector.get_map() or child.poll() is None:
                    remaining = stop - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(argv, seconds)
                    for key, _ in selector.select(min(0.05, remaining)):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        stream_name, target, stream_limit = key.data
                        allowance = max(0, stream_limit - observed[stream_name])
                        target.write(data[:allowance])
                        observed[stream_name] += len(data)
                        if len(data) > allowance:
                            overrun = True
                code = child.wait(timeout=max(0.001, stop-time.monotonic()))
            except subprocess.TimeoutExpired:
                row.update(status='OBSERVER_EXPIRED_CHILD_RETAINED', elapsed_seconds=time.time()-row['started_unix'])
                record['status'] = 'INCOMPLETE_CHILD_RETAINED'
                update(limit)
                raise
            finally:
                selector.close()
                child.stdout.close()
                child.stderr.close()
            out.flush(); os.fsync(out.fileno())
            err.flush(); os.fsync(err.fileno())
        row.update(returncode=code, elapsed_seconds=time.time()-row['started_unix'],
                   stdout_bytes=stdout.stat().st_size, stderr_bytes=stderr.stat().st_size,
                   stdout_sha256=sha(stdout.read_bytes()), stderr_sha256=sha(stderr.read_bytes()))
        row.update(observed_stdout_bytes=observed['stdout'], observed_stderr_bytes=observed['stderr'],
                   output_capacity_exceeded=overrun)
        update(limit)
        need(code == 0 and not overrun and row['stdout_bytes'] <= command['stdout_bytes']
             and row['stderr_bytes'] <= command['stderr_bytes'] and usage() <= limit,
             'objdump command or finite output bound failed: ' + label)
        if label.endswith('-sections'):
            record['debug_frame'][argv[-1]] = {'present': any('.debug_frame' in line.split()
                                                           for line in stdout.read_text().splitlines()),
                                             'section_output': stdout.name,
                                             'absence_is_not_a_stack_bound': True}
    after_objects = {name: facts(name, plan['object_each_bytes']) for name in objects}
    after_sources = {name: facts(name, plan['source_each_bytes']) for name in sources}
    need(after_objects == objects and after_sources == {name: {k: v for k, v in row.items() if k != 'capture'}
                                                       for name, row in sources.items()}, 'object/source identity changed')
    after_pins = preserved()
    after_idle = control['idle'](native, recipe)
    need(after_pins == before_pins and after_idle == before_idle and native['running_notes']()[1] == build_id,
         'kernel/source/boot/idle identities changed')
    for name, expected in evidence.items():
        read_json(BASE/name, expected)
    for name, row in tools.items():
        need(facts(row['resolved'], 32*1024**2) == {k: row[k] for k in ('path', 'bytes', 'sha256', 'identity')},
             'tool changed during capture: ' + name)
    need(facts(client_binary['path'], 1048576) == client_binary
         and all(facts(row['path'], 1048576) == row for row in client_inputs.values()),
         'client binary or original source inputs changed during capture')
    need(time.monotonic() <= deadline, 'overall capture deadline expired during final proof')
    record.update(status='READ_ONLY_OBJECT_CAPTURE_COMPLETE', identity_after=after_idle,
                  objects_after=after_objects, sources_after=after_sources, pins_after=after_pins,
                  command_count=len(record['commands']), elapsed_seconds=time.monotonic()-started,
                  stack_bound_established=False)
    update(limit)
    print(json.dumps({'status': record['status'], 'receipt': str(output/'result.json'),
                      'commands': len(record['commands']), 'bytes': usage()}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record['error'] = repr(error)
            if record['status'] != 'INCOMPLETE_CHILD_RETAINED':
                record['status'] = 'FAILED_OR_INCOMPLETE'
            try:
                update(32*1024**2)
            except BaseException:
                pass
        raise
