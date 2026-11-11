#!/usr/bin/env python3
"""VM-only corrected boundary8 and unrun linked-GS5, without rebuild/replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
OLD = BASE / 'build-01/receipts'
OUT = BASE / 'basic-continue-01'
INPUT = BASE / 'continuation-input-01'
HELPER = BASE / 'transport/build.py'
HELPER_SHA = '56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb'
FAILED_SHA = '223392b879bd1aaad6ffc3e40f322706be8bd94039abd0a50c16afe238ffa37c'
FIXED_SHA = 'a37c1e1515893bb015efecec05527ba5deb2a312669f4c12869a373eb4c6c075'
FIXED_COMMIT = '4cc53e09594efbdf9388488bde4fc507717cb260'
MANIFEST_SHA = 'f51979c2f8488407f329dbfc65dc351bc859322910fc5c6cfd71cbc1dc55f201'
STATE_SHA = '3d7738192d2c47c27981b1721e98ae7bfee558ca66cc1f558c039f195381ce72'
record = None
ns = None


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    global ns, record
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', required=True)
    parser.add_argument('--recovery-sha', required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and sha(HELPER) == HELPER_SHA, 'VM root and exact original helper required')
    ns = runpy.run_path(str(HELPER))
    g = ns['main'].__globals__
    ns['environment']()
    require(not any(name in os.environ for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONOPTIMIZE',
                                                   'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH')),
            'unreviewed compiler/Python environment override')
    old_path, old = ns['checked_json'](OLD / 'result.json', FAILED_SHA)
    require(old['status'] == 'FAILED_OR_INCOMPLETE' and
            old['error'] == "RuntimeError('source-boundary-eight failed; original output retained')" and
            old['source_git_head'] == '140aecc4f83a6b6ae6f20245234e8a63504f9210' and
            len(old['commands']) == 37 and
            all(row['returncode'] == 0 for row in old['commands'][:36]) and
            old['commands'][-2]['label'] == 'new-runner-syntax' and
            old['commands'][-1]['label'] == 'source-boundary-eight' and
            old['commands'][-1]['returncode'] == 1 and
            old['commands'][-1]['log_sha256'] == 'b3240c44fca466a05f4d125bdae353f95fb4efee41566d33f6d356a801732779',
            'exact original five-build/AST success and boundary failure required')
    prior_logs = {}
    for row in old['commands']:
        require(not Path('/proc', str(row['pid'])).exists(), 'old project child still exists')
        path = OLD / (row['label'] + '.log')
        require(sha(path) == row['log_sha256'], 'original command output changed')
        prior_logs[str(path)] = row['log_sha256']
    config_path, config = ns['checked_json'](old['config'], old['config_sha256'])
    require(config == old['arguments'], 'original config/argument bytes disagree')
    manifest_path, files = ns['checked_json'](config['manifest'], config['manifest_sha256'])
    state_path, state = ns['checked_json'](config['state'], config['state_sha256'])
    require(len(files) == state['files'] == 140, 'original140 source required')
    inp = ns['canonical'](old['source_input'])
    ns['source_files'](inp, files)
    fixed = ns['canonical'](INPUT / 'test_source_boundaries.py')
    require(sha(fixed) == FIXED_SHA, 'corrected test bytes differ')
    unused, corrected_files = ns['checked_json'](INPUT / 'source-sha256.json', MANIFEST_SHA)
    unused, corrected_state = ns['checked_json'](INPUT / 'source-state.json', STATE_SHA)
    name = 'tests/test_source_boundaries.py'
    require(set(corrected_files) == set(files) and
            [key for key in files if corrected_files[key] != files[key]] == [name] and
            corrected_files[name] == {'bytes': fixed.stat().st_size, 'sha256': FIXED_SHA} and
            corrected_state == {'files': 140, 'git_status': '', 'source_git_head': FIXED_COMMIT, 'transfer_bytes': 1535363},
            'new source must differ only in the committed boundary test')
    previous = (inp / name).read_bytes()
    a, b = b'RuntimeExit(ExitKind.LOCK_OPERATION,', b'0x1000, ExitPhase.TARGET_READY),'
    require(previous.count(a) == previous.count(b) == 1 and fixed.read_bytes() ==
            previous.replace(a, b'RuntimeExit(int(ExitKind.LOCK_OPERATION),').replace(b, b'0x1000, int(ExitPhase.TARGET_READY)),'),
            'only the exact two enum-to-wire scalar conversions are allowed')
    build_path, built = ns['checked_json'](old['build_receipt'], old['build_receipt_sha256'])
    focus_path, focused = ns['checked_json'](built['focused_receipt'], built['focused_sha256'])
    identity_path, identity = ns['checked_json'](build_path.parent / 'final-identity.json', built['final_identity_sha256'])
    source, build = ns['canonical'](built['source']), ns['canonical'](built['build'])
    outputs = {key: row['sha256'] for key, row in identity['files'].items()}
    require(len(outputs) == 16 and ns['pins'](build, outputs) == old['core_pins_before'] and
            ns['protected'](focused) == old['protected_before'] and
            ns['source_pins'](focused, source) == old['kernel_source_before'] and
            ns['boot_files']() == old['boot_before'], 'original core/source/protected/boot bytes changed')
    artifacts = {}
    for row in old['modules'].values():
        for kind in ('unsigned', 'signed'):
            item = row[kind]
            require(ns['facts'](ns['canonical'](item['path'])) == item, 'built module changed')
            artifacts[item['path']] = item['sha256']
    require(len(old['modules']) == 5 and len(artifacts) == 10 and
            ns['facts'](ns['canonical'](old['client']['path'])) == old['client'] and
            ns['client_reuse'](config['client_reuse'], inp, files, focused['identity_after']) == old['client_reuse'],
            'five actual module pairs/client reuse provenance differs')
    artifacts[old['client']['path']] = old['client']['sha256']
    before = ns['idle'](focused['identity_after'])
    recovery = ns['fresh_recovery'](args.recovery, args.recovery_sha, config['recovery_policy'])
    require(ns['available']('/') >= config['bounds']['root_floor_bytes'] and
            ns['available'](BASE) >= config['bounds']['output_floor_bytes'], 'strict current headroom below original floors')
    require(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True) == BASE, 'fresh direct-child receipt required')
    OUT.mkdir(mode=0o700)
    record = {key: old[key] for key in ('kernel_core_git_head', 'source_git_head', 'kernelrelease', 'build_receipt',
              'build_receipt_sha256', 'final_identity_sha256', 'linked_build_id', 'linked_gs_symbols', 'source_input',
              'modules', 'client', 'client_mode', 'client_reuse', 'arguments', 'config', 'config_sha256', 'signing')}
    record.update(status='PREPARED_BASIC_CONTINUATION', prior_result=str(old_path), prior_result_sha256=FAILED_SHA,
                  prior_error=old['error'], prior_logs=prior_logs, corrected_test=str(fixed), corrected_test_sha256=FIXED_SHA,
                  corrected_test_git_head=FIXED_COMMIT, corrected_manifest_sha256=MANIFEST_SHA,
                  corrected_state_sha256=STATE_SHA, commands=[], artifact_pins=artifacts, core_pins_before=outputs,
                  identity_before=before, recovery=recovery, running_candidate_proof=False,
                  scope='Only corrected boundary8 and previously unrun linked-GS5. No module/C rebuild, sign, AST replay, syscall baseline, load or boot. Original failed receipt remains unchanged.')
    g['out'], g['record'] = OUT, record
    ns['atomic_json']('result.json', record)
    bounds = config['bounds']
    deadline = time.monotonic() + 180
    python = config['tools']['python']['path']
    for name, row in config['tools'].items():
        require(Path(row['path']).resolve(strict=True) == Path(row['resolved_path']) and sha(row['resolved_path']) == row['sha256'],
                'original tool alias or bytes changed: ' + name)
    tests = 'import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); loader=unittest.TestLoader(); ' \
            'suite=loader.discover(str(root),pattern="test_source_boundaries.py"); ' \
            'assert suite.countTestCases()==8, (suite.countTestCases(),loader.errors); result=unittest.TextTestRunner(verbosity=2).run(suite); ' \
            'assert result.testsRun==8 and not result.skipped and result.wasSuccessful(); print("SOURCE_BOUNDARIES_COMPLETE 8")'
    log = ns['dispatch']('corrected-source-boundary-eight', [python, '-B', '-c', tests, str(INPUT)],
                         deadline, 60, OUT, bounds, cwd=INPUT, python_path=inp)
    require(log.read_text().splitlines()[-1] == 'SOURCE_BOUNDARIES_COMPLETE 8', 'eight corrected tests required, no skips')
    gs_path = OUT / 'gs-target.json'
    linked_gs_path = identity_path.parent / 'gs-config.json'
    linked_gs_sha = sha(linked_gs_path)
    ns['atomic_json']('gs-target.json', ns['gs_target'](identity_path.parent, identity, build))
    gs_sha = sha(gs_path)
    tests = 'import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); loader=unittest.TestLoader(); ' \
            'suite=loader.discover(str(root/"tests"),pattern="test_kernel_gs_rip.py"); ' \
            'assert suite.countTestCases()==5, (suite.countTestCases(),loader.errors); result=unittest.TextTestRunner(verbosity=2).run(suite); ' \
            'assert result.testsRun==5 and not result.skipped and result.wasSuccessful(); print("KERNEL_GS_COMPLETE 5")'
    log = ns['dispatch']('linked-gs-five', [python, '-B', '-c', tests, str(inp)], deadline, 60, OUT, bounds,
                         cwd=inp, python_path=inp, gs_config=gs_path)
    require(log.read_text().splitlines()[-1] == 'KERNEL_GS_COMPLETE 5', 'five actual linked-byte tests required, no skips')
    require(sha(gs_path) == gs_sha and sha(linked_gs_path) == linked_gs_sha and sha(old_path) == FAILED_SHA and
            sha(config_path) == old['config_sha256'] and sha(HELPER) == HELPER_SHA and sha(fixed) == FIXED_SHA and
            sha(manifest_path) == config['manifest_sha256'] and sha(state_path) == config['state_sha256'] and
            sha(INPUT / 'source-sha256.json') == MANIFEST_SHA and sha(INPUT / 'source-state.json') == STATE_SHA and
            all(Path(row['path']).resolve(strict=True) == Path(row['resolved_path']) and
                sha(row['resolved_path']) == row['sha256'] for row in config['tools'].values()) and
            sha(build_path) == old['build_receipt_sha256'] and sha(focus_path) == built['focused_sha256'] and
            sha(identity_path) == built['final_identity_sha256'], 'immutable prerequisite changed')
    for path, digest in {**prior_logs, **artifacts}.items():
        require(sha(path) == digest, 'original output changed after checks')
    ns['source_files'](inp, files)
    record['core_pins_after'] = ns['pins'](build, outputs)
    record['protected_after'] = ns['protected'](focused)
    record['kernel_source_after'] = ns['source_pins'](focused, source)
    record['boot_after'] = ns['boot_files']()
    require(record['protected_after'] == old['protected_before'] and record['kernel_source_after'] == old['kernel_source_before'] and
            record['boot_after'] == old['boot_before'], 'protected inputs changed after checks')
    record['identity_after'] = ns['idle'](focused['identity_after'])
    record['checks'] = {'new_runner_ast': 2, 'new_runner_ast_reexecuted': False, 'source_boundary_tests': 8,
                        'source_boundary_skips': 0, 'linked_gs_tests': 5, 'linked_gs_skips': 0,
                        'unselected_baseline_reexecuted': False}
    record['gs_checks'] = {'config': str(gs_path), 'sha256': gs_sha, 'linked_config': str(linked_gs_path),
                           'linked_config_sha256': linked_gs_sha, 'tests': 5, 'skips': 0, 'running_proof': False}
    record['unselected_syscall_baseline'] = old['client_reuse']['baseline']
    record['unselected_baseline_mode'] = 'prior_same_source_client_and_normal_identity'
    record['headroom_after'] = {'root': ns['available']('/'), 'output': ns['available'](BASE)}
    record['status'] = 'AFFECTED_MODULES_CLIENT_AND_BASIC_CHECKS_COMPLETE'
    ns['atomic_json']('result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(OUT / 'result.json')}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record.update(status='FAILED_OR_INCOMPLETE' if record['status'] != 'INCOMPLETE_CHILD_RETAINED' else record['status'], error=repr(error))
            ns['atomic_json']('result.json', record)
        raise
