#!/usr/bin/env python3
"""Strict held-writer syscall witness; correctness only, VM execution only."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/root/host_fs/kdlock')
LEAVES = ('README.md', 'run.py', 'payload/Makefile', 'payload/api.h',
          'payload/module.c', 'payload/client.c')
MUTATIONS = ('different_lock', 'wrong_caller_return', 'wrong_wait_return',
             'wrong_adapter_return', 'running_task', 'other_wait_channel',
             'rescheduled_task', 'missing_chain', 'missing_writer_proof')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classifier(text):
    """Retain exact complete functions; replace neither their gates nor bodies."""
    ranges = (('static void json_string(', 'static int proc_text('),
              ('static char task_state(', '/* Called only after successful joins'))
    pieces = []
    for start, end in ranges:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('frozen classifier extraction boundary differs')
        a, b = text.index(start), text.index(end)
        if not a < b:
            raise ValueError('classifier extraction order differs')
        pieces.append(text[a:b])
    return ''.join(pieces)


def validate(rows, operation, mode, proof, require):
    by = lambda event: [r for r in rows if r.get('event') == event]
    for event in ('target', 'observer', 'writer_stack', 'strict_observation', 'complete'):
        require(len(by(event)) == 1, 'one actual ' + event + ' required')
    require(set(r['event'] for r in rows) <= {'target', 'observer', 'writer_stack',
            'strict_observation', 'complete', 'stack_observation'}, 'unexpected client record')
    require(len(by('stack_observation')) <= 4 and all(r.get('raw_stack') for r in by('stack_observation')),
            'bounded raw classifier observations differ')
    target, observer, stack, observation, final = [by(event)[0] for event in
        ('target', 'observer', 'writer_stack', 'strict_observation', 'complete')]
    require(target['operation'] == final['operation'] == operation and target['mm'] and target['mmap_lock'] and
            target['object'] and target['tgid'] == target['tid'] and target['use_kd'] == int(mode == 'kd'),
            'original target mm/backend differs')
    require(observer['mm'] and observer['mm'] != target['mm'] and observer['tgid'] == observer['tid'] and
            observer['tgid'] != target['tgid'], 'observer must have a separate actual mm')
    require(stack['tid'] == target['tid'] and stack['mm'] == target['mm'] and
            stack['mmap_lock'] == target['mmap_lock'] and
            stack['caller'] == ('vm_mmap_pgoff' if operation == 'mmap' else '__vm_munmap'),
            'witness is not the exact target syscall/lock')
    proof(stack, mode)
    require(observation['passed'] is True and final['passed'] is True and
            final['mm'] == target['mm'] and final['mmap_lock'] == target['mmap_lock'] and
            final['target_tid'] == target['tid'] and final['holder_tid'] not in (0, target['tid'], observer['tid']) and
            final['acquired'] == final['unlocked'] == final['joined'] == 1 and
            final['timed_out'] == final['errors'] == 0, 'strict witness/owner/join completion differs')
    return dict(operation=operation, passed=True, target=target, observer=observer,
                writer_stack=stack, completion=final)


def main():
    # Establish explicit complete source identity before importing runtime gates.
    bootstrap = argparse.ArgumentParser(add_help=False)
    for name in ('harness-source', 'harness-manifest'):
        bootstrap.add_argument('--' + name, type=Path, required=True)
    for name in ('harness-manifest-sha256', 'harness-commit'):
        bootstrap.add_argument('--' + name, required=True)
    harness, _ = bootstrap.parse_known_args()
    if (os.geteuid() != 0 or not re.fullmatch('[0-9a-f]{40}', harness.harness_commit) or
            sha(harness.harness_manifest) != harness.harness_manifest_sha256 or
            not ROOT.is_mount() or not os.path.samefile(ROOT, harness.harness_source) or
            not os.statvfs(ROOT).f_flag & os.ST_RDONLY):
        raise RuntimeError('actual guest root and frozen common harness required')
    manifest = json.loads(harness.harness_manifest.read_bytes())
    if manifest.get('source_commit') != harness.harness_commit:
        raise RuntimeError('common harness commit differs')
    for name, row in manifest['files'].items():
        if sha(ROOT / name) != row['sha256']:
            raise RuntimeError('common harness differs: ' + name)
    sys.path.insert(0, str(ROOT / 'bench/mmap_writer'))
    import shared_platform as platform
    rt = platform.rt
    sites = load_module('strict_hold_sites', ROOT / 'bench/mmap_writer/sites.py')
    mapping = load_module('strict_hold_mapping', ROOT / 'tests/kernel/mmap_lock/mapping.py')
    p = argparse.ArgumentParser(description=__doc__, parents=[bootstrap])
    p.add_argument('--mode', choices=('native', 'kd'), required=True)
    p.add_argument('--output', type=Path, required=True)
    for name in ('writer-sites', 'api-result', 'diagnostic-manifest'):
        p.add_argument('--' + name, type=Path, required=True)
        p.add_argument('--' + name + '-sha256', required=True)
    platform.arguments(p)
    a = p.parse_args()
    platform.guest(a)
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external diagnostic output required')
    mapping.checks.idle(out.parent)
    rt.require(not Path('/sys/module/kd_mmap_strict_hold').exists(), 'existing strict holder module')
    for name in ('writer_sites', 'api_result', 'diagnostic_manifest'):
        rt.require(sha(getattr(a, name)) == getattr(a, name + '_sha256'), 'actual input differs: ' + name)
    diagnostic = json.loads(a.diagnostic_manifest.read_bytes())
    rt.require(re.fullmatch('[0-9a-f]{40}', diagnostic['commit']) and set(diagnostic['files']) == set(LEAVES),
               'exact committed diagnostic source manifest required')
    rt.require(all(sha(HERE / name) == digest for name, digest in diagnostic['files'].items()),
               'diagnostic source changed')
    api = json.loads(a.api_result.read_bytes())
    rt.require(api.get('passed') is True and api.get('drained') is True and api['boot_id'] == a.boot_id and
               api['mode'] == a.mode and api['probe']['use_kd'] == int(a.mode == 'kd'), 'same-boot actual-MM API pass required')
    out.mkdir(parents=True)
    result = dict(schema=1, diagnostic='same-mm-held-writer-v1', state='PREPARATION', passed=False,
                  drained=False, final_idle=False, accepted=False, timing=False, boot_id=a.boot_id,
                  mode=a.mode, harness_commit=a.harness_commit,
                  harness_manifest_sha256=a.harness_manifest_sha256, diagnostic_commit=diagnostic['commit'], cases=[],
                  diagnostic_manifest_sha256=a.diagnostic_manifest_sha256, api_result_sha256=a.api_result_sha256)
    rt.write_json(out / 'result.json', result)
    fd, messages = None, ''

    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out / 'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages), 'kernel fault; preserve diagnostic module', 'KERNEL_FAULT')

    try:
        result.update(platform.admit(a, out))
        rt.require(api['kernel_binding'] == result['kernel_binding'], 'API kernel binding differs')
        files = platform.freeze_support(out)
        for name in LEAVES:
            original, saved = HERE / name, out / 'source' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, saved)
            files[str(original)] = files[str(saved)] = sha(original)
        for name, original in (('diagnostic-manifest.json', a.diagnostic_manifest),
                               ('harness-manifest.json', a.harness_manifest),
                               ('api-result.json', a.api_result), ('writer-sites.json', a.writer_sites)):
            saved = out / name
            shutil.copyfile(original, saved)
            files[str(original)] = files[str(saved)] = sha(original)
        for rel in ('bench/mmap_writer/client.c', 'workload_modules/mmap_writer/mmap_writer_uapi.h',
                    'tests/kernel/mmap_lock/mapping.py'):
            saved = out / 'frozen-classifier-source' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, saved)
            files[str(ROOT / rel)] = files[str(saved)] = sha(saved)
        evidence = out / 'writer-disassembly'
        evidence.mkdir()
        actual_sites = sites.checked_receipt(a.writer_sites, a.writer_sites_sha256,
            result['kernel_binding'], a.kernel_source / 'vmlinux', evidence, rt.command)
        mapping.SITES = actual_sites
        result['writer_sites_sha256'] = a.writer_sites_sha256
        source = out / 'source/payload'
        generated = classifier((ROOT / 'bench/mmap_writer/client.c').read_text())
        (source / 'classifier.inc').write_text(generated)
        shutil.copyfile(ROOT / 'workload_modules/mmap_writer/mmap_writer_uapi.h', source / 'mmap_writer_uapi.h')
        for leaf in ('classifier.inc', 'mmap_writer_uapi.h'):
            files[str(source / leaf)] = sha(source / leaf)
        result['classifier'] = dict(source_sha256=sha(ROOT / 'bench/mmap_writer/client.c'),
            extracted_sha256=sha(source / 'classifier.inc'), functions=['json_string', 'task_state',
            'chain_wait_arguments', 'chain_frame', 'writer_chain_tail', 'writer_observation',
            'writer_contention'], changed_bodies=False)

        def verify():
            platform.verify_boot(a)
            rt.require(all(sha(path) == digest for path, digest in files.items()), 'diagnostic/runtime input changed')

        rt.command(['make', '-C', source, 'KDIR=' + str(a.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                   out / 'build-module.log', timeout=180)
        module = source / 'kd_mmap_strict_hold.ko'
        client = out / 'client'
        rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-Wl,-z,now', '-I' + str(source),
                    source / 'client.c', '-o', client], out / 'build-client.log', timeout=60)
        files[str(module)] = sha(module)
        files[str(client)] = sha(client)
        result['files'] = files
        rt.write_json(out / 'source-sha256.json', files)
        verify()
        mapping.checks.idle(out.parent)
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', module], out / 'load.log')
        chain = actual_sites['chains'][a.mode]
        proof_args = [str(actual_sites['sites'][name]['return_offset']) for name in ('vm_mmap_pgoff', '__vm_munmap')]
        proof_args += [sites.waiter_argument(chain), *sites.wait_arguments(chain),
                       str(chain['adapter_return']), actual_sites['adapter']]
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        for index, operation in enumerate(('mmap', 'munmap'), 1):
            data = rt.command([client, operation, *proof_args], out / (operation + '.jsonl'), timeout=45)
            logs()
            rows = [json.loads(line) for line in data.splitlines()]
            case = validate(rows, operation, a.mode, mapping.chain_proof, rt.require)
            edits = (lambda r: r.__setitem__('mmap_lock', 1), lambda r: r.__setitem__('return_offset', 1),
                     lambda r: r.__setitem__('wait_return_offset', 1), lambda r: r.__setitem__('adapter_return_offset', 1),
                     lambda r: r.__setitem__('state_after', 'R'), lambda r: r.__setitem__('wchan_before', 'futex_wait'),
                     lambda r: r.__setitem__('schedstat_after', '1 2 3\n'), lambda r: r.__setitem__('raw_stack', 'missing'))
            rejected = []
            for name, edit in zip(MUTATIONS, edits):
                bad = copy.deepcopy(rows)
                edit(next(row for row in bad if row['event'] == 'writer_stack'))
                try:
                    validate(bad, operation, a.mode, mapping.chain_proof, rt.require)
                except rt.Failure:
                    rejected.append(name)
                else:
                    raise RuntimeError('corrupt positive witness accepted: ' + name)
            try:
                validate([r for r in rows if r['event'] != 'writer_stack'], operation, a.mode, mapping.chain_proof, rt.require)
            except rt.Failure:
                rejected.append('missing_writer_proof')
            rt.require(tuple(rejected) == MUTATIONS, 'missing witness accepted')
            health = Path('/sys/module/kd_mmap_strict_hold/parameters/health').read_text().strip()
            rt.require(health == f'files=0 mm_refs=0 active=0 errors=0 objects={index}', 'exact diagnostic holder drain differs')
            case.update(rejected_mutations=rejected, health=health)
            result['cases'].append(case)
            rt.write_json(out / 'result.json', result)
        rt.command(['rmmod', 'kd_mmap_strict_hold'], out / 'unload.log')
        logs()
        verify()
        mapping.checks.idle(out.parent)
        rt.require(not Path('/sys/module/kd_mmap_strict_hold').exists(), 'diagnostic module remains loaded')
        result.update(state='COMPLETE', passed=True, drained=True, final_idle=True, source_unchanged=True, files=files)
        rt.write_json(out / 'source-sha256.json', files)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        platform.common.finish_logs(out, result, logs, fd)
    print(json.dumps(dict(state=result['state'], passed=result['passed'], drained=result['drained'], cases=len(result['cases']))))


if __name__ == '__main__':
    main()
