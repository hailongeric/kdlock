#!/usr/bin/env python3
"""Fetch and verify one finalized MM arm; no archive/timing or archived-code execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HARNESS = 'f4ae82cfdf053c679c5d09ee8e503a7919764c9b'
ARCHIVER = 'fbde42310b1b9f01e866852e70a177a45913d44a7253249bd8eb1b3e09b1f327'
REMOTE = '/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/killable-mm-20261031'
CORE = Path('/tmp/kdlock-killable-offline-20261031/nano_core.py')
CORE_SHA = '782280a1b63dda4a08dda36fd1db621ee3121111a273a705f97b2637fbef309f'
FRESH_CONTROLS = CORE.parent / 'fresh_controls.py'
FRESH_CONTROLS_SHA = 'f77e60625bdc2a53e7b1629c76355028be393f381d0d5a270a422461dc034f79'
ORIGINAL_FETCH_SHA = '19e73578e919af0d0e50248ddca647f976062f3786944ba955afaf0ec0541e53'
MAP_MEMBER = 'preservation-inputs/preservation-map.json'
BUNDLE_MEMBER = 'preservation-inputs/kernel-bundle/manifest.json'
STEPS = ('sites', 'api', 'mapping', 'faults', 'completed', 'mmap1-identity', 'mmap1-measure', 'endpoint')
ARMS = {
    'baseline-f7-scope1-kd': dict(
        variant='kdscope1-kd', release='7.0.0-38-kdscope1',
        build='/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build',
        bundle='/root/kdlock-kernel-baselines/linux70-kdscope1-kd-20261030',
        kernel_project_commit='8446f4ecb08816380a4c233197a8ce5e4d333aac',
        provider_comparison_commit='f7a84065e84474380faa37eeadfdf534abd72a68'),
    'candidate-22d-scope2-kd': dict(
        variant='kdscope2-kd', release='7.0.0-38-kdscope2',
        build='/mnt/kdlock-builds2/linux-7.0.0-38-kdscope2/build',
        bundle='/root/kdlock-kernel-baselines/linux70-kdscope2-kd-20261031',
        kernel_project_commit=HARNESS,
        provider_comparison_commit='22d62d5c13cad3c61c97dd47524da908769f1a52')}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


GUEST = r'''import hashlib,json,pathlib,subprocess,sys
base=pathlib.Path(sys.argv[1]);name=sys.argv[2];expected=json.loads(sys.argv[3])
boot,harness,archiver=sys.argv[4:7];kernel=json.loads(sys.argv[7]);steps=json.loads(sys.argv[8])
control=base/(name+'-archive-control');archives=base/(name+'-archives')
paths={'archive-owner':control/'owner.json','archive':archives/'archives.json',
       'inventory':archives/'input-inventory.json','aliases':control/'alias-map.json',
       'preservation-map':control/'preservation-map.json'}
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
need(all(p.is_file() and not p.is_symlink() and sha(p)==expected[n] for n,p in paths.items()),'actual receipt hashes differ')
o,a,aliases,preservation=[json.loads(paths[n].read_bytes())for n in ('archive-owner','archive','aliases','preservation-map')]
need(o.get('schema')==1 and o.get('state')=='COMPLETE' and o.get('completed')is True and o.get('idle')is True and
     o.get('drain_unknown')is False and o.get('child_returncode')==0 and o.get('arm')==name and o.get('boot_id')==boot and
     o.get('harness_commit')==harness and o.get('kernel')==kernel and o.get('script_sha256')==archiver and
     o.get('performance_accepted')is False and set(o['step_owners'])==set(steps),'archive owner incomplete or generation differs')
need(o['archives_sha256']==expected['archive'] and o['input_inventory_sha256']==expected['inventory'] and
     o['alias_map_sha256']==expected['aliases'] and o['preservation_map_sha256']==expected['preservation-map'],'archive receipt chain differs')
need(a.get('completed')is True and a.get('guest_idle')is True and a.get('guest_base')==str(base/name) and
     a.get('archive_prefix')==name and a.get('boot_id')==boot and a.get('kernel_variant')==kernel['variant'] and
     a.get('kernel_release')==kernel['release'] and a['input_inventory_sha256']==expected['inventory'] and
     a['health_sha256']==o['final_health_sha256'],'archive index identity differs')
need(aliases.get('schema')==1 and aliases.get('arm')==name and aliases.get('boot_id')==boot and
     aliases.get('harness_commit')==harness and aliases.get('owners')==o['step_owners'] and
     aliases.get('bundle_member')=='preservation-inputs/kernel-bundle/manifest.json' and
     aliases.get('performance_accepted')is False,'alias map differs')
need(preservation.get('schema')==1 and preservation.get('arm')==name and preservation.get('boot_id')==boot and
     preservation.get('harness_commit')==harness and preservation.get('alias_map_sha256')==expected['aliases'] and
     preservation.get('original_paths_retained')is True and preservation.get('performance_accepted')is False,'preservation map differs')
more={control/'controller.py':archiver,control/'bindings.json':o['bindings_sha256']}
need(all(sha(p)==h for p,h in more.items()),'archive control input differs')
bound={**{p:expected[n]for n,p in paths.items()},**more}
code=subprocess.call(['tar','--hard-dereference','-C',str(base),'-cf','-',name+'-archives',name+'-archive-control'])
need(code==0 and all(sha(p)==h for p,h in bound.items()),'transport or final receipt check failed')
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=ARMS, required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--offline-transport', type=Path)
    parser.add_argument('--offline-receipt', type=Path)
    parser.add_argument('--offline-receipt-sha256')
    for name in ('archive-owner', 'archive', 'inventory', 'aliases', 'preservation-map'):
        parser.add_argument('--' + name + '-sha256', required=True)
    args = parser.parse_args()
    need(bool(args.offline_transport) == bool(args.offline_receipt) == bool(args.offline_receipt_sha256),
         'offline mode requires original transport, failed receipt and its actual hash')
    expected = {name: getattr(args, name.replace('-', '_') + '_sha256') for name in
                ('archive-owner', 'archive', 'inventory', 'aliases', 'preservation-map')}
    need(all(re.fullmatch('[0-9a-f]{64}', value) for value in expected.values()),
         'actual finalized receipt hashes required')
    need(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.boot_id),
         'actual completed arm boot ID required')
    need(sha(CORE) == CORE_SHA and sha(FRESH_CONTROLS) == FRESH_CONTROLS_SHA,
         'reviewed offline archive reader or local dependency differs')
    name, kernel = args.arm, ARMS[args.arm]
    raw = args.destination
    need(raw.is_absolute() and raw.parent == Path('/dev/shm') and raw.resolve() == raw and
         not raw.exists() and not raw.is_symlink(), 'new direct /dev/shm destination required')
    need(Path('/dev/shm').is_mount() and shutil.disk_usage(raw.parent).free > 2 * 1024**3,
         'actual source-host tmpfs needs at least 2 GiB free')
    raw.mkdir()
    roots = {name + suffix for suffix in ('-archives', '-archive-control')}
    transport = args.offline_transport or raw / 'transport.tar'
    receipt_path = raw / 'transfer.json'
    receipt = dict(completed=False, started=time.time(), arm=name, boot_id=args.boot_id,
                   kernel=kernel, harness_commit=HARNESS,
                   expected_sha256=expected, remote_base=REMOTE, roots=sorted(roots),
                   destination=str(raw), script_sha256=sha(__file__),
                   mount_namespace=os.readlink('/proc/self/ns/mnt'),
                   destination_device=raw.stat().st_dev,
                   performance_accepted=False, offline_analysis_pending=True,
                   scope='Read-only transport and host archive-byte verification; no score validation or guest drain inference')

    def save():
        tmp = receipt_path.with_name('.transfer.json.tmp')
        tmp.write_text(json.dumps(receipt, indent=2) + '\n')
        tmp.replace(receipt_path)

    save()
    remote = shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh', shlex.join(
        ['python3', '-c', GUEST, REMOTE, name, json.dumps(expected), args.boot_id,
         HARNESS, ARCHIVER, json.dumps(kernel), json.dumps(STEPS)])])
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'eric@10.176.26.71', remote]
    if args.offline_transport:
        receipt['offline_inputs'] = dict(transport=str(args.offline_transport),
                                         failed_receipt=str(args.offline_receipt))
    else:
        receipt['argv'] = command
    try:
        if args.offline_transport:
            need(re.fullmatch('[0-9a-f]{64}', args.offline_receipt_sha256) and
                 args.offline_receipt.is_file() and not args.offline_receipt.is_symlink() and
                 sha(args.offline_receipt) == args.offline_receipt_sha256,
                 'original failed transfer receipt differs')
            prior = json.loads(args.offline_receipt.read_bytes())
            need(prior.get('completed') is False and prior.get('returncode') == 0 and
                 prior.get('arm') == name and prior.get('boot_id') == args.boot_id and
                 prior.get('kernel') == kernel and prior.get('harness_commit') == HARNESS and
                 prior.get('expected_sha256') == expected and prior.get('remote_base') == REMOTE and
                 prior.get('roots') == sorted(roots) and prior.get('script_sha256') == ORIGINAL_FETCH_SHA and
                 prior.get('error') == 'ModuleNotFoundError("No module named \'fresh_controls\'")' and
                 transport == Path(prior['destination']) / 'transport.tar' and
                 args.offline_receipt == Path(prior['destination']) / 'transfer.json' and
                 transport.is_file() and not transport.is_symlink() and
                 transport.stat().st_size == prior['transport_bytes'] and sha(transport) == prior['transport_sha256'],
                 'only the exact completed transfer/import failure may continue offline')
            shutil.copyfile(args.offline_receipt, raw / 'prior-failed-transfer.json')
            code = 0
            receipt.update(offline_continuation=True, remote_actions_executed=False,
                           prior_failed_transfer_path=str(args.offline_receipt),
                           prior_failed_transfer_sha256=args.offline_receipt_sha256,
                           original_transport_path=str(transport), original_transport_retained=True)
            save()
        else:
            with transport.open('xb') as output, (raw / 'transport.log').open('xb') as error:
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=error)
                receipt['pid'] = child.pid
                save()
                try:
                    code = child.wait(timeout=1200)
                except subprocess.TimeoutExpired:
                    receipt.update(timed_out=True, remote_completion_unconfirmed=True)
                    try:
                        child.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            child.kill()
                        except ProcessLookupError:
                            pass
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                    receipt.update(returncode=child.poll(),
                                   local_transport_completion_unconfirmed=child.poll() is None)
                    raise
        receipt['returncode'] = code
        need(code == 0, 'fetch failed; preserve partial transport')
        receipt.update(transport_sha256=sha(transport), transport_bytes=transport.stat().st_size)
        need(shutil.disk_usage(raw).free > transport.stat().st_size + 1024**3,
             'retain fetched transport; insufficient tmpfs headroom to unpack')
        files = {}
        seen = set()
        with tarfile.open(transport, 'r:') as archive:
            for entry in archive:
                member = entry.name.rstrip('/')
                relative = PurePosixPath(member)
                need(member and not relative.is_absolute() and '..' not in relative.parts and
                     str(relative) == member and member not in seen, 'invalid or duplicate transport member')
                seen.add(member)
                need((relative.parts[0] in roots and (entry.isdir() or entry.isfile())),
                     'unexpected transport member type or root; retain original tar')
                destination = raw / member
                if entry.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                need(not destination.exists() and entry.size >= 0, 'transport target exists')
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as incoming, destination.open('xb') as output:
                    shutil.copyfileobj(incoming, output)
                need(destination.stat().st_size == entry.size, 'truncated transport member')
                files[member] = dict(sha256=sha(destination), bytes=entry.size, mode=entry.mode,
                                     uid=entry.uid, gid=entry.gid, mtime=entry.mtime)

        def bound(relative, digest):
            need(relative in files and files[relative]['sha256'] == digest,
                 'copied evidence differs: ' + relative)
            return raw / relative

        def checked_json(relative, digest):
            return json.loads(bound(relative, digest).read_bytes())

        paths = {'archive-owner': name + '-archive-control/owner.json',
                 'archive': name + '-archives/archives.json',
                 'inventory': name + '-archives/input-inventory.json',
                 'aliases': name + '-archive-control/alias-map.json',
                 'preservation-map': name + '-archive-control/preservation-map.json'}
        values = {key: checked_json(relative, expected[key]) for key, relative in paths.items()}
        owner, metadata, aliases, preservation = (values[key] for key in
                                                  ('archive-owner', 'archive', 'aliases', 'preservation-map'))
        bound(name + '-archive-control/controller.py', ARCHIVER)
        bindings = checked_json(name + '-archive-control/bindings.json', owner['bindings_sha256'])
        need(bindings['arm'] == name and bindings['boot_id'] == args.boot_id and
             bindings['step_owners'] == owner['step_owners'], 'copied bindings identity differs')
        need(sha(CORE) == CORE_SHA and sha(FRESH_CONTROLS) == FRESH_CONTROLS_SHA,
             'reviewed offline archive reader or local dependency changed')
        # The pinned dependency imports nano_core. Publish this same module
        # under its normal name before execution, avoiding a second core load.
        need('nano_core' not in sys.modules and 'fresh_controls' not in sys.modules,
             'offline reader modules were already loaded')
        sys.path.insert(0, str(CORE.parent))
        spec = importlib.util.spec_from_file_location('nano_core', CORE)
        core = importlib.util.module_from_spec(spec)
        sys.modules['nano_core'] = core
        spec.loader.exec_module(core)
        cache = raw / 'receipt-cache'
        cache.mkdir()
        parsed = core.Archive(raw / (name + '-archives'), cache)
        need(parsed.meta['guest_base'] == REMOTE + '/' + name and parsed.meta['boot_id'] == args.boot_id and
             parsed.meta['kernel_variant'] == kernel['variant'] and
             parsed.meta['kernel_release'] == kernel['release'] and
             parsed.hashes[MAP_MEMBER] == expected['preservation-map'] and
             parsed.hashes['preservation-inputs/alias-map.json'] == expected['aliases'] and
             parsed.hashes['preservation-inputs/archive-controller.py'] == ARCHIVER and
             parsed.hashes['preservation-inputs/archive-bindings.json'] == owner['bindings_sha256'],
             'archived identity or preserved controls differ')
        need(parsed.json(MAP_MEMBER) == preservation and
             parsed.json('preservation-inputs/alias-map.json') == aliases,
             'internal and external map copies differ')
        need(parsed.hashes[parsed.meta['health_path']] == owner['final_health_sha256'],
             'archived final health differs')
        health = parsed.json(parsed.meta['health_path'])
        need(health.get('idle') is True and health.get('boot_id') == args.boot_id and
             health.get('arm') == name and health.get('harness_commit') == HARNESS and
             health.get('kernel') == kernel and health.get('step_owners') == owner['step_owners'] and
             health.get('preservation_map_sha256') == expected['preservation-map'],
             'archived health identity differs')
        preserved_sources = {}
        for row in preservation['files']:
            core.safe(row['member'])
            need(parsed.hashes.get(row['member']) == row['sha256'],
                 'preserved member bytes differ: ' + row['member'])
            need(row['source'] not in preserved_sources or
                 preserved_sources[row['source']] == row['sha256'],
                 'one preserved original has conflicting bytes')
            preserved_sources[row['source']] = row['sha256']
        for original, member in aliases['aliases'].items():
            core.safe(member)
            need(Path(original).is_absolute() and '..' not in Path(original).parts and
                 member in parsed.hashes, 'alias lacks authenticated regular member')
            need(preserved_sources.get(original) == parsed.hashes[member],
                 'alias differs from preserved original source binding')
            prefix = REMOTE + '/' + name + '/'
            if original.startswith(prefix):
                need(parsed.hashes.get(original[len(prefix):]) == parsed.hashes[member],
                     'alias changes already archived original bytes')
        for step, digest in aliases['owners'].items():
            need(step in STEPS and parsed.hashes.get(step + '-controller.json') == digest,
                 'archived step owner differs')
        need(set(aliases['owners']) == set(STEPS), 'all eight step owners required')
        bundle = parsed.json(BUNDLE_MEMBER)
        need(bundle['variant'] == kernel['variant'] and bundle['runtime_policy']['mmap_mode'] == 'on',
             'archived KD bundle differs')
        arm = dict(archives=str(raw / (name + '-archives')), archives_sha256=expected['archive'],
                   bundle_member=BUNDLE_MEMBER, owners=aliases['owners'], aliases=aliases['aliases'])
        for leaf, value in (('member-sha256.json', parsed.hashes),
                            ('archive-provenance.json', parsed.provenance), ('analysis-arm.json', arm)):
            (raw / leaf).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
        receipt.update(files=files, group_archives=len(metadata['groups']),
                       regular_members=len(parsed.hashes),
                       member_manifest_sha256=sha(raw / 'member-sha256.json'),
                       archive_provenance_sha256=sha(raw / 'archive-provenance.json'),
                       offline_reader_sha256=CORE_SHA,
                       offline_reader_dependency_sha256=FRESH_CONTROLS_SHA,
                       analysis_arm_sha256=sha(raw / 'analysis-arm.json'),
                       transport_verified=True, archive_members_verified=True)
        save()
        if args.offline_transport:
            need(sha(args.offline_receipt) == args.offline_receipt_sha256 and
                 sha(raw / 'prior-failed-transfer.json') == args.offline_receipt_sha256 and
                 transport.stat().st_size == prior['transport_bytes'] and
                 sha(transport) == prior['transport_sha256'], 'original failed attempt changed')
        shutil.rmtree(cache)
        if not args.offline_transport:
            transport.unlink()
        receipt.update(completed=True, finished=time.time(),
                       transport_intermediate_removed=not bool(args.offline_transport),
                       removal_scope=('Only the new derived receipt-cache; original failed attempt/tar retained'
                                      if args.offline_transport else
                                      'Only verified task-created transport.tar and derived receipt-cache; original compressed groups/control retained'))
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        save()
    print(json.dumps({key: receipt[key] for key in
                      ('completed', 'transport_bytes', 'transport_sha256', 'group_archives', 'analysis_arm_sha256')}))


if __name__ == '__main__':
    main()
