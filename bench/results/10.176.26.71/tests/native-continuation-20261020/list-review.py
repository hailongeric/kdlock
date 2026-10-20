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
        prepared_manifest = name+'/prepared-source-sha256.json'
        if prepared_manifest in audit.files:
            changes = audit.reconstruct(original,
                audit.contents[original+'bench/spin_cacheline/provider/observation.patch'])
            for path, digest in audit.jread(prepared_manifest).items():
                if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
                    data = audit.contents[original+'bench/spin_cacheline/provider/'+Path(path).name]
                else:
                    data = changes.get(path, audit.contents.get(original+path))
                audit.check(data is not None and module.sha(data) == digest,
                            'prepared_reconstructed_hash', name+'/'+path)
        for planned in audit.jread(name+'/plan.json'):
            prefix = name+'/'+planned['name']+'/'
            session = audit.jread(prefix+'session.json')
            retired = session.get('retired')
            if not session['drained']:
                later = audit.jread('post-failure-drain.json')
                audit.check(session['execution_status'] == 'PREPARATION_FAILED' and
                            session['cleanup_error'] == 'translator has not exited' and
                            later['complete'] and later['final_idle'] and
                            later['counts']['active'] == 0 and
                            later['before_retire']['frames'] == later['before_retire']['writers'] == 0,
                            'separate_post_failure_drain', prefix)
                retired = later['retired']
            else:
                audit.check(not session.get('cleanup_error'), 'original_cleanup_success', prefix)
            audit.check(session['name'] == planned['name'] and
                        retired == dict(state=2, modules=0, frames=0, writers=0),
                        'exact_retirement', prefix)
            status = session['execution_status']
            audit.check(status in ('OK', 'PREPARATION_FAILED') and
                        (task['exit_code'] == 0) == (status == 'OK'), 'retained_outcome', prefix)
            if status == 'OK':
                measurement = session['measurement']
                shared = session['lock_kind'] in ('rwlock', 'rwsem')
                audit.check(session['functional'] and session['duration_ms'] == 0 and
                            measurement['complete'] and measurement['data_ok'],
                            'list_business_validation', prefix)
                if not shared:
                    audit.check(measurement['list_integrity_ok'], 'list_integrity', prefix)
                audit.check(session['jit_bodies'] == session['jit_completions'] > 0,
                            'positive_returned_bodies', prefix)
                workers = measurement['workers']
                audit.check(len(workers) == session['threads'] and
                            [w['cpu'] for w in workers] == session['cpus'] and
                            all(w['completed'] == session['iterations'] and w['error'] in (0, None)
                                and w['cpu'] == w['observed_cpu'] for w in workers) and
                            sum(w['completed'] for w in workers) == measurement['completed'],
                            'exact_worker_progress', prefix)
                if shared:
                    for index, worker in enumerate(workers):
                        writes = ((index*17) % 100 + worker['completed']*session['write_percent']) // 100
                        audit.check(worker['writes'] == writes and worker['read_errors'] == 0 and
                                    worker['read_hits'] == 0 and
                                    worker['reads'] + writes == worker['completed'],
                                    'exact_mixed_operations', prefix+str(index))
                    before, after = measurement['before'], measurement['after']
                    audit.check(all(snapshot[k] == 0 for snapshot in (before, after)
                                    for k in ('active', 'cnts', 'gate')) and
                                [a-b for a, b in zip(after['values'], before['values'])] ==
                                [measurement['writes']] + [0]*15 and
                                measurement['writes'] == sum(w['writes'] for w in workers) and
                                measurement['reads'] == sum(w['reads'] for w in workers),
                                'mixed_business_effects_and_drain', prefix)
                image = session['list_image_audit']
                audit.check(image['byte_for_byte_match'] and
                            image['loaded_sha256'] == image['uploaded_sha256'] ==
                            audit.files[prefix+'list-image/loaded.bin'] and
                            image['prefetch'] == (session['workload'] == 'list-prefetch') and
                            bool(image['hints']) == image['prefetch'] and
                            all(h['mnemonic'] in ('prefetchnta', 'prefetcht0', 'prefetcht1', 'prefetcht2')
                                for h in image['hints']), 'loaded_list_image_and_hints', prefix)
                for publication in ('published_before', 'published_after'):
                    published = session[publication]
                    entry = published['entry']
                    workspace = prefix+'workspace/daemon/'+hex(entry['entry'])+'/'+str(entry['tgid'])+'/asm/'
                    for filename, digest in published['images'].items():
                        audit.check(audit.files.get(workspace+filename) == digest,
                                    'published_image_hash', prefix+filename)
                for publication in session.get('publications', []):
                    path = publication['path']
                    audit.check(module.safe_relative(path), 'publication_history_path', prefix+path)
                    for filename, digest in publication['images'].items():
                        audit.check(audit.files.get(prefix+path+'/'+filename) == digest,
                                    'publication_history_hash', prefix+path+'/'+filename)
            else:
                audit.check('measurement' not in session and 'jit_bodies' not in session,
                            'refused_preparation_not_execution', prefix)
            cases.append(dict(task=name, name=planned['name'], status=status,
                              original_drained=session['drained'], independent_retirement=retired,
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
