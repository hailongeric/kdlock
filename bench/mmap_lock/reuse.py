#!/usr/bin/env python3
"""Verify the one completed Native control set; never run or relabel old work."""
import argparse
import json
from pathlib import Path

import paired

rt, eligibility, window = paired.rt, paired.eligibility, paired.window
RULES = Path(__file__).with_name('reuse_native_v1.json')
ORIGIN = Path('/root/host_fs/kdlock')
VERSION = 'native-controls-compat-v1'
CHANGED = {'bench/mmap_writer/client.c', 'bench/mmap_lock/paired.py',
           'bench/mmap_lock/prepare.py', 'bench/mmap_lock/report.py',
           'tests/kernel/mmap_writer/run.py', 'tests/kernel/mmap_lock/mapping.py'}
ADDED = {'bench/mmap_lock/eligibility.py', 'bench/mmap_lock/reuse.py'}


def source_maps(rules, prior_source):
    """Bind both source versions; a filename allowlist alone is insufficient."""
    old = {str(prior_source / name): digest for name, digest in rules['sources'].items()}
    paired.common.verify_maps(old)
    target = {str(Path(name).relative_to(paired.ROOT)): digest
              for name, digest in paired.control_files().items()}
    reviewed = rules['target_sources']
    rt.require(set(reviewed) == CHANGED | ADDED, 'compatibility review source set differs')
    expected = dict(rules['control_sources'], **reviewed)
    expected['bench/mmap_lock/reuse_native_v1.json'] = rt.digest(RULES)
    rt.require(target == expected, 'unreviewed target control source difference')
    # Payload source and Makefile are prepared inputs outside control_files().
    for name, digest in rules['sources'].items():
        actual = rt.digest(paired.ROOT / name)
        rt.require(actual == reviewed.get(name, digest), 'unreviewed workload source: ' + name)
        target[name] = actual
    return old, target


def preparation(old_ref, target_path, rules, prior_source):
    old_path = paired.file_bound(old_ref)
    rt.require(old_ref['sha256'] == rules['prepared_sha256'], 'original preparation differs')
    old = paired.common.load(old_path)
    rt.require(old['passed'] and old['built_only'] and not old['modules_loaded'] and
               old['profile'] == paired.PROFILE, 'original build identity differs')
    saved = {}
    for name, digest in old['files'].items():
        path = Path(name)
        if path.is_relative_to(ORIGIN):
            rel = str(path.relative_to(ORIGIN))
            rt.require(rules['sources'].get(rel) == digest, 'original source manifest differs')
            path = prior_source / rel
        saved[str(path)] = digest
    paired.common.verify_maps(saved)
    target = paired.prepared(target_path)
    rt.require(target.get('fixed_eligibility_policy') == eligibility.FUNCTIONAL and
               target.get('reused_from') == old_ref and target.get('client_only') is True and
               target.get('reused_payload') is True and target.get('booted') is False and
               target.get('prior_source') == str(prior_source) and
               target['driver_sha256'] == rules['target_sources']['bench/mmap_lock/prepare.py'],
               'reviewed fixed-client-only preparation required')
    rt.require(set(target['binaries']) == {'fixed', 'timed', 'payload'}, 'binary set differs')
    for kind in ('payload', 'timed'):
        name = old['binaries'][kind]
        rt.require(target['binaries'][kind] == name and
                   target['files'][name] == old['files'][name], 'reused ' + kind + ' differs')
    fixed = Path(target['binaries']['fixed'])
    rt.require(fixed == target_path.parent / 'fixed', 'new fixed client location differs')
    expected = dict(saved)
    for rel in ('bench/mmap_writer/client.c', 'bench/mmap_writer/control.h',
                'workload_modules/mmap_writer/mmap_writer_uapi.h'):
        digest = rules['target_sources'].get(rel, rules['sources'][rel])
        expected[str(target_path.parent / 'source' / rel)] = digest
    expected[str(fixed)] = rt.digest(fixed)
    expected[str(old_path)] = old_ref['sha256']
    rt.require(target['files'] == expected, 'preparation changed more than fixed client inputs')
    manifest = target_path.parent / 'source-manifest.json'
    rt.require(rt.digest(manifest) == target['source_manifest_sha256'], 'new build source manifest differs')
    manifest = paired.common.load(manifest)['files']
    rt.require(all(manifest[name] == rt.digest(paired.ROOT / name) for name in
                   ('bench/mmap_writer/client.c', 'bench/mmap_writer/control.h',
                    'workload_modules/mmap_writer/mmap_writer_uapi.h')), 'compiled source differs')
    return target


def create(prior, target, prior_source):
    """Recompute every verdict from retained bytes, without live kernel checks."""
    prior, target, prior_source = prior.resolve(), target.resolve(), prior_source.resolve()
    rules = paired.common.load(RULES)
    rt.require(rt.digest(prior) == rules['validation_sha256'], 'only the completed Native receipt is reusable')
    original = paired.common.load(prior)
    rt.require('compatibility' not in original and eligibility.policy(original) == eligibility.STRICT,
               'original strict execution required')
    old_sources, target_sources = source_maps(rules, prior_source)
    preparation(original['prepared'], target, rules, prior_source)
    original = paired.validation_receipt(prior, 'native', original['prepared'], paired.SCALING_PLAN)
    ready = paired.load_bound(original['ready'])
    rt.require(ready['files'] == {str(ORIGIN / n): h for n, h in rules['control_sources'].items()} and
               ready['kernel_identity']['running_build_id'] == paired.PROFILE['build_id'],
               'original readiness source/kernel differs')
    for mode, binding in zip(('native', 'kd'), ready['prior_api'], strict=True):
        rt.require(binding['sha256'] == paired.PROFILE['prior_api'][mode]['sha256'], 'prior API binding differs')
        paired.load_bound(binding)
    rt.require(window.policy(original) == window.POLICY and
               window.admission_policy(original) == window.WORKER_ADMISSION,
               'original measurement/admission policy differs')
    rt.require(all(original.get(k) == ready.get(k) == v for k, v in window.binding().items()),
               'window implementation changed')
    paired.ready_roles(ready)
    return dict(passed=True, drained=True, accepted=False, mode='native', plan=paired.SCALING_PLAN,
        prepared=paired.bind(target), eligibility_policy=eligibility.FUNCTIONAL,
        writer_observation='observed', **window.binding(), **window.admission_fields(original),
        compatibility=dict(version=VERSION, original=paired.bind(prior), rules=paired.bind(RULES),
            importer=paired.bind(Path(__file__)), prior_source=str(prior_source),
            original_sources=old_sources, target_sources=target_sources,
            original_ready=original['ready'], original_prepared=original['prepared'],
            fixed_raw=original['fixed_raw'], timed_raw=[c['raw'] for c in original['cases']],
            source_commit=rules['source_commit'], controls=21,
            claim='Verified reuse of original unscored controls; no new execution or live readiness.'))


def replay(path, mode, prepared_ref, plan):
    row = paired.common.load(path)
    rt.require(mode == 'native' and plan == paired.SCALING_PLAN and row['prepared'] == prepared_ref,
               'compatibility target scope differs')
    compat = row['compatibility']
    for key, current in (('rules', RULES), ('importer', Path(__file__))):
        paired.file_bound(compat[key])
        rt.require(compat[key]['sha256'] == rt.digest(current), 'running compatibility implementation differs')
    expected = create(paired.file_bound(compat['original']), paired.file_bound(prepared_ref),
                      Path(compat['prior_source']))
    # Identical reviewed code may be synchronized from a private build snapshot
    # to the maintained checkout. Keep its original provenance paths; both the
    # retained files and the executing implementation must still match by hash.
    for key in ('rules', 'importer'):
        expected['compatibility'][key] = compat[key]
    rt.require(row == expected, 'compatibility receipt differs from replay')
    return row


def match_ready(row, ready):
    """Old controls never supply the new boot, host admission or endpoints."""
    if 'compatibility' not in row:
        return
    old = paired.load_bound(row['compatibility']['original_ready'])
    rt.require(eligibility.policy(ready) == eligibility.FUNCTIONAL and ready['passed'] and
               ready['prepared'] == row['prepared'] and paired.row_plan(ready) == paired.SCALING_PLAN and
               window.policy(ready) == window.POLICY and
               window.admission_policy(ready) == window.WORKER_ADMISSION and
               ready['topology'] == old['topology'] and
               ready['window_roles'] == old['window_roles'] and ready['prior_api'] == old['prior_api'] and
               ready['kernel_identity']['running_build_id'] == paired.PROFILE['build_id'],
               'new readiness is incompatible with reused controls')
    env = dict(old['environment'])
    env.update(boot_id=ready['boot_id'], cmdline=' '.join(paired.PROFILE['cmdline_common'] +
               ['kd_mmap=' + paired.PROFILE['modes'][ready['mode']]]))
    rt.require(ready['boot_id'] != old['boot_id'] and ready['environment'] == env,
               'fresh boot or compatible environment missing')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', required=True, type=Path)
    p.add_argument('--prepared', required=True, type=Path)
    p.add_argument('--prior-source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    rt.require(not a.output.exists() and not a.output.resolve().is_relative_to(paired.ROOT),
               'new private compatibility receipt required')
    row = create(a.original, a.prepared, a.prior_source)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as output:
        json.dump(row, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(dict(passed=True, controls=21, executed=False, output=str(a.output))))


if __name__ == '__main__':
    main()
