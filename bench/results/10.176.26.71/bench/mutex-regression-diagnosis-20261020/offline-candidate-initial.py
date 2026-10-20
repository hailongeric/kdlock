#!/usr/bin/env python3
"""Inert source-host audit of the isolated provider's archives and derivation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo/'bench/results/10.176.26.71'
    raw = root/'raw/bench/mutex-public-20261020-inline-inputs-1'
    old_raw = root/'raw/bench/mutex-public-20261020-r2'
    helper = root/'bench/mutex32-native-tclock-20261020/offline-review.py'
    sha = lambda data: hashlib.sha256(data).hexdigest()
    assert sha(helper.read_bytes()) == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('archive_audit', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    a = module.Audit(SimpleNamespace(repo=repo, raw=raw, report=args.report))
    groups, links = a.load_archives()
    a.manifests()
    original_archives = json.loads((old_raw/'archives.json').read_text())
    a.check(module.hashfile(old_raw/'archives.json') ==
            '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4',
            'original_archives_manifest')
    originals = {}
    for group in original_archives['groups']:
        if group['group'] not in ('current', 'metadata'):
            continue
        archive = old_raw/group['file']
        a.check(module.hashfile(archive) == group['sha256'], 'original_archive_hash', group['group'])
        with tarfile.open(archive) as stream:
            for member in stream:
                if member.isfile() and (member.name.endswith('/frozen-inputs.json')
                        or member.name.endswith('/source-sha256.json')
                        or member.name.endswith('/provider/manifest.json')):
                    originals[member.name.removeprefix('mutex-public-20261020-r2/')] = stream.extractfile(member).read()
    frozen = json.loads(originals['frozen-inputs.json'])
    c = a.jread('candidate.json')
    a.check(sha(a.contents['candidate.json']) ==
            'd8b5b56daa3110cf3e276ca8c2198c2b05eda1bd79630210142163f57bc8f9ac',
            'candidate_manifest')
    entry = 'kernel_module/lock/mutex_calls.inc'
    overlay = 'bench/spin_cacheline/.build/provider/'
    new_hash = sha(a.git_bytes(a.revision('003d71c'), entry))
    a.check(c['complete'] and c['patch_commit'] == a.revision('003d71c')
            and c['kind'] == 'd21-plus-entry-inline', 'candidate_recipe')
    for retained, source in [('entry_candidate.py', 'bench/mutex_api_compare/entry_candidate.py'),
                             ('scheduler.py', 'bench/mutex_api_compare/run.py')]:
        a.check(a.files[retained] == sha(a.git_bytes(a.revision('d1a976a'), source)),
                'driver_git_binding', retained)
    a.check(c['preparer_sha256'] == a.files['entry_candidate.py'], 'preparer_binding')
    for path, digest in c['immutable_files'].items():
        a.check(a.files.get(path) == digest, 'immutable_input', path)
    common = a.jread('original-provider-inputs.json')
    prepared = a.jread('provider/manifest.json')
    changes = a.reconstruct('provider-inputs/',
                            a.contents['provider-inputs/bench/spin_cacheline/provider/observation.patch'])
    for path, digest in common.items():
        a.check(a.files['provider-inputs/'+path] == (new_hash if path == entry else digest),
                'raw_provider_derivation', path)
    for path, digest in prepared['prepared'].items():
        if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
            expected = a.contents['provider-inputs/bench/spin_cacheline/provider/'+Path(path).name]
        elif path in changes:
            expected = changes[path]
        else:
            expected = a.contents['provider-inputs/'+path]
        a.check(a.files['provider/'+path] == digest == sha(expected),
                'prepared_provider_reconstruction', path)
    summaries = []
    for group in ('c08', 'rcuht', 'pipebytes', 'pipecap'):
        key = 'current/'+group
        original = frozen[key]
        old_prefix = original['bundle']+'/'
        original_source_bytes = originals[key+'/source-sha256.json']
        a.check(sha(original_source_bytes) == original['files'][old_prefix+'source-sha256.json'],
                'original_source_map_binding', group)
        before = json.loads(original_source_bytes)
        prefix = 'candidate-public/'+group+'/'
        after = a.jread(prefix+'source-sha256.json')
        a.check(set(before) == set(after), 'derived_path_set', group)
        expected_changes = {entry}
        if overlay+entry in before:
            expected_changes |= {overlay+entry, overlay+'manifest.json'}
            old_manifest = json.loads(originals[key+'/source/'+overlay+'manifest.json'])
            for field in ('production', 'prepared'):
                old_manifest[field][entry] = new_hash
            a.check(old_manifest == prepared, 'prepared_manifest_only_entry_changed', group)
        a.check({p for p in before if before[p] != after[p]} == expected_changes,
                'exact_source_delta', group)
        for path, digest in after.items():
            expected = (new_hash if path in (entry, overlay+entry)
                        else a.files['provider/manifest.json'] if path == overlay+'manifest.json'
                        else before[path])
            a.check(a.files[prefix+'source/'+path] == digest == expected,
                    'derived_source_bytes', [group, path])
        identity = sha(json.dumps(after, sort_keys=True).encode())
        bundle = c['bundles']['candidate-public/'+group]
        a.check(identity == bundle['source_identity'], 'distinct_source_identity', group)
        binaries = a.jread(prefix+'candidate-binaries.json')
        expected_set = {p.removeprefix(old_prefix) for p in original['files']
                        if '/source/' not in p and (p.endswith('.ko') or Path(p).name in ('client', 'daemon'))}
        a.check(set(binaries) == expected_set, 'retained_binary_set', group)
        for path, row in binaries.items():
            old_hash = original['files'][old_prefix+path]
            expected = c['provider_sha256'] if Path(path).name == 'kdlock_km.ko' else old_hash
            a.check(row['original'] == old_prefix+path and row['original_sha256'] == old_hash
                    and a.files[prefix+path] == row['sha256'] == expected,
                    'provider_only_binary_change', [group, path])
        summaries.append(dict(group=group, source_identity=identity, changed=sorted(expected_changes),
                              binaries=len(binaries)))
    a.check(a.files['provider/kernel_module/kdlock_km.ko'] == c['provider_sha256'],
            'provider_elf_binding')
    a.check(a.jread('state.json')['state'] == 'COMPLETE' and a.jread('health.json')['idle'],
            'completed_preparation_idle')
    record = dict(consistent=not a.issues, issues=a.issues, checks=sum(a.counts.values()),
                  check_counts=dict(a.counts), members=len(a.members), symlinks=len(links),
                  groups=groups, bundles=summaries, provider_sha256=c['provider_sha256'],
                  archives_manifest_sha256=module.hashfile(raw/'archives.json'),
                  script_sha256=sha(Path(__file__).read_bytes()))
    args.report.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: record[k] for k in ('consistent', 'issues', 'checks',
                                            'archives_manifest_sha256')}))


if __name__ == '__main__':
    main()
