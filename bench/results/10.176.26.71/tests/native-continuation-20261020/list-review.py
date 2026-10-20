#!/usr/bin/env python3
"""Read inert resident-list archives and Git blobs; never import archived code."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True


def review(repo, raw):
    helper = repo/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == \
        '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('inert_archive_reader', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audit = module.Audit(SimpleNamespace(repo=repo, raw=raw, report=Path('/tmp/unused-report')))
    groups, links = audit.load_archives()
    sources, binaries = audit.manifests()
    manifest = audit.jread('committed-source.json')
    tasks = audit.jread('tasks.json')
    revision = audit.revision(manifest['commit'])
    paths = audit.names(revision)
    for path, digest in manifest['files'].items():
        audit.check(path in paths and module.sha(audit.git_bytes(revision, path)) == digest,
                    'committed_source_git_hash', path)
    audit.check(tasks['source_commit'] == revision and
                module.sha(audit.contents['run-tasks.py']) == tasks['script_sha256'],
                'supervisor_binding')
    cases = []
    for task in tasks['tasks']:
        name = task['name']
        original = name+'/source/'
        source = audit.jread(name+'/source-sha256.json')
        overlay = 'bench/spin_cacheline/.build/provider/'
        extra = {p: h for p, h in source.items() if p not in manifest['files']}
        for path, digest in source.items():
            if path not in extra:
                audit.check(manifest['files'].get(path) == digest, 'source_commit_binding', name+'/'+path)
        if extra:
            generated = audit.jread(original+overlay+'manifest.json')
            expected = {overlay+p: h for p, h in generated['prepared'].items()}
            expected[overlay+'manifest.json'] = audit.files[original+overlay+'manifest.json']
            audit.check(extra == expected and generated['complete'], 'exact_generated_set', name)
            changes = audit.reconstruct(original,
                audit.contents[original+'bench/spin_cacheline/provider/observation.patch'])
            for path, digest in generated['prepared'].items():
                if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
                    data = audit.contents[original+'bench/spin_cacheline/provider/'+Path(path).name]
                else:
                    data = changes.get(path, audit.contents.get(original+path))
                audit.check(data is not None and module.sha(data) == digest,
                            'prepared_reconstructed_hash', name+'/'+path)
            for category, prefix in (('production', original),
                                    ('observation', original+'bench/spin_cacheline/provider/')):
                for path, digest in generated[category].items():
                    audit.check(audit.files.get(prefix+path) == digest,
                                'generated_'+category+'_binding', name+'/'+path)
        for planned in audit.jread(name+'/plan.json'):
            prefix = name+'/'+planned['name']+'/'
            session = audit.jread(prefix+'session.json')
            audit.check(session['name'] == planned['name'] and session['drained'] and
                        session['retired'] == dict(state=2, modules=0, frames=0, writers=0)
                        and not session.get('cleanup_error'), 'exact_retirement', prefix)
            status = session['execution_status']
            audit.check(status in ('OK', 'PREPARATION_FAILED') and
                        (task['exit_code'] == 0) == (status == 'OK'), 'retained_outcome', prefix)
            if status == 'OK':
                measurement = session['measurement']
                audit.check(session['functional'] and session['duration_ms'] == 0 and
                            measurement['complete'] and measurement['data_ok'] and
                            measurement['list_integrity_ok'], 'list_business_validation', prefix)
                audit.check(session['jit_bodies'] == session['jit_completions'] > 0,
                            'positive_returned_bodies', prefix)
                workers = measurement['workers']
                audit.check(len(workers) == session['threads'] and
                            [w['cpu'] for w in workers] == session['cpus'] and
                            all(w['completed'] == session['iterations'] and w['error'] == 0
                                and w['cpu'] == w['observed_cpu'] for w in workers) and
                            sum(w['completed'] for w in workers) == measurement['completed'],
                            'exact_worker_progress', prefix)
                for publication in ('published_before', 'published_after'):
                    for filename, digest in session.get(publication, {}).get('images', {}).items():
                        matches = [p for p in audit.files
                                   if p.startswith(prefix) and p.endswith('/'+filename)]
                        audit.check(len(matches) == 1 and audit.files[matches[0]] == digest,
                                    'published_image_hash', prefix+filename)
            else:
                audit.check('measurement' not in session and 'jit_bodies' not in session,
                            'refused_preparation_not_execution', prefix)
            cases.append(dict(task=name, name=planned['name'], status=status, drained=True,
                              entries=session.get('jit_bodies'),
                              completions=session.get('jit_completions')))
    health = audit.jread('health.json')
    audit.check(health['idle'] and not health['per_session_kernel_faults'] and
                health['boot_id'] == tasks['boot_id'] == audit.archive['boot_id'],
                'independent_health_identity')
    return dict(scope='Archive consistency; preserves failures and original supervisor status.',
                consistent=not audit.issues, issues=audit.issues, source_commit=revision,
                checks=sum(audit.counts.values()), check_counts=dict(audit.counts), cases=cases,
                groups=groups, members=len(audit.members), symlinks=len(links),
                binary_entries=len(binaries), sources=sources,
                archives_manifest_sha256=module.hashfile(raw/'archives.json'),
                regular_file_hash_map_sha256=module.canonical(audit.files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    args = parser.parse_args()
    receipt = review(args.repo, args.raw)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt['consistent'] else 1)
