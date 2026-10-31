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
HARNESS = 'de5e4f06a6d60e531a8b329d3c7f2c5335d5e707'
ARCHIVER = 'fd52c123f07d1c9de1996dd2fc8540b8cb8794e2cfe9b22937b6af1a444bd7b0'
PROVENANCE_HELPER_SHA = 'a30f16ccb4036ff5acc186c029359456bcbcbedce8c89a7820cf931bf8cc4bfb'
PROVENANCE_SHA = '2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364'
POLICY = 'mmap-functional-held-writer-v1'
CONFIG = Path('/tmp/kdlock-writer-queue-mm-20261031.config-queue-proof.json')
CONFIG_SHA = 'fafaac5315038e45f150feb4d24a45913a848dfaed8e8c51236952d5087c8584'
REMOTE = '/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/writer-queue-mm-20261031'
CORE = Path('/tmp/kdlock-killable-offline-20261031/nano_core.py')
CORE_SHA = '782280a1b63dda4a08dda36fd1db621ee3121111a273a705f97b2637fbef309f'
FRESH_CONTROLS = CORE.parent / 'fresh_controls.py'
FRESH_CONTROLS_SHA = 'f77e60625bdc2a53e7b1629c76355028be393f381d0d5a270a422461dc034f79'
MAP_MEMBER = 'preservation-inputs/preservation-map.json'
BUNDLE_MEMBER = 'preservation-inputs/kernel-bundle/manifest.json'
STEPS = ('sites', 'api', 'mapping', 'faults', 'completed', 'strict-hold',
         'mmap1-identity', 'mmap1-measure', 'endpoint')


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
boot,harness,archiver,config_sha=sys.argv[4:8];kernel=json.loads(sys.argv[8]);steps=json.loads(sys.argv[9]);policy=sys.argv[10];provenance_sha=sys.argv[11];provenance_helper_sha=sys.argv[12]
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
     o.get('config_sha256')==config_sha and o.get('eligibility_policy')==policy and
     o.get('diagnostic_provenance_helper_sha256')==provenance_helper_sha and
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
     aliases.get('config_member')=='preservation-inputs/config.json' and
     aliases.get('harness_manifest_member')=='preservation-inputs/harness-manifest.json' and
     aliases.get('diagnostic_manifest_member')=='preservation-inputs/diagnostic-manifest.json' and
     aliases.get('config_sha256')==config_sha and aliases.get('eligibility_policy')==policy and
     aliases.get('performance_accepted')is False and set(aliases['logical_steps'])==set(steps),'alias map differs')
need(preservation.get('schema')==1 and preservation.get('arm')==name and preservation.get('boot_id')==boot and
     preservation.get('harness_commit')==harness and preservation.get('config_sha256')==config_sha and
     preservation.get('alias_map_sha256')==expected['aliases'] and preservation.get('original_paths_retained')is True and
     preservation.get('performance_accepted')is False,'preservation map differs')
more={control/'controller.py':archiver,control/'bindings.json':o['bindings_sha256'],control/'config.json':config_sha}
need(all(sha(p)==h for p,h in more.items()),'archive control input differs')
bindings=json.loads((control/'bindings.json').read_bytes())
need(bindings.get('schema')==1 and bindings.get('arm')==name and bindings.get('boot_id')==boot and
     bindings['config']['sha256']==config_sha and bindings['owners']==o['step_owners'],'actual archive bindings differ')
provenance=pathlib.Path(o['diagnostic_provenance']['path'])
need(o['diagnostic_provenance']['sha256']==provenance_sha and sha(provenance)==provenance_sha and aliases['diagnostic_provenance_sha256']==provenance_sha and aliases['diagnostic_provenance_member']=='preservation-inputs/diagnostic-provenance/record.json','actual diagnostic provenance differs')
bound={**{p:expected[n]for n,p in paths.items()},**more,provenance:provenance_sha}
code=subprocess.call(['tar','--hard-dereference','-C',str(base),'-cf','-',name+'-archives',name+'-archive-control'])
need(code==0 and all(sha(p)==h for p,h in bound.items()),'transport or final receipt check failed')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('candidate',), required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--diagnostic-provenance-sha256', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    for name in ('archive-owner', 'archive', 'inventory', 'aliases', 'preservation-map'):
        parser.add_argument('--' + name + '-sha256', required=True)
    args = parser.parse_args()
    expected = {name: getattr(args, name.replace('-', '_') + '_sha256') for name in
                ('archive-owner', 'archive', 'inventory', 'aliases', 'preservation-map')}
    need(all(re.fullmatch('[0-9a-f]{64}', value) for value in expected.values()),
         'actual finalized receipt hashes required')
    need(args.diagnostic_provenance_sha256 == PROVENANCE_SHA, 'exact completed diagnostic provenance hash required')
    need(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.boot_id),
         'actual completed arm boot ID required')
    need(sha(CORE) == CORE_SHA and sha(FRESH_CONTROLS) == FRESH_CONTROLS_SHA,
         'reviewed offline archive reader/dependency differs')
    need(re.fullmatch('[0-9a-f]{64}', ARCHIVER) and sha(CONFIG) == CONFIG_SHA,
         'reviewed archive producer/configuration not frozen')
    config = json.loads(CONFIG.read_bytes())
    need(config['schema'] == 1 and config['campaign'] == REMOTE and
         config['harness']['commit'] == HARNESS and config['eligibility_policy'] == POLICY,
         'exact common configuration differs')
    name, kernel = args.arm, config['arms'][args.arm]
    raw = args.destination
    need(raw.is_absolute() and raw.parent == Path('/dev/shm') and raw.resolve() == raw and
         not raw.exists() and not raw.is_symlink(), 'new direct /dev/shm destination required')
    need(Path('/dev/shm').is_mount() and shutil.disk_usage(raw.parent).free > 2 * 1024**3,
         'actual source-host tmpfs needs at least 2 GiB free')
    raw.mkdir()
    roots = {name + suffix for suffix in ('-archives', '-archive-control')}
    transport = raw / 'transport.tar'
    receipt_path = raw / 'transfer.json'
    receipt = dict(completed=False, started=time.time(), arm=name, boot_id=args.boot_id,
                   kernel=kernel, harness_commit=HARNESS, config_sha256=CONFIG_SHA,
                   expected_sha256=expected, diagnostic_provenance_sha256=args.diagnostic_provenance_sha256, remote_base=REMOTE, roots=sorted(roots),
                   destination=str(raw), script_sha256=sha(__file__),
                   mount_namespace=os.readlink('/proc/self/ns/mnt'),
                   destination_device=raw.stat().st_dev,
                   performance_accepted=False, eligibility_policy=POLICY, offline_analysis_pending=True,
                   scope='Read-only transport and host archive-byte verification; no score validation or guest drain inference')

    def save():
        tmp = receipt_path.with_name('.transfer.json.tmp')
        tmp.write_text(json.dumps(receipt, indent=2) + '\n')
        tmp.replace(receipt_path)

    save()
    remote = shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh', shlex.join(
        ['python3', '-c', GUEST, REMOTE, name, json.dumps(expected), args.boot_id,
         HARNESS, ARCHIVER, CONFIG_SHA, json.dumps(kernel), json.dumps(STEPS), POLICY, args.diagnostic_provenance_sha256, PROVENANCE_HELPER_SHA])])
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'eric@10.176.26.71', remote]
    receipt['argv'] = command
    try:
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
        checked_json(name + '-archive-control/config.json', CONFIG_SHA)
        logical = aliases['logical_steps']
        need(bindings['arm'] == name and bindings['boot_id'] == args.boot_id and bindings.get('schema') == 1 and
             bindings['config']['sha256'] == CONFIG_SHA and bindings['owners'] == owner['step_owners'] and
             aliases['owners'] == owner['step_owners'] and set(logical) == set(STEPS) and
             all(v.get('arm') == name and v.get('boot_id') == args.boot_id and
                 v.get('harness_commit') == HARNESS and v.get('config_sha256') == CONFIG_SHA
                 for v in (owner, aliases, preservation)) and
             owner.get('eligibility_policy') == aliases.get('eligibility_policy') == POLICY,
             'copied bindings/policy identity differs')
        need(sha(CORE) == CORE_SHA and sha(FRESH_CONTROLS) == FRESH_CONTROLS_SHA,
             'reviewed offline archive reader/dependency changed')
        need('nano_core' not in sys.modules and 'fresh_controls' not in sys.modules,
             'offline reader modules already loaded')
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
             parsed.hashes['preservation-inputs/archive-bindings.json'] == owner['bindings_sha256'] and
             parsed.hashes[aliases['config_member']] == CONFIG_SHA and
             parsed.hashes[aliases['harness_manifest_member']] == config['harness']['manifest']['sha256'] and
             parsed.hashes[aliases['diagnostic_manifest_member']] == config['strict_diagnostic']['manifest']['sha256'],
             'archived identity or preserved controls differ')
        provenance_member=aliases['diagnostic_provenance_member']
        need(provenance_member=='preservation-inputs/diagnostic-provenance/record.json' and
             parsed.hashes[provenance_member]==aliases['diagnostic_provenance_sha256']==args.diagnostic_provenance_sha256==owner['diagnostic_provenance']['sha256'], 'preserved diagnostic provenance differs')
        provenance=parsed.json(provenance_member)
        need(owner['diagnostic_provenance_helper_sha256'] == PROVENANCE_HELPER_SHA and
             parsed.hashes.get(aliases['aliases']['/tmp/kdlock-writer-queue-diagnostic-provenance-r2-20261031.py']) == PROVENANCE_HELPER_SHA,
             'preserved diagnostic provenance helper differs')
        need(provenance['schema']==2 and provenance['kind']=='bounded-mm-diagnostic-delta-v2' and
             provenance['arms']['baseline']['config']['sha256']=='b15f6ec4b235e46907978e512b2429906f1bdfa937340ac32f0f9fe76181e602' and
             provenance['arms']['candidate']['config']['sha256']==CONFIG_SHA and provenance['performance_accepted'] is False, 'per-arm diagnostic record differs')
        for reference in [v for arm_refs in provenance['arms'].values() for v in arm_refs.values()]+[*provenance['return_diagnostic'].values(),provenance['compatibility'],provenance['focused_checks'],*provenance['failed_sites'].values(),*provenance['failed_api'].values(),*provenance.get('evidence_files',[])]:
            original=reference['path']; prefix=REMOTE+'/'+name+'/'
            member=original[len(prefix):] if original.startswith(prefix) else aliases['aliases'][original]
            need(parsed.hashes.get(member)==reference['sha256'], 'diagnostic provenance input is not preserved: '+original)
        need(parsed.json(MAP_MEMBER) == preservation and
             parsed.json('preservation-inputs/alias-map.json') == aliases,
             'internal and external map copies differ')
        need(parsed.hashes[parsed.meta['health_path']] == owner['final_health_sha256'],
             'archived final health differs')
        health = parsed.json(parsed.meta['health_path'])
        need(health.get('idle') is True and health.get('boot_id') == args.boot_id and
             health.get('arm') == name and health.get('harness_commit') == HARNESS and
             health.get('kernel') == kernel and health.get('step_owners') == owner['step_owners'] and
             health.get('config_sha256') == CONFIG_SHA and
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
        for step, reference in aliases['owners'].items():
            need(step in STEPS and isinstance(reference, dict) and
                 set(reference) == {'path', 'sha256'}, 'actual logical owner reference differs')
            relative = logical[step]
            need(set(relative) == {'owner', 'result'}, 'logical member fields differ')
            core.safe(relative['owner']); core.safe(relative['result'])
            need(reference['path'] == REMOTE + '/' + name + '/' + relative['owner'] and
                 parsed.hashes.get(relative['owner']) == reference['sha256'],
                 'archived logical step owner differs')
            step_owner = parsed.json(relative['owner'])
            need(step_owner['step'] == step and step_owner['arm'] == name and
                 step_owner['boot_id'] == args.boot_id and step_owner['config_sha256'] == CONFIG_SHA and
                 step_owner.get('completed') is True and step_owner.get('passed') is True and
                 step_owner.get('drained') is True and step_owner.get('final_idle') is True and
                 step_owner.get('drain_unknown') is False and step_owner.get('state') == 'COMPLETE' and
                 step_owner['result']['path'] == REMOTE + '/' + name + '/' + relative['result'] and
                 parsed.hashes.get(relative['result']) == step_owner['result']['sha256'],
                 'archived logical step result differs')
        need(set(aliases['owners']) == set(STEPS), 'all nine step owners required')
        measure = parsed.json(logical['mmap1-measure']['owner'])
        policy_member = aliases['measurement_policy_member']; core.safe(policy_member)
        need(measure['measurement_policy']['path'] == REMOTE + '/' + name + '/' + policy_member and
             parsed.hashes.get(policy_member) == measure['measurement_policy']['sha256'],
             'prospective measurement policy bytes differ')
        bundle = parsed.json(BUNDLE_MEMBER)
        need(bundle['variant'] == kernel['variant'] and bundle['runtime_policy']['mmap_mode'] == 'on',
             'archived KD bundle differs')
        arm = dict(archives=str(raw / (name + '-archives')), archives_sha256=expected['archive'],
                   control=str(raw / (name + '-archive-control')),
                   archive_owner_sha256=expected['archive-owner'], expected_sha256=expected,
                   bundle_member=BUNDLE_MEMBER, owners=aliases['owners'], aliases=aliases['aliases'],
                   logical_steps=logical, eligibility_policy=POLICY, config_sha256=CONFIG_SHA,
                   diagnostic_provenance_member=provenance_member, diagnostic_provenance_sha256=args.diagnostic_provenance_sha256,
                   config_member=aliases['config_member'],
                   harness_manifest_member=aliases['harness_manifest_member'],
                   diagnostic_manifest_member=aliases['diagnostic_manifest_member'],
                   measurement_policy_member=policy_member,
                   measurement_policy_sha256=measure['measurement_policy']['sha256'])
        for leaf, value in (('member-sha256.json', parsed.hashes),
                            ('archive-provenance.json', parsed.provenance), ('analysis-arm.json', arm)):
            (raw / leaf).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
        receipt.update(files=files, group_archives=len(metadata['groups']),
                       regular_members=len(parsed.hashes),
                       member_manifest_sha256=sha(raw / 'member-sha256.json'),
                       archive_provenance_sha256=sha(raw / 'archive-provenance.json'),
                       offline_reader_sha256=CORE_SHA, offline_reader_dependency_sha256=FRESH_CONTROLS_SHA,
                       analysis_arm_sha256=sha(raw / 'analysis-arm.json'),
                       transport_verified=True, archive_members_verified=True)
        save()
        shutil.rmtree(cache)
        transport.unlink()
        receipt.update(completed=True, finished=time.time(), transport_intermediate_removed=True,
                       removal_scope='Only verified task-created transport.tar and derived receipt-cache; original compressed groups/control retained')
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        save()
    print(json.dumps({key: receipt[key] for key in
                      ('completed', 'transport_bytes', 'transport_sha256', 'group_archives', 'analysis_arm_sha256')}))


if __name__ == '__main__':
    main()
