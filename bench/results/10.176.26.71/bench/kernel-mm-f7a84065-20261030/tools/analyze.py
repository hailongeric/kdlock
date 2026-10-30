#!/usr/bin/env python3
"""Compare completed f7 MM receipt caches offline; never starts guest work."""
import argparse
import ast
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys
import tarfile
from types import SimpleNamespace

sys.dont_write_bytecode = True
COMMIT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
RECIPE = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
CAMPAIGN = '/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-mm-f7a84065-20261030'
SOURCE_ROOT = '/root/host_fs/kdlock/'
CORE_SHA = '1bbd6e010c27c42f5293a3df09660342e453d49663d9452e3c1d02269116c3a7'
SOURCE_SHA = 'f093746333abdc7e3ca647852b43b611d6a0a494e7922b9c285125dd46c00db3'
STATE_SHA = '52448d33d2ed7c781b0bea4cd1ac4ab80b59107a42622a4fc8a0fd9d857fd520'
GENERATION_SHA = '4618cd0df915928562e94569662a3771483a86cdc26f4762f276190d8ee88567'
IDENTITY_RUNNER = '/tmp/kdlock-scope-mmap1-identity-runner-r1-20261030.py'
IDENTITY_RUNNER_SHA = '5c23db457fc9cfc91ff68c7f392e5c003812cb54a66fe082a0e73a0b459b6120'
IDENTITY_COMMIT = 'd22a36567de28c024ebb8d1c79997c0d39541bd2'
IDENTITY_MAINTAINED_SHA = '70f256264db17e60ebcfe5187595f5f403ed3d1f7cbab3e6a873410640311f37'
IDENTITY_FROZEN_SHA = '39abca1536cae7d1ea325fa91a5cf6e95e96fed58d2ab056da080c8681e83d43'
REFERENCE_SHA = '95199f8417b1eb8a0e7a406fa1143dec17090aa0973c6db3d0ae828e401ed588'
BUILD_ID = 'a17d565ee157601e030d1b3c77c13e63fa62c994'
REVISION = '75f66e45697e6f5f49c33dd950c4e6b289198f8f'
UPSTREAM_PINNED = {
    'main.c': '48d4640f151801fdfb5f3915c822cf280c713df3c1998068e16ce0c961cbf746',
    'Makefile': '9089726b38440a6466ebd0ea7561b3fd99ee263fea2485f974fbd91f4866d5a8',
    'tests/mmap1.c': 'a7e09c6a7a12524a2cd949e5d37cf8ec0ba2479868cbd04ebd8c83c4eaed9d06',
}
WORKERS = (*range(1, 9), *range(12, 61, 4))
MODELS = ('threads', 'processes')
CHECKS = ('api', 'mapping', 'faults', 'completed')
VALIDATORS = {
    'bench/spin_cacheline/peak.py': 'fa90dc91b33c7a52b99168565baad0b210d56e2005cd615047d939414c596ad2',
    'bench/mmap_writer/timing.py': '6ba11b0f284f89ed213916cd7f8b05df27753460daf50081c51cf4f5b3ea2b3a',
    'bench/mmap_writer/linux70.py': '3ac744ab4d606da5284c384d272de73e09ead8cdd2fc5ca444b58589318860ad',
    'bench/mmap1/run.py': '863c4aa07eda2324dba6a14c3b811b571a4f72c561ce4c162e559af91b114410',
}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    temporary = path.with_name('.'+path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    temporary.replace(path)


class Cache:
    """Consume the existing generic Archive verification, without duplicating it."""
    def __init__(self, label, entry):
        self.label, self.raw = label, Path(entry['raw']).resolve()
        need(sha(self.raw/'transfer.json') == entry['transfer_sha256'], 'actual transfer differs: '+label)
        self.transfer = t = read(self.raw/'transfer.json')
        need(t.get('completed') is True and t.get('source_commit') == COMMIT and
             t.get('kernel_project_commit') == RECIPE and t.get('label') == label and
             t.get('offline_reader_sha256') == CORE_SHA and t.get('performance_accepted') is False,
             'generic Archive verification missing: '+label)
        self.directory = self.raw/(label+'-archives')
        for name, expected in [('archives.json', t['archives_sha256']),
                               ('input-inventory.json', t['input_inventory_sha256'])]:
            need(sha(self.directory/name) == expected, 'archive metadata differs: '+label+'/'+name)
        self.meta, inventory = read(self.directory/'archives.json'), read(self.directory/'input-inventory.json')
        need(self.meta.get('completed') is True and self.meta.get('guest_idle') is True and
             self.meta.get('guest_base') == CAMPAIGN+'/'+label and self.meta.get('boot_id') == t['boot_id'],
             'archive identity/completion differs: '+label)
        self.boot = t['boot_id']
        self.owner = read(self.raw/(label+'-archive-control')/'owner.json')
        need(sha(self.raw/(label+'-archive-control')/'owner.json') == t['archive_owner_sha256'] and
             self.owner.get('completed') is True and self.owner.get('state') == 'COMPLETE' and
             self.owner.get('idle') is True and self.owner.get('drain_unknown') is False and
             self.owner.get('boot_id') == self.boot and self.owner.get('source_commit') == COMMIT and
             self.owner.get('archives_sha256') == t['archives_sha256'], 'archive owner differs: '+label)
        for row in self.meta['groups']:
            path = self.directory/row['file']
            need(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'archive group changed: '+str(path))
        need(sha(self.raw/'member-sha256.json') == t['member_sha256_manifest'], 'verified member map differs')
        self.hashes = read(self.raw/'member-sha256.json')
        regular = {name for name, row in inventory.items() if stat.S_ISREG(row['mode'])}
        need(set(self.hashes) == regular and len(regular) == t['regular_members'], 'verified regular member coverage differs')
        # The Archive flat-cache numbering is deliberately not a persistent ABI.
        # Address retained bytes by their verified digest instead of that number.
        self.cached = {}
        for path in (self.raw/'receipt-cache').iterdir():
            need(path.is_file() and not path.is_symlink(), 'unexpected cached object')
            self.cached[sha(path)] = path
        self.extra = {}
        self.preservation = self.json('preservation-inputs/preservation-map.json')
        self.aliases = {row['source']: row['target'] for row in self.preservation['files']}
        for row in self.preservation['files']:
            need(self.hashes[row['target']] == row['sha256'], 'preserved file binding differs')
        for tree in self.json('boot-evidence/copy-map.json')['trees']:
            for name, row in tree['files'].items():
                if row['kind'] == 'file':
                    member = tree['target']+'/'+name
                    need(self.hashes[member] == row['sha256'], 'preserved boot tree differs')
                    self.aliases[tree['source']+'/'+name] = member
        health = self.json(self.meta['health_path'])
        need(self.hashes[self.meta['health_path']] == self.meta['health_sha256'] == self.owner['final_health_sha256'] and
             health.get('idle') is True and health.get('boot_id') == self.boot and
             not health.get('new_faults_in_retained_dmesg', []) and not health.get('per_session_kernel_faults', []),
             'final health differs: '+label)

    def data(self, name):
        expected = self.hashes[name]
        if name in self.extra:
            value = self.extra[name]
        else:
            need(expected in self.cached, 'receipt not retained in verified cache: '+name)
            value = self.cached[expected].read_bytes()
        need(hashlib.sha256(value).hexdigest() == expected, 'retained bytes changed: '+name)
        return value

    def json(self, name):
        return json.loads(self.data(name))

    def logs(self, wanted):
        """Read only original score inputs; never execute archived source."""
        remaining = set(wanted)
        prefix = self.meta['archive_prefix']+'/'
        for group in self.meta['groups']:
            with tarfile.open(self.directory/group['file'], 'r|gz') as stream:
                for item in stream:
                    name = item.name.removeprefix(prefix)
                    if name in remaining:
                        need(item.isfile() and item.size <= 8*1024*1024, 'unexpected client log')
                        self.extra[name] = stream.extractfile(item).read()
                        self.data(name)
                        remaining.remove(name)
        need(not remaining, 'missing original score log: '+repr(remaining))


def pure(source, name, functions, **namespace):
    path = source/name
    need(sha(path) == VALIDATORS[name], 'fixed pure-validator source differs: '+name)
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in functions]
    need({n.name for n in nodes} == set(functions), 'pure validator missing')
    # Only these explicitly selected, hash-bound pure functions are evaluated.
    # No runner import, top-level code, test, build or subprocess is executed.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def image(binding):
    return {key: binding[key] for key in ('release', 'build_id', 'configuration_sha256', 'source_files', 'build_files')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--inputs-sha256', required=True)
    p.add_argument('--scope', choices=('localized', 'all'), default='all')
    p.add_argument('--source', type=Path, default=Path('/tmp/kdlock-continuation-perf-20261030'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    need(sha(args.inputs) == args.inputs_sha256, 'actual input record differs')
    selected = read(args.inputs)
    labels = ('native-a', 'kd', 'native-b') + (('kd-b',) if args.scope == 'all' else ())
    need(selected.get('schema') == 1 and set(selected['boots']) == set(labels), 'exact completed boot inputs required')
    out = args.output.resolve()
    need(not out.exists() and all(not out.is_relative_to(Path(x['raw']).resolve()) for x in selected['boots'].values()),
         'new output separate from preserved raw evidence required')
    out.mkdir(parents=True)
    receipt = dict(schema=1, completed=False, validated=False, performance_accepted=False,
                   source_commit=COMMIT, kernel_project_commit=RECIPE, scope=args.scope,
                   inputs_sha256=args.inputs_sha256, script_sha256=sha(__file__), limitations=[
                       'One round per point; no statistical significance or performance promotion.',
                       'Localized host evidence remains exploratory; mmap1 requires strict endpoint identity.',
                       'Compiler/library bytes outside the archive are runner-verified dependencies, not independently archived bytes.',
                       'No scored parking, JIT-return, or specific timed-mm address observation.'])
    save(out/'validation.json', receipt)
    try:
        caches = {label: Cache(label, selected['boots'][label]) for label in labels}
        absolute = {}
        for cache in caches.values():
            for name, digest in cache.hashes.items():
                absolute[CAMPAIGN+'/'+cache.label+'/'+name] = digest
            for original, member in cache.aliases.items():
                digest = cache.hashes[member]
                need(original not in absolute or absolute[original] == digest, 'aliased artifact changed across boots')
                absolute[original] = digest
        original = caches['native-a']
        sources = original.json('preservation-inputs/kdlock-continuation-f7a84065-source-sha256.json')
        need(original.hashes['preservation-inputs/kdlock-continuation-f7a84065-source-sha256.json'] == SOURCE_SHA,
             'frozen f7 source map differs')
        for name, digest in sources.items():
            absolute[SOURCE_ROOT+name] = digest
        # Native-A captured 21 older, unused unit files because sync retains
        # untracked leaves. Keep these separate from the frozen tracked map.
        retained_name = 'api/source-sha256.json'
        need(original.hashes[retained_name] == '3dc60a693d07159a8e7878ee0f7e1858da67d627882dc64e71e346e511b23d14',
             'original retained probe snapshot differs')
        retained = {n: h for n, h in original.json(retained_name).items() if n not in sources}
        need(len(retained) == 21 and all(n.startswith('tests/unit/') for n in retained), 'retained snapshot scope differs')
        for name, digest in retained.items():
            need(original.hashes['api/source/'+name] == digest, 'retained unit snapshot bytes differ')
            absolute[SOURCE_ROOT+name] = digest
        for cache in caches.values():
            for name, digest in cache.hashes.items():
                for marker in ('/runtime-source/', '/source/'):
                    relative = name.split(marker, 1)[1] if marker in name else None
                    if relative in sources:
                        need(digest == sources[relative], 'archived source differs from f7: '+name)
        for name, digest in VALIDATORS.items():
            need(sources[name] == digest, 'validator differs from actual frozen inputs')
        external_dependencies = {}
        kernel_files, bundles = {}, {}
        for label, mode in [('native-a', 'native'), ('kd', 'kd')]:
            cache = caches[label]
            member = 'boot-evidence/'+mode+'-bundle/manifest.json'
            bundle = cache.json(member)
            need(bundle['variant'] == 'kdscope1-'+mode, 'mode bundle differs')
            bundles[mode] = bundle
            for kind in ('source', 'build'):
                for name, digest in bundle[kind+'_files'].items():
                    path = bundle[kind+'_root']+'/'+name
                    need(path not in kernel_files or kernel_files[path] == digest, 'same-image kernel files differ')
                    kernel_files[path] = digest

        def bind(files, allow_dependencies=None):
            need(isinstance(files, dict), 'file binding map required')
            for name, digest in files.items():
                if name in absolute:
                    need(absolute[name] == digest, 'artifact/source binding differs: '+name)
                elif name in kernel_files:
                    need(kernel_files[name] == digest, 'runner-verified kernel build identity differs: '+name)
                else:
                    need(allow_dependencies is not None and allow_dependencies.get(name) == digest,
                         'unarchived required artifact: '+name)
                    external_dependencies[name] = digest

        def result(label, step):
            cache = caches[label]
            owner_name = step+'-controller.json'
            owner = cache.json(owner_name)
            name = step+'/result.json'
            value = cache.json(name)
            need(cache.preservation['steps'][step]['owner_sha256'] == cache.hashes[owner_name] and
                 owner.get('result_sha256') == cache.hashes[name] and
                 owner.get('state') == 'COMPLETE' and owner.get('passed') is True and
                 owner.get('drained') is True and owner.get('final_idle') is True and
                 owner.get('completion_checks_passed') is True and owner.get('drain_unknown') is False and
                 owner.get('child_returncode') == 0 and owner.get('source_commit') == COMMIT and
                 owner.get('kernel_project_commit') == RECIPE and owner.get('expected_boot_id') == cache.boot and
                 owner.get('boot') == label and owner.get('step') == step and
                 owner.get('source_manifest_sha256') == SOURCE_SHA and owner.get('source_state_sha256') == STATE_SHA and
                 owner.get('generation_record_sha256') == GENERATION_SHA, 'step owner differs: '+label+'/'+step)
            need(value.get('passed') is True and value.get('drained') is True and
                 value.get('boot_id') == cache.boot and value.get('mode') == ('kd' if label.startswith('kd') else 'native'),
                 'runner result differs: '+label+'/'+step)
            bind(owner.get('prerequisite_bindings', {}))
            binding = value['kernel_binding']
            need(binding['release'] == '7.0.0-38-kdscope1' and binding['build_id'] == BUILD_ID and
                 binding['kernel_mmap_backend'] == value['mode'] and binding['private_backing_locks'] is False and
                 binding['variant'] == 'kdscope1-'+value['mode'] and
                 binding['runtime_policy']['mmap_mode'] == ('on' if value['mode'] == 'kd' else 'off') and
                 [x for x in binding['runtime_policy']['cmdline'].split() if x.startswith('kd_mmap=')] ==
                 ['kd_mmap='+('on' if value['mode'] == 'kd' else 'off')] and
                 value['kernel_identity'].get('runtime_policy_verified') is True, 'kernel identity differs')
            bundle = '/root/kdlock-kernel-baselines/linux70-kdscope1-'+value['mode']+'-20261030/manifest.json'
            bind({bundle: binding['manifest_sha256']})
            for kind in ('source_files', 'build_files'):
                need(bool(binding[kind]) and binding[kind] == bundles[value['mode']][kind], 'compiled kernel identity differs')
            return owner, value

        rt = SimpleNamespace(require=need)
        peak = pure(args.source, 'bench/spin_cacheline/peak.py', ('require', 'unsigned', 'analyze_peak'))
        writer = pure(args.source, 'bench/mmap_writer/timing.py', ('validate', 'spec'), rt=rt, math=math,
                      common=SimpleNamespace(analyze_peak=peak.analyze_peak))
        local = pure(args.source, 'bench/mmap_writer/linux70.py', ('validate',), rt=rt, writer=writer,
                     platform=SimpleNamespace(MODES=('native', 'kd')))
        mmap = pure(args.source, 'bench/mmap1/run.py', ('parse_output',), rt=rt, re=re,
                    DESCRIPTION='Anonymous memory mmap/munmap of 128MB', SAMPLES=2, UPSTREAM_S=2, WARMUP_SAMPLES=6)

        # Preparations have no scores. Reuse the one Native-A artifact set.
        prep = {}
        for label in ('native-a', 'kd'):
            _, r = result(label, 'shared-prepare')
            need(r['action'] == 'prepare' and len(r['sessions']) == 2 and
                 [x['threads'] for x in r['sessions']] == [1, 16] and
                 all(x['passed'] and x['drained'] for x in r['sessions']) and
                 len(r['sessions'][1]['rejected_mutations']) == 11, 'shared preparation differs')
            prep[label] = caches[label].json('shared-prepare/inputs.json')
            bind(prep[label]['files'])
            need(prep[label]['image_identity'] == image(r['kernel_binding']), 'preparation image differs')
        need(prep['native-a'] == prep['kd'], 'localized timed artifacts differ')
        mmap_inputs = original.json('mmap1-prepare/inputs.json')
        _, mr = result('native-a', 'mmap1-prepare')
        need(mr['action'] == 'prepare' and mr['inputs_sha256'] == original.hashes['mmap1-prepare/inputs.json'] and
             mmap_inputs.get('upstream_revision') == REVISION and mmap_inputs.get('executable_modified') is False and
             set(mmap_inputs['binaries']) == set(MODELS) and
             all(mmap_inputs['source_sha256'].get(n) == h for n, h in UPSTREAM_PINNED.items()),
             'original mmap1 preparation differs')
        bind(mmap_inputs['files'], mmap_inputs['dependencies'])
        for model, binary in mmap_inputs['binaries'].items():
            bind({binary: mmap_inputs['binary_sha256'][model]})

        points, grid_info = [], {}
        diagnostic_adapters, unused_generated_snapshots = {}, {}
        grids = [('kd', 'shared-measure'), ('native-b', 'shared-measure')]
        if args.scope == 'all':
            grids += [('native-b', 'mmap1-measure'), ('kd-b', 'mmap1-measure')]
        for label, step in grids:
            cache = caches[label]
            owner, r = result(label, step)
            strict = step == 'mmap1-measure'
            expected = [(model, n) for model in MODELS for n in WORKERS] if strict else [('shared', n) for n in WORKERS]
            actual = [(s['model'], s['workers']) if strict else ('shared', s['threads']) for s in r['sessions']]
            need(actual == expected and r['planned'] == len(expected) and r['single_round'] is True and
                 r['accepted'] is False and r['state'] == 'COMPLETE' and r['final_idle'] is True and
                 r['action'] == 'measure' and image(r['kernel_binding']) == prep['native-a']['image_identity'],
                 'single-round grid/image differs: '+label+'/'+step)
            for check in CHECKS:
                _, cr = result(label, check)
                need(cr['kernel_binding'] == r['kernel_binding'], 'same-boot correctness image/mode differs')
            inputs = cache.json(step+'/inputs.json')
            need(inputs == (mmap_inputs if strict else prep['native-a']), 'measured artifact inputs differ')
            topology = cache.json(step+'/topology.json')
            need(topology['online_cpus'] == list(range(64)) and topology['role_cpus'] == list(range(60)) and
                 topology['role_nodes'] == [0]*32+[1]*28, 'worker topology differs')
            env = cache.json(step+'/environment.json')
            need(env['boot_id'] == cache.boot and env['collector_topology']['role_cpus'] == [63], 'collector/boot differs')
            endpoint_name = 'endpoints/'+step+'/endpoint-receipt.json'
            ep = cache.json(endpoint_name)
            need(cache.preservation['endpoints'][step]['sha256'] == cache.hashes[endpoint_name] and
                 ep.get('completed') is True and ep.get('boot_id') == cache.boot and ep.get('label') == label and
                 ep.get('step') == step and ep.get('source_commit') == COMMIT and ep.get('kernel_project_commit') == RECIPE and
                 ep.get('measure_owner_sha256') == cache.hashes[step+'-controller.json'] and
                 ep.get('measure_result_sha256') == cache.hashes[step+'/result.json'] and
                 ep.get('strict_required') is strict and ep.get('rounds_per_point') == 1 and
                 ep.get('grid_points') == len(expected) and ep.get('performance_accepted') is False and
                 0 <= ep['capture_delay_from_transport_finish_seconds'] <= 300, 'endpoint differs')
            for filename, field in [('host-before.json', 'host_before_sha256'), ('host-after.json', 'host_after_sha256'),
                                    ('host-reference.json', 'reference_sha256'), ('endpoint-policy.json', 'endpoint_policy_sha256'),
                                    ('measure-transport-owner.json', 'measure_transport_owner_sha256')]:
                need(cache.hashes['endpoints/'+step+'/'+filename] == ep[field], 'endpoint input differs')
            need(ep['reference_sha256'] == REFERENCE_SHA and
                 ep['host_before_sha256'] == cache.hashes[step+'/host-before.json'] == owner['host_state_sha256'],
                 'endpoint before/reference differs')
            bind({ep['phase_controller_path']: ep['phase_controller_sha256']})
            for q in (r['host_qualification'], ep['comparison'], ep['comparison_to_before']):
                need(q['exploratory'] is (not strict) and q['strict_host_gate'] == ('PASS' if strict else 'FAILED') and
                     q['original_threads'] == q['observed_threads'] == 131 and
                     (not strict or q['task_set_unchanged'] is True), 'qualification relabeled or failed')
            if strict:
                _, diagnostic = result(label, 'mmap1-identity')
                need(diagnostic.get('scope') == 'diagnostic-class-proof' and
                     diagnostic['kernel_binding'] == r['kernel_binding'] and
                     diagnostic['inputs_sha256'] == r['inputs_sha256'] == original.hashes['mmap1-prepare/inputs.json'],
                     'separate mmap1 diagnostic/preparation binding differs')
                adapter = diagnostic.get('diagnostic_runner', {})
                retained_runner = CAMPAIGN+'/'+label+'/mmap1-identity/diagnostic-runner.py'
                need(adapter.get('path') == IDENTITY_RUNNER and
                     adapter.get('retained') == retained_runner and
                     adapter.get('source_commit') == IDENTITY_COMMIT and
                     adapter.get('maintained_sha256') == IDENTITY_MAINTAINED_SHA and
                     adapter.get('frozen_validator_sha256') == IDENTITY_FROZEN_SHA and
                     adapter.get('sha256') == IDENTITY_RUNNER_SHA and
                     diagnostic['files'].get(IDENTITY_RUNNER) == IDENTITY_RUNNER_SHA and
                     diagnostic['files'].get(retained_runner) == IDENTITY_RUNNER_SHA and
                     cache.hashes['mmap1-identity/diagnostic-runner.py'] == IDENTITY_RUNNER_SHA and
                     sources['tests/kernel/mmap1_identity/run.py'] == IDENTITY_FROZEN_SHA and
                     'kd_mmap1_identity.mod.c' not in diagnostic['source_sha256'],
                     'distinct diagnostic adapter or corrected build-source inputs differ')
                generated_relative = 'tests/kernel/mmap1_identity/payload/kd_mmap1_identity.mod.c'
                generated = SOURCE_ROOT+generated_relative
                extra = adapter.get('unused_generated_inputs')
                need(isinstance(extra, dict) and set(extra) ==
                     ({generated} if generated in diagnostic['files'] else set()),
                     'unexpected unused diagnostic generated inputs')
                if extra:
                    member = 'mmap1-identity/runtime-source/'+generated_relative
                    retained_generated = CAMPAIGN+'/'+label+'/'+member
                    digest = cache.hashes[member]
                    need(generated_relative not in sources and extra[generated] == dict(
                             sha256=digest, retained=retained_generated, built=False, tracked_f7_source=False) and
                         diagnostic['files'][generated] == diagnostic['files'][retained_generated] == digest and
                         cache.json('mmap1-identity/runtime-source-sha256.json').get(generated) == digest and
                         cache.json('mmap1-identity/runtime-source-sha256.json').get(retained_generated) == digest and
                         (generated not in absolute or absolute[generated] == digest),
                         'unused generated bytes do not match the actual retained runtime snapshot')
                    absolute[generated] = digest
                    unused_generated_snapshots[label] = extra
                diagnostic_adapters[label] = adapter
                bind(diagnostic['files'], mmap_inputs['dependencies'])
                bind({r['identity_result']['path']: r['identity_result']['sha256']})
                need(r['binary_sha256'] == mmap_inputs['binary_sha256'], 'mmap1 measured binary differs')
            names = [s['name'] if not strict else f'{s["model"]}-n{s["workers"]:02d}-r00' for s in r['sessions']]
            cache.logs([step+'/'+name+('/upstream.log' if strict else '/client.jsonl') for name in names])
            for s, name, coordinate in zip(r['sessions'], names, expected):
                child = cache.json(step+'/'+name+'/result.json')
                need(child == ({k: v for k, v in s.items() if k != 'name'} if not strict else s) and
                     s['state'] == 'COMPLETE' and s['passed'] is True and s['drained'] is True, 'point receipt differs')
                if strict:
                    need(s['round'] == 0 and s['nominal_seconds'] == 2 and s['scored'] is True and
                         s['instrumentation'] == 'none' and s['returncode'] == 0 and
                         s['executable_sha256'] == mmap_inputs['binary_sha256'][s['model']], 'mmap1 scored scope differs')
                    parsed = mmap.parse_output(cache.data(step+'/'+name+'/upstream.log').decode(), s['workers'])
                    need(parsed == s['output'], 'original upstream score differs')
                    # The live validator also queries parent affinity. Offline
                    # replay checks retained worker identities only; the actual
                    # collector check remains bound to the successful runner.
                    workers, parent = s['workers_observed'], s['pid']
                    need(len(workers) == s['workers'] and len({w['tid'] for w in workers}) == s['workers'] and
                         all(w['tid'] != parent and type(w['start_ticks']) is int and w['start_ticks'] > 0 and
                             w['executable'] == inputs['binaries'][s['model']] and len(w['cpus']) == 1 and
                             w['tgid'] == (parent if s['model'] == 'threads' else w['tid']) and
                             (s['model'] == 'threads' or w['ppid'] == parent) for w in workers) and
                         sorted(w['cpus'][0] for w in workers) == list(range(s['workers'])), 'retained worker placement differs')
                    need(s['observation_finished_ns']-s['started_ns'] < 5_000_000_000, 'placement observation overlaps measured tail')
                    score, metric = parsed['pairs_per_nominal_second'], 'pairs_per_nominal_second'
                else:
                    spec = dict(writer.spec(s['threads'], 'plain', 0), arm=r['mode'], backend=r['mode'], peak_policy='optional-positive-window')
                    need(all(s[k] == v for k, v in spec.items()), 'localized plan differs')
                    rows = [json.loads(line) for line in cache.data(step+'/'+name+'/client.jsonl').splitlines()]
                    parsed = local.validate(rows, spec)
                    need(parsed == s['measurement'] and s['health'] == 'files=0 mm_refs=0 destroyed=1 release_errors=0',
                         'actual joined-wall score/lifetime differs')
                    score, metric = parsed['whole_ops_s'], 'whole_ops_s'
                need(math.isfinite(score) and score > 0, 'nonpositive/nonfinite score')
                points.append(dict(label=label, boot_id=cache.boot, mode=r['mode'], model=coordinate[0], workers=coordinate[1],
                                   round=0, metric=metric, score=score, qualification='strict' if strict else 'exploratory',
                                   result_sha256=cache.hashes[step+'/'+name+'/result.json']))
            grid_info[label+'/'+step] = dict(owner_sha256=cache.hashes[step+'-controller.json'], result_sha256=cache.hashes[step+'/result.json'],
                endpoint_sha256=cache.hashes[endpoint_name], image=image(r['kernel_binding']), topology=topology,
                environment={k: env[k] for k in ('preemption', 'packages', 'python', 'semantic_builder', 'collector_topology')})
        identities = list(grid_info.values())
        need(all(v['image'] == identities[0]['image'] and v['topology'] == identities[0]['topology'] and
                 v['environment'] == identities[0]['environment'] for v in identities), 'source/image/topology/dependencies differ across grids')
        comparisons = []
        for native in [row for row in points if row['mode'] == 'native']:
            kd = [row for row in points if row['mode'] == 'kd' and
                  (row['metric'], row['model'], row['workers']) == (native['metric'], native['model'], native['workers'])]
            need(len(kd) == 1, 'ambiguous/missing KD comparison point')
            kd = kd[0]
            comparisons.append(dict(metric=native['metric'], model=native['model'], workers=native['workers'], round=0,
                qualification=native['qualification'], native=native['score'], kd=kd['score'],
                kd_over_native=kd['score']/native['score'], change_percent=(kd['score']/native['score']-1)*100,
                native_boot=native['boot_id'], kd_boot=kd['boot_id']))
        for metric in sorted({row['metric'] for row in comparisons}):
            rows = [row for row in comparisons if row['metric'] == metric]
            with (out/(metric+'.csv')).open('x', newline='') as stream:
                writer_csv = csv.DictWriter(stream, fieldnames=list(rows[0])); writer_csv.writeheader(); writer_csv.writerows(rows)
        save(out/'points.json', points)
        receipt.update(completed=True, validated=True, grids=grid_info, point_count=len(points), comparison_count=len(comparisons),
                       comparisons_by_metric={metric: sum(row['metric'] == metric for row in comparisons) for metric in {r['metric'] for r in comparisons}},
                       archive_inputs={k: v.transfer for k, v in caches.items()}, runner_verified_external_dependencies=external_dependencies,
                       runner_verified_kernel_build_files=kernel_files, retained_untracked_unit_snapshots=retained,
                       diagnostic_adapters=diagnostic_adapters, unused_generated_snapshots=unused_generated_snapshots,
                       artifacts={p.name: sha(p) for p in out.iterdir() if p.name != 'validation.json'})
    except BaseException as error:
        receipt.update(error=repr(error))
        save(out/'validation.json', receipt)
        raise
    save(out/'validation.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('completed', 'validated', 'performance_accepted', 'point_count', 'comparison_count')}))


if __name__ == '__main__':
    main()
