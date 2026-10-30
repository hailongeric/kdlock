#!/usr/bin/env python3
"""Fetch one finalized fresh KD210 arm; no archive/timing or archived-code execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile
import time

COMMITS = {'f7': 'f7a84065e84474380faa37eeadfdf534abd72a68',
           '22d': '22d62d5c13cad3c61c97dd47524da908769f1a52'}
NANO = '26d484996dd8f2a2b3e7e0e7ee813c63713fcecff8ce90b7eb031a88a52fc0c3'
ENDPOINT = '40f576dbb3128de1f08229bd8d488fad6d722cea84591cf35c94f63d9401aa15'
BOOT = '760d4758-28b8-4903-b1d5-5bbb8938430d'
REMOTE = '/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench'


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
commit,nano,endpoint,boot=sys.argv[4:8]
control=base/(name+'-control');archives=base/(name+'-archives')
basic=base/(name+'-basic');basic_control=base/(name+'-basic-control')
paths={'archive':archives/'archives.json','owner':control/'owner.json',
       'archive-owner':control/'archive-owner.json',
       'endpoint-receipt':control/'endpoint-receipt.json','host-after':control/'host-after.json'}
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
need(all(p.is_file() and not p.is_symlink() and sha(p)==expected[n] for n,p in paths.items()),'actual receipt hashes differ')
a,o,r,e=[json.loads(paths[n].read_bytes())for n in ('archive','owner','archive-owner','endpoint-receipt')]
need(a.get('completed')is True and a.get('guest_idle')is True and a.get('guest_base')==str(base/name),'archive incomplete')
need(o.get('completed')is True and o.get('idle')is True and o.get('returncode')==0 and o.get('source_commit')==commit,'run incomplete')
need(o.get('arm')=='kdlock' and o.get('rounds_per_point')==1 and o.get('validated_points')==o.get('expected_points')==210 and
     o.get('host_mode')=='strict' and o.get('performance_accepted')is False and o['inputs']['controller.py']==nano,'run generation differs')
need(r.get('completed')is True and r.get('idle')is True and r.get('returncode')==0 and r.get('source_commit')==commit,'archive owner incomplete')
need(r['run_owner_sha256']==expected['owner'] and r['archives_sha256']==expected['archive'] and
     r['endpoint_receipt_sha256']==expected['endpoint-receipt'] and r['host_after_sha256']==expected['host-after'],'archive chain differs')
need(e.get('completed')is True and e.get('returncode')==0 and e.get('source_commit')==commit and
     e.get('output_sha256')==expected['host-after'] and e.get('script_sha256')==endpoint and
     e.get('completion_marker')=='COMPLETE killable-nano '+commit,'endpoint incomplete')
policy=control/'endpoint-policy.json';need(sha(policy)==r['endpoint_policy_sha256']==e['endpoint_policy_sha256'],'endpoint policy differs')
need(a['boot_id']==o['boot_id']==r['boot_id']==boot==pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'boot differs')
bp=basic_control/'owner.json';br=basic/'result.json'
need(sha(bp)==o['inputs']['basic-owner.json'] and sha(br)==o['inputs']['basic-result.json'],'separate basic receipt differs')
b=json.loads(bp.read_bytes());result=json.loads(br.read_bytes())
need(b.get('completed')is True and b.get('final_idle')is True and b.get('returncode')==0 and b.get('source_commit')==commit and
     b.get('boot_id')==boot and b.get('result_sha256')==sha(br) and b['inputs']['controller.py']==nano,'basic owner incomplete')
need(result.get('passed')is True and result.get('final_idle')is True and result.get('boot_id')==boot and
     result.get('timing_started')is False and [x['family']for x in result['results']]==['spin','mutex','rwlock','rwsem'] and
     all(x['passed'] and x['drained'] and x['jit_completions']>0 for x in result['results']),'basic result incomplete')
bound={str(p):sha(p)for p in [*paths.values(),policy,bp,br]}
code=subprocess.call(['tar','--hard-dereference','-C',str(base),'-cf','-',
                      name+'-archives',name+'-control',name+'-basic',name+'-basic-control'])
need(code==0 and all(sha(pathlib.Path(p))==h for p,h in bound.items()),'transport or final receipt check failed')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=COMMITS, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--offline-transport', type=Path)
    parser.add_argument('--offline-receipt', type=Path)
    parser.add_argument('--offline-receipt-sha256')
    for name in ('archive', 'owner', 'archive-owner', 'endpoint-receipt', 'host-after'):
        parser.add_argument('--' + name + '-sha256', required=True)
    args = parser.parse_args()
    need(bool(args.offline_transport) == bool(args.offline_receipt) == bool(args.offline_receipt_sha256),
         'offline mode requires transport, original failed receipt and its actual hash')
    expected = {name: getattr(args, name.replace('-', '_') + '_sha256') for name in
                ('archive', 'owner', 'archive-owner', 'endpoint-receipt', 'host-after')}
    need(all(re.fullmatch('[0-9a-f]{64}', value) for value in expected.values()),
         'actual finalized receipt hashes required')
    commit = COMMITS[args.arm]
    name = 'killable-nano-' + commit[:8] + '-20261031'
    raw = args.destination
    need(raw.is_absolute() and raw.parent == Path('/dev/shm') and raw.resolve() == raw and
         not raw.exists() and not raw.is_symlink(), 'new direct /dev/shm destination required')
    need(Path('/dev/shm').is_mount() and shutil.disk_usage(raw.parent).free > 2 * 1024**3,
         'actual source-host tmpfs needs at least 2 GiB free')
    raw.mkdir()
    roots = {name + suffix for suffix in ('-archives', '-control', '-basic', '-basic-control')}
    transport = args.offline_transport or raw / 'transport.tar'
    receipt_path = raw / 'transfer.json'
    receipt = dict(completed=False, started=time.time(), source_commit=commit,
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
        ['python3', '-c', GUEST, REMOTE, name, json.dumps(expected), commit, NANO, ENDPOINT, BOOT])])
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'eric@10.176.26.71', remote]
    if args.offline_transport:
        receipt['offline_inputs'] = dict(transport=str(args.offline_transport),
                                         failed_receipt=str(args.offline_receipt))
    else:
        receipt['argv'] = command
    try:
        if args.offline_transport:
            need(re.fullmatch('[0-9a-f]{64}', args.offline_receipt_sha256) and
                 sha(args.offline_receipt) == args.offline_receipt_sha256,
                 'original failed transfer receipt differs')
            prior = json.loads(args.offline_receipt.read_bytes())
            need(prior.get('completed') is False and prior.get('returncode') == 0 and
                 prior.get('source_commit') == commit and prior.get('expected_sha256') == expected and
                 prior.get('script_sha256') == 'e64c4d7de1dddf04f35ab15d5e4195ce7d2f9a4c9e7eff9f624f62d5d39be697' and
                 prior.get('error') == "RuntimeError('unexpected transport member type or root; retain original tar')" and
                 transport == Path(prior['destination']) / 'transport.tar' and
                 args.offline_receipt == Path(prior['destination']) / 'transfer.json' and
                 transport.is_file() and not transport.is_symlink() and
                 transport.stat().st_size == prior['transport_bytes'] and sha(transport) == prior['transport_sha256'],
                 'only the exact completed transport/type-refusal may continue offline')
            shutil.copyfile(args.offline_receipt, raw / 'prior-failed-transfer.json')
            code = 0
            receipt.update(returncode=0, offline_continuation=True, remote_actions_executed=False,
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
        links = {}
        sessions = {'spin': 'c01-t16-r00-direct-kdlock-adaptive',
                    'mutex': 'c01-t16-r00-direct-kdlock-adaptive-public',
                    'rwlock': 'cacheline-c01-kdlock-w020-t16-r00',
                    'rwsem': 'rwsem-cacheline-c16-kdlock-w100-t16-r00'}
        expected_links = {name + '-basic/' + family + '/' + session + '/workspace/' + leaf:
                          REMOTE + '/' + name + '-basic/' + family + '/source/' + leaf
                          for family, session in sessions.items() for leaf in ('disassem', 'include')}
        seen = set()
        with tarfile.open(transport, 'r:') as archive:
            for entry in archive:
                member = entry.name.rstrip('/')
                relative = PurePosixPath(member)
                need(member and not relative.is_absolute() and '..' not in relative.parts and
                     str(relative) == member and member not in seen, 'invalid or duplicate transport member')
                seen.add(member)
                need((relative.parts[0] in roots and (entry.isdir() or entry.isfile() or entry.issym())),
                     'unexpected transport member type or root; retain original tar')
                destination = raw / member
                if entry.issym():
                    need(expected_links.get(member) == entry.linkname,
                         'unexpected basic workspace symlink; preserve transport')
                    links[member] = dict(original_target=entry.linkname, mode=entry.mode,
                                         uid=entry.uid, gid=entry.gid, mtime=entry.mtime)
                    continue
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

        need(set(links) == set(expected_links), 'exact eight basic workspace links required')
        for member, row in links.items():
            target_member = str(PurePosixPath(row['original_target']).relative_to(REMOTE))
            target, link = raw / target_member, raw / member
            need(target.is_dir() and target_member in seen and not target.is_symlink() and
                 not link.exists() and not link.is_symlink(), 'copied family source/link target differs')
            relative_target = os.path.relpath(target, link.parent)
            os.symlink(relative_target, link)
            need(link.resolve() == target.resolve() and target.resolve().is_relative_to(raw),
                 'recreated relative link escapes copied family source')
            row.update(retained_target_member=target_member, local_relative_target=relative_target)
        link_path = raw / 'transport-links.json'
        link_path.write_text(json.dumps(dict(schema=1, original_guest_targets_preserved=True,
                            reconstruction='relative links to the exact same family source',
                            links=links), indent=2, sort_keys=True) + '\n')

        def bound(relative, digest):
            need(relative in files and files[relative]['sha256'] == digest,
                 'copied evidence differs: ' + relative)
            return raw / relative

        def checked_json(relative, digest):
            return json.loads(bound(relative, digest).read_bytes())

        paths = {'archive': name + '-archives/archives.json', 'owner': name + '-control/owner.json',
                 'archive-owner': name + '-control/archive-owner.json',
                 'endpoint-receipt': name + '-control/endpoint-receipt.json',
                 'host-after': name + '-control/host-after.json'}
        values = {key: checked_json(relative, expected[key]) for key, relative in paths.items()}
        metadata, owner, archived = (values[key] for key in ('archive', 'owner', 'archive-owner'))
        group_names = set()
        for row in metadata['groups']:
            group = row['file']
            need(group and PurePosixPath(group).name == group and group not in group_names,
                 'archive group filename differs')
            group_names.add(group)
            path = bound(name + '-archives/' + group, row['sha256'])
            need(path.stat().st_size == row['bytes'], 'archive group size differs')
        bound(name + '-archives/input-inventory.json', metadata['input_inventory_sha256'])
        for leaf, digest in owner['inputs'].items():
            need(PurePosixPath(leaf).name == leaf, 'control input is not a direct file')
            bound(name + '-control/' + leaf, digest)
        basic = checked_json(name + '-basic-control/owner.json', owner['inputs']['basic-owner.json'])
        result = checked_json(name + '-basic/result.json', owner['inputs']['basic-result.json'])
        need(basic['result_sha256'] == owner['inputs']['basic-result.json'], 'basic result binding differs')
        for leaf, digest in basic['inputs'].items():
            need(PurePosixPath(leaf).name == leaf, 'basic input is not a direct file')
            bound(name + '-basic-control/' + leaf, digest)
        for row in result['results']:
            relative = PurePosixPath(row['receipt']).relative_to(PurePosixPath(REMOTE) / (name + '-basic'))
            bound(name + '-basic/' + str(relative), row['receipt_sha256'])
        policy = archived['endpoint_policy_sha256']
        bound(name + '-control/endpoint-policy.json', policy)
        need(values['endpoint-receipt']['endpoint_policy_sha256'] == policy, 'endpoint policy binding differs')
        arm = dict(archives=str(raw / (name + '-archives')), archives_sha256=expected['archive'],
                   control=str(raw / (name + '-control')), owner_sha256=expected['owner'],
                   archive_owner_sha256=expected['archive-owner'])
        arm_path = raw / 'analysis-arm.json'
        arm_path.write_text(json.dumps(arm, indent=2) + '\n')
        receipt.update(files=files, group_archives=len(group_names),
                       link_count=len(links), link_manifest_sha256=sha(link_path),
                       analysis_arm_sha256=sha(arm_path), transport_verified=True)
        save()
        if not args.offline_transport:
            transport.unlink()
        receipt.update(completed=True, finished=time.time(),
                       transport_intermediate_removed=not bool(args.offline_transport),
                       removal_scope=('No original failed transport or partial evidence changed' if args.offline_transport else
                                      'Only this verified task-created transport.tar; extracted evidence and original link metadata retained'))
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        save()
    print(json.dumps({key: receipt[key] for key in
                      ('completed', 'transport_bytes', 'transport_sha256', 'group_archives', 'analysis_arm_sha256')}))


if __name__ == '__main__':
    main()
