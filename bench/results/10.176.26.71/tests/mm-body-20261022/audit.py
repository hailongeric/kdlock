#!/usr/bin/env python3
"""Read-only archive audit on 380G10; never extract or execute archived code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[5]
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-body-20261022'
ARCHIVES = RAW / 'seal-1/guest-archives-1'
checks = 0


def check(value, message):
    global checks
    checks += 1
    if not value:
        raise AssertionError(message)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    check(os.uname().nodename == '380G10', 'source-host audit only')
    manifest = json.loads((ARCHIVES / 'archives.json').read_text())
    inventory = json.loads((ARCHIVES / 'input-inventory.json').read_text())
    check(manifest['completed'] and manifest['guest_idle'], 'completed idle archive')
    check(sha((ARCHIVES / 'input-inventory.json').read_bytes()) == manifest['input_inventory_sha256'], 'inventory binding')
    hashes, data, seen = {}, {}, set()
    files = directories = links = compressed = payload = 0
    for group in manifest['groups']:
        path = ARCHIVES / group['file']
        value = path.read_bytes()
        check(len(value) == group['bytes'] and sha(value) == group['sha256'], 'archive bytes/hash')
        compressed += len(value)
        with tarfile.open(path, 'r:gz') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                check(not name.is_absolute() and '..' not in name.parts and name.parts[0] == manifest['archive_prefix'], 'safe member')
                rel = '/'.join(name.parts[1:])
                check(rel in inventory and rel not in seen, 'unique inventoried member')
                seen.add(rel)
                row = inventory[rel]
                check(member.uid == row['uid'] and member.gid == row['gid'] and member.mode == stat.S_IMODE(row['mode']), 'member metadata')
                if member.isdir():
                    directories += 1; check(stat.S_ISDIR(row['mode']), 'directory type')
                elif member.issym():
                    links += 1; check(stat.S_ISLNK(row['mode']) and member.linkname == row['link'], 'symbolic link')
                else:
                    check(member.isfile() or member.islnk(), 'regular/internal hardlink member')
                    check(stat.S_ISREG(row['mode']), 'regular inventory type')
                    value = archive.extractfile(member).read()
                    check(len(value) == row['bytes'], 'regular bytes')
                    files += 1; payload += len(value); hashes[rel] = sha(value)
                    if rel.endswith(('.json', '.jsonl', '.log', '.py', '.c', '.h', '.inc')):
                        data[rel] = value
    check(seen == set(inventory), 'complete inventory coverage')
    get = lambda name: json.loads(data[name])
    health = get('final-health.json')
    check(hashes['final-health.json'] == manifest['health_sha256'] == sha((RAW / 'seal-1/final-health.json').read_bytes()), 'final health binding')
    check(health['passed'] and health['idle'] and len(health['modules']) == 73 and not health['new_faults_in_retained_dmesg'], 'final recovery cleanup')
    check(health['build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and health['release'] == '6.1.159-kdclobber2', 'recovery identity')
    check(not health['timing_started'] and not health['performance_accepted'] and health['p95'] == 'DEFERRED', 'unscored correctness only')
    check(len(health['sessions']) == 10, 'all affected results present')
    source_bindings = 0
    for name in data:
        if not name.endswith('/source-sha256.json'):
            continue
        prefix = name.rsplit('/', 1)[0]
        for source, digest in get(name).items():
            candidates = [prefix + '/source/' + source, prefix + '/' + source]
            matches = [n for n in candidates if n in hashes]
            check(len(matches) == 1 and hashes[matches[0]] == digest, 'frozen source binding: ' + source)
            source_bindings += 1
    for item in health['sessions']:
        prefix = item['mode'] + '-1/' + item['task']
        check(hashes[prefix + '/result.json'] == item['sha256'], 'session hash binding')
        row = get(prefix + '/result.json')
        check(row['passed'] and row['drained'] and row['boot_id'] == item['boot_id'], 'session completion/drain')
        check(data[prefix + '/result.json'] == (RAW / (item['mode'] + '-1') / (item['task'] + '.json')).read_bytes(), 'local/archived receipt')
        if item['task'] == 'api':
            check(row['probe']['checks'] == (139 if item['mode'] == 'kd' else 121) and row['probe']['errors'] == 0 and row['probe']['idle'] == 1, 'API oracle')
            check(b'Unit tests: 2 passed, 0 failed' in data[prefix + '/basic.log'], 'basic programs')
            check(hashes[prefix + '/source/tests/kernel/mmap_lock/payload/kd_mmap_probe.ko'] == row['probe_sha256'], 'API binary')
        elif item['task'] == 'mmap':
            check(len(row['cases']) == 6 and all(c['passed'] for c in row['cases']), 'six mmap cases')
            check([c['completion']['completed'] for c in row['cases'] if c['mode'] == 'cycle'] == [1000, 80000], '81000 untouched cycles')
            check([c['completion']['completed'] for c in row['cases'] if c['mode'] == 'lifetime'] == [1, 16], 'separate lifetime completions')
            check(all(o.get('faults', 0) == 0 for c in row['cases'] for o in c['observations']), 'mmap separated from faults')
            check(len(row['cases'][2]['rejected_mutations']) == 9, 'writer proof rejection guards')
            check(hashes[prefix + '/writer-sites.json'] == row['writer_sites_sha256'] == hashes['control/writer-sites.json'], 'exact writer ELF manifest')
        elif item['task'] == 'page-fault':
            check(len(row['cases']) == 18 and all(c['passed'] for c in row['cases']) and row['cases'][-1]['checks'] == 596, 'fault/remote/lifetime cases')
            check(row['children_joined'] == row['fault_threads_joined'] == 16, 'fault joins')
            check(hashes[prefix + '/fault_cases'] == row['binary_sha256'], 'fault binary')
        elif item['task'] == 'completed-fault':
            obs = row['observation']
            check(obs['entries'] == obs['returns'] == obs['completed'] == 64 and obs['errors'] == obs['missed'] == obs['retries'] == 0 and obs['write_reacquired'] == 1, 'actual completed faults')
        for binary, digest in row.get('binaries', {}).items():
            relative = prefix + ('/source/' if item['task'].startswith('body') else '/') + binary
            check(hashes[relative] == digest, 'binary hash: ' + relative)
    body = get('kd-1/body/result.json')['client']
    a, b, c = body['phases']
    check(body['checks'] == 55 and body['errors'] == 0 and body['completed'] == 2576 and body['reader_peak'] == 2 and body['pending_peak'] == 16 and body['idle'] == 1 and body['unmapped'] == 16, 'body effects/readers/cleanup')
    check(a['calls'] == a['supported'] == 2048 and a['delegated'] == 1690 and a['native'] == a['native_only'] == 0, 'supported actual bodies')
    check(b['calls'] == 2064 and b['supported'] == 2048 and b['delegated'] == 1690 and b['native'] == 16 and b['handbacks'] == b['acks'] == 15 and b['native_only'] == 1, 'exact native handback ACKs')
    check(c['calls'] == 2576 and c['native'] == 528 and c['post_ban'] == 512 and c['delegated'] == 1690 and c['handbacks'] == c['acks'] == 15 and c['native_only'] == 1, 'sticky local execution')
    records = re.findall(rb'KD_MM_BODY done mm=([0-9a-f]+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) behavior=(\d+) result=(-?\d+)', data['kd-1/body/kernel.log'])
    check(len(records) == 16, 'sixteen actual executor receipts')
    for mm, origin, executor, start, end, behavior, result in records:
        check(int(mm, 16) == body['mm'] and origin != executor and int(origin) in a['tids'] and int(executor) in a['tids'] and int(end, 16) - int(start, 16) == 12288 and int(behavior) in (16, 17) and int(result) == 0, 'exact returned body identity')
    cancel = get('kd-1/body-cancellation/result.json')['client']
    check(cancel['checks'] == 11 and cancel['errors'] == 0 and cancel['completed'] == 2 and cancel['idle'] == 1 and cancel['unmapped'] == 16, 'cancellation retirement')
    check(cancel['phases'][0]['calls'] == 2 and cancel['phases'][0]['supported'] == cancel['phases'][0]['cancelled'] == 1 and cancel['phases'][0]['delegated'] == 0, 'cancelled before effect')
    for rel in ('payload/module.c', 'payload/api.h', 'client.c', 'run.py', 'test_receipts.py'):
        value = subprocess.check_output(['git', 'show', '0d2a471:tests/kernel/mmap_lock/body/' + rel], cwd=ROOT)
        check(sha(value) == hashes['kd-1/body/source/' + rel] == hashes['kd-1/body-cancellation/source/' + rel], 'live body probe Git identity')
    first = get('build-control-1/build-result.json'); second = get('build-control-2/build-result.json')
    check(first['state'] == second['state'] == 'FAILED' and not first['installed'] and not second['installed'], 'failures preserved')
    check(second['stages'] == ['basic-2-and-body-receipts-4', 'image', 'runtime-modules-73'], 'completed build stages')
    capture = get('capture-control-3/result.json')
    check(capture['passed'] and capture['recovery_unchanged'] and capture['baseline_manifest_sha256'] == hashes['build-evidence/baseline/manifest.json'] == health['candidate_manifest_sha256'], 'corrected capture')
    kernel = get('build-evidence/baseline/manifest.json')
    for name, digest in kernel['source_files'].items():
        check(hashes['build-evidence/source/' + name] == digest, 'kernel source bytes')
    for name, digest in kernel['bundle_files'].items():
        check(hashes['build-evidence/baseline/' + name] == digest, 'kernel bundle bytes')
    old = get('build-evidence/failed-attempt-1/prepare.json')
    for name, digest in old['outputs'].items():
        check(hashes['build-evidence/failed-attempt-1/source/' + name] == digest, 'failed source bytes')
    check(kernel == get('build-evidence/failed-capture-1/manifest.json'), 'capture correction preserved kernel identity')
    check(get('control/writer-sites.json')['vmlinux_sha256'] == kernel['build_files']['vmlinux'], 'writer proof binds candidate')
    return dict(passed=True, checks=checks, mismatches=0, archives=len(manifest['groups']),
                files=files, directories=directories, symlinks=links, source_bindings=source_bindings,
                compressed_bytes=compressed, payload_bytes=payload, sessions=10,
                returned_compiled_bodies=1690, handbacks=15, acks=15, cancelled_queued=1,
                manifest_sha256=sha((ARCHIVES / 'archives.json').read_bytes()), health_sha256=manifest['health_sha256'],
                script_sha256=sha(Path(__file__).read_bytes()), performance_accepted=False,
                scope='Inventory, source/binary/Git bindings, exact MM/body results, retained failures and recovery; no extraction or archived-code execution')


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, sort_keys=True))
