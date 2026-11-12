#!/usr/bin/env python3
"""VM-only build/sign and bounded frame comparison for one metadata provider.

Reuses checked metadata and one bounded build loop, never the old main.
No kernel build, client, check suite, module load or runtime command is invoked.
The prior and new unsigned ioctl disassemblies remain separate exact artifacts.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import runpy
import shutil
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
TRANSPORT = BASE/'mm-provider-ioctl-input-0798c1ab-01'
RECIPE_SHA = 'ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7'
OLD_SHA = '56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb'
PRIOR_SHA = '223392b879bd1aaad6ffc3e40f322706be8bd94039abd0a50c16afe238ffa37c'
NATIVE_SHA = '2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074'
record = None
ns = None


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def idle(native, recipe):
    current = native['idle']()
    expected = recipe['candidate_idle_policy']
    need(current['identity'] == {'boot': expected['boot_id'], 'release': expected['release'],
                                'taint': expected['expected_taint']}, 'exact candidate boot/release/taint differs')
    need({line.split()[0] for line in current['modules'].splitlines()} == set(expected['modules']),
         'exact candidate NLS module set differs')
    actors = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            comm = (entry/'comm').read_text().strip()
            argv = (entry/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            if comm.startswith('kd-kill') or comm == 'mmap-userspace' or any(
                    token in argv for token in ('tests/kernel/rwsem_killable/runner.py',
                                                'tests/kernel/mmap_api/runner.py')):
                actors.append({'pid': int(entry.name), 'comm': comm, 'argv': argv})
        except (FileNotFoundError, ProcessLookupError):
            continue
    need(not actors, 'prior managed/API workload remains: ' + repr(actors))
    for name in ('kd_rwsem_killable_fixture', 'kd_rwsem_runtime_fixture', 'kd_runtime_fixture',
                 'kd_rwsem_api', 'kd_mmap_api'):
        for suffix in ('', '_ctl', '_events'):
            need(not (Path('/dev')/(name+suffix)).exists(), 'fixture/API device remains: ' + name+suffix)
    return current


def prior_artifacts(prior):
    need(set(prior['modules']) == {'native-api', 'mmap', 'killable', 'rwsem', 'mutex'},
         'all five prior compiled module identities required')
    result = {}
    for label, module in prior['modules'].items():
        for form in ('unsigned', 'signed'):
            row = module[form]
            path = ns['canonical'](row['path'])
            need(path.is_relative_to(BASE/'build-01'), 'prior module lies outside preserved build01')
            actual = ns['facts'](path)
            need(actual == row, 'prior module bytes differ: ' + label + '/' + form)
            result[label+'/'+form] = actual
    row = prior['client']
    path = ns['canonical'](row['path'])
    need(path == BASE/'build-01/mmap-userspace', 'exact preserved client path required')
    result['client'] = ns['facts'](path)
    need(result['client'] == row, 'prior client bytes differ')
    return result


def tools(recipe):
    result = {}
    for name, row in recipe['tools'].items():
        alias = Path(row['path'])
        resolved = ns['canonical'](row['resolved_path'])
        need(alias.is_absolute() and alias.resolve(strict=True) == resolved and digest(resolved) == row['sha256'],
             'actual invocation/resolved tool differs: ' + name)
        result[name] = {'alias': str(alias), 'resolved': str(resolved), 'sha256': digest(resolved)}
    need(set(result) == {'make', 'gcc', 'modinfo', 'python', 'objdump'} and Path(result['modinfo']['alias']).name == 'modinfo',
         'exact five tools and kmod modinfo invocation required')
    return result



def fixed_entry_frame(path, limits):
    raw = path.read_bytes()
    need(len(raw) <= limits['maximum_log_bytes'], 'bounded frame log exceeded')
    text = raw.decode()
    symbol = limits['symbol']
    labels = re.findall(r'^\s*[0-9a-f]+ <([^>]+)>:\s*$', text, re.M)
    need(labels == [symbol], 'exact single jit_ioctl disassembly symbol required')
    instructions = []
    for line in text.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$', line)
        if match:
            instructions.append({'address': int(match[1], 16), 'mnemonic': match[2],
                                 'operands': match[3].split('#', 1)[0].strip(), 'text': line})
    leading = instructions[:limits['maximum_instructions_before_reservation']]
    allocations = []
    for index, instruction in enumerate(leading):
        if instruction['mnemonic'] == 'sub':
            match = re.fullmatch(r'rsp,\s*(0x[0-9a-f]+|[0-9]+)', instruction['operands'])
            if match:
                allocations.append((index, int(match[1], 0)))
    need(len(allocations) == 1 and allocations[0][1] > 0,
         'fixed entry RSP reservation is unresolved; retain raw disassembly')
    index, reserved = allocations[0]
    prologue = leading[:index+1]
    pushes = 0
    for row in prologue[:-1]:
        if row['mnemonic'] == 'push':
            need(re.fullmatch(r'(?:rbx|rbp|r12|r13|r14|r15)', row['operands']) is not None,
                 'non-callee-save prologue push requires review')
            pushes += 8
        need(row['mnemonic'] not in ('enter', 'leave', 'pop') and
             not (row['mnemonic'] in ('and', 'lea', 'mov', 'add', 'sub') and
                  row['operands'].split(',', 1)[0].strip() == 'rsp'),
             'dynamic or additional entry stack adjustment requires review')
    return {'symbol': symbol, 'log_sha256': digest(path), 'log_bytes': len(raw),
            'fixed_rsp_reservation_bytes': reserved, 'callee_save_push_bytes': pushes,
            'entry_prologue_bytes': reserved + pushes, 'reservation_instruction': leading[index],
            'prologue': prologue, 'scope': limits['scope']}


def main():
    global ns, record
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--recipe-sha256', required=True)
    parser.add_argument('--recovery-sha256', required=True)
    args = parser.parse_args()
    need(os.geteuid() == 0 and args.recipe_sha256 == RECIPE_SHA, 'VM root and exact closed recipe required')
    old = BASE/'transport/build.py'
    native_path = BASE/'native-api-input-01/controller.py'
    need(digest(old) == OLD_SHA and digest(native_path) == NATIVE_SHA, 'reviewed metadata/idle helpers differ')
    ns = runpy.run_path(str(old))
    g = ns['main'].__globals__
    native = runpy.run_path(str(native_path))
    ns['environment']()
    need(not any(name in os.environ for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONOPTIMIZE',
            'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH')),
         'inherited execution override refused')
    recipe_path, recipe = ns['checked_json'](args.recipe, RECIPE_SHA)
    need(recipe_path == TRANSPORT/'recipe.json' and recipe['kernel_core_git_head'] == ns['CORE'] and
         recipe['kernelrelease'] == ns['RELEASE'] and recipe['actual_kbuild_target'] == 'kd_mmap_api_provider.ko',
         'exact recipe path/core/target required')
    bounds = recipe['bounds']
    need(bounds == {'check_seconds': 60, 'client_seconds': 60, 'jobs': 8, 'log_bytes': 536870912,
                    'module_seconds': 180, 'output_floor_bytes': 4294967296, 'root_floor_bytes': 1073741824,
                    'source_bytes': 2097152, 'total_seconds': 900, 'frame_log_bytes': 262144}, 'closed finite bounds differ')
    before = idle(native, recipe)
    need(native['running_notes']()[1] == recipe['build_id'], 'actual running Build ID differs')
    proof = Path(recipe['kernel_build']).parent/'receipts/postboot-kdrebuild8-api-01'
    need(digest(proof/'result.json') == '878c80315ed3f5ee9fd96388987a64cb7f0776ea01bc4eae044eca63ff2bb919' and
         digest(proof/'gs-proof.json') == '7b3480c16ac39def469c84d1a9cc349bcb15a591b655e752eb221c93e2b5a803',
         'actual kernel8 postboot/GS receipts differ')
    tools_before = tools(recipe)
    bp, built = ns['checked_json'](recipe['kernel_full_receipt']['path'], recipe['kernel_full_receipt']['sha256'])
    need(built['status'] == 'BUILT_AND_LINKED_IDENTITY_VERIFIED' and built['phase'] == 'build', 'actual full build required')
    ip, linked = ns['checked_json'](bp.parent/'final-identity.json', recipe['final_identity_sha256'])
    fp, focused = ns['checked_json'](built['focused_receipt'], built['focused_sha256'])
    source, build = ns['canonical'](recipe['kernel_source']), ns['canonical'](recipe['kernel_build'])
    output_pins = {name: row['sha256'] for name, row in recipe['kernel_files'].items()}
    need(set(output_pins) == set(ns['FILE_NAMES']) and len(output_pins) == 16 and
         output_pins == {name: row['sha256'] for name, row in linked['files'].items()} and
         linked['build_id'] == recipe['build_id'] and source == Path(built['source']) and build == Path(built['build']) and
         focused['target_units'] == {'core': 33, 'native': 8} and len(focused['package_after']) == 78,
         'exact linked16/focused78/source/O identity differs')
    core_before = ns['pins'](build, output_pins)
    protected_before, source_before = ns['protected'](focused), ns['source_pins'](focused, source)
    need(protected_before == built['protected_after'] and source_before == built['source_after'],
         'normal/kernel6/kernel7/kernel8 source protections changed')
    boot_before = ns['boot_files']()
    prior_path, prior = ns['checked_json'](BASE/'build-01/receipts/result.json', PRIOR_SHA)
    need(prior['source_git_head'] == '140aecc4f83a6b6ae6f20245234e8a63504f9210' and
         prior['kernel_core_git_head'] == ns['CORE'] and prior['status'] == 'FAILED_OR_INCOMPLETE',
         'exact prior five-build receipt required, including its later checker failure')
    preserved_before = prior_artifacts(prior)
    derivation = recipe['controller_derivation']
    need(digest(derivation['parent_guest']) == derivation['parent_sha256'] ==
         'f560a2215cb3a6b86ca7d2a8e58d12c332cbd6ea09a277bffacf304d2107ba84' and
         digest(derivation['parent_recipe_guest']) == derivation['parent_recipe_sha256'] ==
         '8534523d3e9af0d3f27be329692c3ced75c8ce6e3b7a18f7ac6ca98f0c9c5c30',
         'reviewed parent provider helper/recipe differs')
    previous = recipe['prior_provider']
    pp, previous_record = ns['checked_json'](previous['receipt'], previous['receipt_sha256'])
    need(previous_record['status'] == previous['status'] == 'MM_PROVIDER_MODULE_BUILD_COMPLETE' and
         previous_record['source_git_head'] == previous['source_git_head'] ==
         'de76da8aa2031d73f185f5864071f316c1150c08' and
         previous_record['modules']['mmap']['unsigned'] == previous['unsigned'] and
         previous_record['modules']['mmap']['signed'] == previous['signed'],
         'exact previous provider build receipt differs')
    previous_pins = {form: ns['facts'](ns['canonical'](previous[form]['path'])) for form in ('unsigned', 'signed')}
    need(all(previous_pins[form] == previous[form] for form in previous_pins),
         'previous provider output bytes differ')
    archive = ns['canonical'](TRANSPORT/'source.tar')
    manifest_path, files = ns['checked_json'](TRANSPORT/'source-sha256.json', recipe['host_source']['transport']['source-sha256.json']['sha256'])
    state_path, state = ns['checked_json'](TRANSPORT/'source-state.json', recipe['host_source']['transport']['source-state.json']['sha256'])
    need(archive.stat().st_size == recipe['host_source']['transport']['source.tar']['bytes'] and
         digest(archive) == recipe['host_source']['transport']['source.tar']['sha256'] and
         state == {'files': 143, 'git_status': '', 'source_git_head': recipe['host_source']['source_git_head'],
                   'transfer_bytes': recipe['host_source']['transfer_bytes']} and len(files) == 143 and
         sum(row['bytes'] for row in files.values()) == state['transfer_bytes'], 'frozen 0798c1ab transport differs')
    need(all(files[name]['sha256'] == value for name, value in focused['package_after'].items()) and
         all(files[name] == row for name, row in recipe['relevant_source_files'].items()),
         'snapshot kernel78/provider/private include differs')
    config_lines = (build/'.config').read_text().splitlines()
    need('CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"' in config_lines and
         'CONFIG_MODULE_SIG_HASH="sha512"' in config_lines, 'normal signing configuration differs')
    sign_tool = ns['canonical'](build/'scripts/sign-file')
    key = ns['canonical'](build/'certs/signing_key.pem')
    certificate = ns['canonical'](build/'certs/signing_key.x509')
    need(digest(sign_tool) == recipe['signing']['sign_file_sha256'] and key.is_file() and
         digest(certificate) == recipe['signing']['certificate_sha256'], 'normal signing tool/certificate differs')
    recovery = ns['fresh_recovery'](TRANSPORT/'recovery.json', args.recovery_sha256, recipe['fresh_recovery_policy'])
    root = Path(recipe['output'])
    need(root.parent.resolve(strict=True) == BASE and not os.path.lexists(root) and
         not root.is_relative_to(source) and not root.is_relative_to(build), 'fresh separate output required')
    need(ns['available']('/') >= bounds['root_floor_bytes'] and ns['available'](BASE) >= bounds['output_floor_bytes'],
         'root/data headroom below explicit floor')
    root.mkdir(mode=0o700)
    receipt, inp, signed = root/'receipts', root/'input', root/'signed'
    receipt.mkdir(mode=0o700)
    signed.mkdir(mode=0o700)
    g['out'] = receipt
    record = {'status': 'PREPARED', 'recipe': str(recipe_path), 'recipe_sha256': RECIPE_SHA,
              'source_git_head': recipe['host_source']['source_git_head'], 'kernel_core_git_head': ns['CORE'],
              'kernelrelease': ns['RELEASE'], 'linked_build_id': linked['build_id'], 'source_input': str(inp),
              'identity_before': before, 'recovery': recovery, 'tools_before': tools_before, 'commands': [], 'modules': {},
              'core_pins_before': core_before, 'protected_before': protected_before, 'source_before': source_before,
              'boot_before': boot_before, 'preserved_artifacts_before': preserved_before,
              'prior_build_receipt': str(prior_path), 'prior_build_sha256': PRIOR_SHA,
              'prior_build_status': prior['status'], 'signing_private_key_data_recorded': False,
              'public_certificate_sha256': digest(certificate),
              'previous_provider': previous, 'previous_provider_pins': previous_pins,
              'scope': 'One external metadata-provider build/sign/modinfo and two bounded jit_ioctl disassemblies only. No kernel build, install, load, client, unit, GS or runtime execution.'}
    g['record'] = record
    ns['atomic_json']('result.json', record)
    ns['unpack'](archive, files, inp, bounds['source_bytes'])
    need(inp == Path(recipe['input']), 'fresh source input path differs from exact make arguments')
    deadline = time.monotonic() + bounds['total_seconds']
    module_out = root/'mmap-build'
    need(module_out == Path(recipe['module_output']), 'fresh module output differs')
    module_out.mkdir(mode=0o700)
    command = recipe['commands'][0]
    log = ns['dispatch'](command['label'], command['argv'], deadline, command['seconds'], root, bounds)
    module = ns['canonical'](module_out/recipe['actual_kbuild_target'])
    need(sorted(module_out.glob('*.ko')) == [module], 'exact one named provider module required')
    unsigned = ns['facts'](module)
    target = Path(recipe['signed_output'])
    need(target.parent == signed and target.name == module.name and not os.path.lexists(target), 'exclusive signed output required')
    with module.open('rb') as original, target.open('xb') as output:
        shutil.copyfileobj(original, output)
        output.flush()
        os.fsync(output.fileno())
    need(target.stat().st_ino != module.stat().st_ino or target.stat().st_dev != module.stat().st_dev,
         'signed copy must have its own inode')
    fd = os.open(signed, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    record['modules']['mmap'] = {'unsigned': unsigned, 'diagnostics': ns['diagnostic_rows'](log)}
    ns['atomic_json']('result.json', record)
    fields = {}
    for command in recipe['commands'][1:7]:
        metadata = ns['dispatch'](command['label'], command['argv'], deadline, command['seconds'], root, bounds)
        need(digest(module) == unsigned['sha256'], 'signing/metadata changed the unsigned output')
        if command['label'] != 'mmap-sign':
            fields[command['label'][len('mmap-'):]] = metadata.read_text().strip()
            record['modules']['mmap']['modinfo'] = dict(fields)
            ns['atomic_json']('result.json', record)
    need(fields == recipe['expected_modinfo'], 'actual signed provider metadata differs')
    record['modules']['mmap'] = {'unsigned': unsigned, 'signed': ns['facts'](target), 'modinfo': fields,
                                  'diagnostics': ns['diagnostic_rows'](log)}
    need(len(record['commands']) == 7 and all(row['returncode'] == 0 for row in record['commands']),
         'all seven actual build/sign/metadata commands must complete')
    frames = {}
    for command in recipe['commands'][7:]:
        frame_bounds = dict(bounds, log_bytes=bounds['frame_log_bytes'])
        frame_log = ns['dispatch'](command['label'], command['argv'], deadline, command['seconds'], root, frame_bounds)
        frames[command['label']] = fixed_entry_frame(frame_log, recipe['frame_comparison'])
        record['frame_comparison'] = dict(frames)
        ns['atomic_json']('result.json', record)
    need(set(frames) == {'mmap-old-ioctl-frame', 'mmap-new-ioctl-frame'} and len(record['commands']) == 9 and
         all(row['returncode'] == 0 for row in record['commands']), 'all nine actual commands required')
    old_frame, new_frame = frames['mmap-old-ioctl-frame'], frames['mmap-new-ioctl-frame']
    need(new_frame['fixed_rsp_reservation_bytes'] < old_frame['fixed_rsp_reservation_bytes'],
         'new ioctl fixed entry RSP reservation did not decrease')
    record['frame_comparison']['fixed_rsp_reservation_reduction_bytes'] = (
        old_frame['fixed_rsp_reservation_bytes'] - new_frame['fixed_rsp_reservation_bytes'])
    record['frame_comparison']['entry_prologue_reduction_bytes'] = (
        old_frame['entry_prologue_bytes'] - new_frame['entry_prologue_bytes'])
    ns['source_files'](inp, files)
    need(digest(recipe_path) == RECIPE_SHA and digest(archive) == recipe['host_source']['transport']['source.tar']['sha256'] and
         digest(manifest_path) == recipe['host_source']['transport']['source-sha256.json']['sha256'] and
         digest(state_path) == recipe['host_source']['transport']['source-state.json']['sha256'] and
         digest(prior_path) == PRIOR_SHA and prior_artifacts(prior) == preserved_before and
         digest(pp) == previous['receipt_sha256'] and
         all(ns['facts'](Path(previous[form]['path'])) == previous_pins[form] for form in previous_pins) and
         ns['pins'](build, output_pins) == core_before and ns['protected'](focused) == protected_before and
         ns['source_pins'](focused, source) == source_before and ns['boot_files']() == boot_before and
         digest(sign_tool) == recipe['signing']['sign_file_sha256'] and
         digest(certificate) == recipe['signing']['certificate_sha256'], 'frozen inputs or preserved outputs changed')
    after = idle(native, recipe)
    need(after['identity'] == before['identity'] and native['running_notes']()[1] == recipe['build_id'] and
         tools(recipe) == tools_before, 'actual candidate/tool identity changed')
    record.update(status='MM_PROVIDER_MODULE_BUILD_COMPLETE', identity_after=after,
                  tools_after=tools(recipe), source_files_verified=len(files), preserved_artifacts_unchanged=True)
    ns['atomic_json']('result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(receipt/'result.json')}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record['status'] = 'INCOMPLETE_CHILD_RETAINED' if record['status'] == 'INCOMPLETE_CHILD_RETAINED' else 'FAILED_OR_INCOMPLETE'
            record['error'] = repr(error)
            ns['atomic_json']('result.json', record)
        raise
