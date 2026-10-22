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
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-unmap-body-20261022'
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
    check(len(health['sessions']) == 16, 'all affected results present')
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
        prefix = item['run'] + '/' + item['task']
        check(hashes[prefix + '/result.json'] == item['sha256'], 'session hash binding')
        row = get(prefix + '/result.json')
        check(row['passed'] and row['drained'] and row['boot_id'] == item['boot_id'], 'session completion/drain')
        check(data[prefix + '/result.json'] == (RAW / item['run'] / (item['task'] + '.json')).read_bytes(), 'local/archived receipt')
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
            relative = prefix + ('/source/' if item['task'].startswith(('body', 'fault-', 'unmap-')) else '/') + binary
            check(hashes[relative] == digest, 'binary hash: ' + relative)
    body = get('kd-1/body/result.json')['client']
    a, b, c = body['phases']
    check(body['errors'] == 0 and body['completed'] == 2576 and body['reader_peak'] == 2 and
          body['pending_peak'] == 16 and body['idle'] == 1 and body['unmapped'] == 16, 'advice preserved')
    check(a['calls'] == a['supported'] == 2048 and a['delegated'] > 0, 'advice remote count')
    check(b['handbacks'] == b['acks'] == c['handbacks'] == c['acks'] == 15 and c['post_ban'] == 512 and
          c['native_only'] == 1 and c['delegated'] == a['delegated'], 'advice ACK/sticky preservation')
    cancellation = get('kd-1/body-cancellation/result.json')['client']
    check(cancellation['errors'] == 0 and cancellation['idle'] == 1 and
          cancellation['phases'][0]['cancelled'] == 1, 'advice cancellation preservation')
    fault = get('kd-1/fault-body/result.json')['client']
    a, b, c = fault['phases']
    check(fault['errors'] == 0 and fault['completed'] == 400 and fault['checks'] > 400 * 8190 and
          fault['reader_peak'] == 2 and fault['delegated_with_readers'] == a['delegated'] > 0 and fault['idle'] == 1 and
          fault['unmapped_pages'] == 512, 'actual fault contents/readers/cleanup')
    check(a['calls'] == a['supported'] == 256 and a['delegated'] > 0 and a['native'] == 0, 'supported installation')
    check(b['calls'] == 272 and b['native'] == 16 and b['handbacks'] == b['acks'] == 15 and
          b['refused'] == b['native_only'] == 1, 'queued native continuation')
    check(c['calls'] == 400 and c['native'] == 144 and c['post_ban'] == 128 and c['delegated'] == a['delegated'] and
          c['supported'] == 256 and c['handbacks'] == c['acks'] == 15, 'sticky fault refusal')
    pages = {page['address']:page for page in fault['pages']}
    check(len(pages) == len({p['pfn'] for p in pages.values()}) == 256, 'distinct installed physical pages')
    records = re.findall(rb'KD_MM_FAULT done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) address=([0-9a-f]+) pfn=([0-9a-f]+)', data['kd-1/fault-body/kernel.log'])
    check(len(records) == len({r[1] for r in records}) == 16, 'sixteen unique completion receipts')
    for mm, ident, origin, executor, address, pfn in records:
        page = pages[int(address, 16)]
        check(int(mm, 16) == fault['mm'] and origin != executor and int(origin) in a['tids'] and
              int(executor) in a['tids'] and page['origin'] == int(origin) and page['pfn'] == int(pfn, 16),
              'different executor installed the actual PTE')
    for task, count in [('fault-body',15), ('fault-retry',1)]:
        records = {}
        row = get('kd-1/'+task+'/result.json')['client']
        for kind in ('handback', 'ack'):
            records[kind] = re.findall(('KD_MM_FAULT '+kind+r' mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) address=([0-9a-f]+)').encode(), data['kd-1/'+task+'/kernel.log'])
        check(len(records['ack']) == count and len(set(records['ack'])) == count and
              sorted(records['ack']) == sorted(records['handback']), 'exact handback/ACK identities')
        for mm, ident, origin, executor, address in records['ack']:
            check(int(mm,16) == row['mm'] and origin != executor and int(ident)>0, 'borrowed owner refusal identity')
    cancel = get('kd-1/fault-cancellation/result.json')['client']
    check(cancel['cancel_present'] == [1,0] and cancel['cancel_result'] == [0,-14] and
          len(set(cancel['cancel_tid'])) == 2 and cancel['errors'] == 0 and cancel['idle'] == 1 and
          cancel['phases'][0]['cancelled'] == 1 and cancel['phases'][0]['supported'] == 1 and
          cancel['phases'][0]['delegated'] == 0, 'cancelled page absent and read acquisition retired')
    retry = get('kd-1/fault-retry/result.json')['client']
    check(retry['errors'] == 0 and retry['completed'] == 3 and retry['retry_writer_completed'] == 1 and
          retry['idle'] == 1 and retry['phases'][0]['calls'] == 2 and retry['phases'][0]['handbacks'] == 1 and
          retry['phases'][1]['post_ban'] == 1 and retry['phases'][1]['delegated'] == 0,
          'userfaultfd retry releases lock and completes native memory effects')
    unmap = get('kd-2/unmap-body/result.json')['client']
    a, b, c = unmap['phases']
    check(unmap['mode'] == 'body' and unmap['groups'] == unmap['completed'] == 48 and
          unmap['errors'] == 0 and unmap['idle'] == 1 and unmap['reader_peak'] == 2 and
          unmap['pending_peak'] == 16 and unmap['checks'] > 16 * 4 * 4096, 'real munmap memory/reader oracle')
    check(a['calls'] == a['removed'] == 16 and a['delegated'] == 15 and a['native'] == 0 and
          b['calls'] == 32 and b['native'] == 16 and b['handbacks'] == b['acks'] == 15 and
          c['calls'] == 48 and c['native'] == 32 and c['post_ban'] == 16 and
          c['removed'] == 16 and c['delegated'] == 15 and c['refused'] == c['native_only'] == 1,
          'munmap supported/refusal/sticky balance')
    check(unmap['late_fault_blocked'] == 1 and unmap['late_fault_code'] == 1 and
          'kd_mmap_down_read' in unmap['late_fault_stack'] and 'do_user_addr_fault' in unmap['late_fault_stack'],
          'actual hardware fault waits then observes removal')
    for task, count in [('unmap-body', 15), ('unmap-read-first', 0), ('unmap-cancellation', 0)]:
        row = get('kd-2/'+task+'/result.json')['client']
        log = data['kd-2/'+task+'/kernel.log']
        done = re.findall(rb'KD_MM_UNMAP done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) result=0', log)
        check(len(done) == len(set(done)) == count, 'actual remote removal receipt count')
        origins = {o['tid']: o for o in row['phases'][0]['origins']}
        for mm, ident, origin, executor, start, end in done:
            source = origins.get(int(origin), {})
            check(int(mm,16) == row['mm'] and 0 < int(ident) <= 16 and origin != executor and
                  int(executor) in origins and source.get('start') == int(start,16) and
                  source.get('end') == int(end,16), 'other task removed the exact original mapping')
        acknowledgements = {}
        for kind in ('handback', 'ack'):
            acknowledgements[kind] = re.findall(('KD_MM_UNMAP '+kind+r' mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+)').encode(),log)
        expected = {'unmap-body':15, 'unmap-read-first':1, 'unmap-cancellation':0}[task]
        check(len(acknowledgements['ack']) == len(set(acknowledgements['ack'])) == expected and
              sorted(acknowledgements['ack']) == sorted(acknowledgements['handback']), 'exact munmap refusal ACK pairs')
        for mm, ident, origin, executor, start, end in acknowledgements['ack']:
            phase = row['phases'][1 if task == 'unmap-body' else 0]
            origins = {o['tid']: o for o in phase['origins']}
            source = origins.get(int(origin), {})
            check(int(mm,16) == row['mm'] and int(ident)>0 and origin!=executor and
                  int(executor) in origins and source.get('start') == int(start,16) and
                  source.get('end') == int(end,16), 'munmap ACK routing identity')
        before, after = row['phases'][-1], row['after_cleanup']
        check(row['errors'] == 0 and row['idle'] == 1 and row['cleanup_calls'] == row['groups']*3 and
              after['calls']-before['calls'] == after['native']-before['native'] == row['cleanup_calls'] and
              after['removed'] == before['removed'] and after['delegated'] == before['delegated'], 'munmap cleanup does not inflate bodies')
        for phase in [*row['phases'], after]:
            check(phase['calls'] == phase['removed']+phase['native']+phase['cancelled'] and
                  phase['failed'] == 0 and phase['handbacks'] == phase['acks'], 'munmap exact final accounting')
    cancel = get('kd-2/unmap-cancellation/result.json')['client']
    check(cancel['cancel_mapped'] == [0,1] and cancel['cancel_result'] == [0,-4] and
          len(set(cancel['cancel_tid'])) == 2 and cancel['phases'][0]['cancelled'] == 1 and
          cancel['phases'][0]['removed'] == 1, 'cancelled munmap retains original mapping')
    read = get('kd-2/unmap-read-first/result.json')['client']
    check(read['read_first_code'] == 1 and read['completed'] == 3 and
          read['phases'][0]['handbacks'] == 1 and read['phases'][1]['post_ban'] == 1 and
          read['phases'][1]['delegated'] == 0, 'read-first PGD refusal and cached translation removal')
    for revision, folder in [('50412ff','test-build-1'),('50412ff','kd-1/unmap-body'),
                             ('b787a90','test-build-2'),('b787a90','kd-2/unmap-body'),
                             ('b787a90','kd-2/unmap-cancellation'),('b787a90','kd-2/unmap-read-first')]:
        for rel in ('payload/module.c','payload/api.h','payload/Makefile','client.c','run.py','test_receipts.py'):
            value=subprocess.check_output(['git','show',revision+':tests/kernel/mmap_lock/unmap_body/'+rel],cwd=ROOT)
            check(sha(value)==hashes[folder+'/source/'+rel], 'frozen munmap probe revision')
    for preparation in ('test-build-1','test-build-2'):
        check(get(preparation+'/result.json')['passed'] and b'Ran 5 tests' in data[preparation+'/receipts.log'] and
              b'OK' in data[preparation+'/receipts.log'], 'five munmap receipt checks passed')
    failed=get('kd-1/unmap-body/result.json');drain=get('failed-live-drain-1/result.json')
    check(failed['state']=='FAILED' and not failed['passed'] and not failed['drained'] and
          b'open actual fault stack' in data['kd-1/unmap-body/client.json'] and
          drain['passed'] and drain['idle'] and drain['ordinary_unload'], 'failed live probe and independent drain preserved')
    for attempt, log, text in [(1,'modules-serio.log',b'MODULE_LICENSE'),
                              (2,'modules-serio-directory-2.log',b'missing separator'),
                              (3,'modules-serio-directory-3.log',b'hyperv-keyboard.ko')]:
        failed=get('build-control-'+str(attempt)+'/build-result.json')
        check(failed['state']=='FAILED' and not failed['passed'] and not failed['installed'] and
              not failed['booted'] and text in data['build-evidence/'+log], 'failed preparation remains distinguishable')
        check(get('build-evidence/'+log+'.command.json')['returncode']==2, 'failed command status retained')
        for name,digest in get('build-evidence/failed-module-'+str(attempt)+'/sha256.json').items():
            check(hashes['build-evidence/failed-module-'+str(attempt)+'/'+name]==digest, 'failed object/command preservation')
    build = get('build-control-4/build-result.json')
    kernel = get('build-evidence/baseline/manifest.json')
    check(build['passed'] and build['source_commit'].startswith('670796f') and
          build['baseline_manifest_sha256'] == hashes['build-evidence/baseline/manifest.json'] ==
          health['candidate_manifest_sha256'], 'kernel build/capture provenance')
    check(kernel['running']['build_id'] == 'a4f371bb5bca303f6b6d9354bfbf156275479dcb', 'exact candidate')
    for name,digest in kernel['source_files'].items():
        check(hashes['build-evidence/source/'+name] == digest, 'kernel source binding')
    for name,digest in kernel['bundle_files'].items():
        check(hashes['build-evidence/baseline/'+name] == digest, 'kernel capture binding')
    check(get('control/writer-sites.json')['vmlinux_sha256'] == kernel['build_files']['vmlinux'], 'writer ELF proof')
    check(health['advice_body_unchanged'] and health['prior_advice_installed_files'] > 73 and
          health['fault_body_unchanged'] and health['prior_fault_installed_files'] > 73, 'prior advice/fault preserved')
    return dict(passed=True, checks=checks, mismatches=0, archives=len(manifest['groups']),
                files=files, directories=directories, symlinks=links, source_bindings=source_bindings,
                compressed_bytes=compressed, payload_bytes=payload, sessions=16,
                actual_remote_page_installations=fault['phases'][0]['delegated'], pte_bound_receipts=16,
                fault_handbacks=16, fault_acks=16, cancelled_faults=1, advice_remote_bodies=body['phases'][0]['delegated'], actual_remote_vma_removals=15, munmap_handbacks=16,
                cancelled_munmaps=1, munmap_cleanup_calls=159,
                manifest_sha256=sha((ARCHIVES/'archives.json').read_bytes()), health_sha256=manifest['health_sha256'],
                script_sha256=sha(Path(__file__).read_bytes()), performance_accepted=False,
                scope='Read-only inventory, source/Git/binary, PTE/body/ACK, failure and recovery evidence; no archived code execution')


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, sort_keys=True))
