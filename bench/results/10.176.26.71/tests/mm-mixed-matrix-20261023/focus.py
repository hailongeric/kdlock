#!/usr/bin/env python3
"""Serial mixed-layout/native matrix and five preservation smokes; no timing."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
BASE = Path('/mnt/kdlock-builds/mm-mixed-matrix-20261023')
PRIOR = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023')
old = runpy.run_path(str(PRIOR / 'control/focus.py'))
rt, command, idle = old['rt'], old['command'], old['idle']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='focused-1')
    args = parser.parse_args()
    assert args.run.replace('-', '').isalnum()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdmm9'
    assert 'kd_mmap=on' in Path('/proc/cmdline').read_text().split()
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    idle()
    build = json.loads((BASE / 'build-1/result.json').read_text()); assert build['passed']
    assert rt.digest(PRIOR / 'build-2/result.json') == build['prior_build_sha256']
    assert rt.digest(Path(build['client'])) == build['client_sha256']
    inputs = json.loads((BASE / 'control-1/inputs.json').read_text())
    assert rt.digest(BASE / 'control-1/inputs.json') == build['inputs_sha256']
    for name, digest in inputs['files'].items(): assert rt.digest(BASE / name) == digest
    for name, digest in build['reused'].items(): assert rt.digest(Path(name)) == digest
    probes = PRIOR / 'probes-1'
    new = BASE / 'probes-1/mixed_partial'
    validators = {kind: runpy.run_path(str(path / 'receipts.py'))
                  for kind, path in [('resident', probes / 'resident_partial'), ('mixed', new)]}
    controls = {kind: runpy.run_path(str(path / 'controls.py'))['check']
                for kind, path in [('resident', probes / 'resident_partial'), ('mixed', new)]}
    shapes = list(validators['mixed']['SHAPES'])
    tasks = [(f'{route}-{shape}', [route, shape], None, 'mixed')
             for shape in shapes for route in ('native', 'mixed')]
    tasks += [(f'error-{route}-2', ['error', route, 'resident', 'middle', '2'], None, 'mixed') for route in ('native', 'kd')]
    tasks += [(f'mixed-{mode}', ['mixed', mode], None, 'mixed') for mode in ('refusal', 'cancel')]
    plans = [
        ('unmap_body', 'kd_mm_unmap_test', tasks + [
            ('resident-smoke', ['resident', 'middle'], None, 'resident'),
            ('untouched-smoke', ['middle'], None, 'partial')]),
        ('populated_unmap', 'kd_mm_populated_test', [('whole-smoke', [], 4, 'validate')]),
        ('body', 'kd_mm_body_test', [('advice-smoke', [], None, 'validate')]),
        ('fault_body', 'kd_mm_fault_test', [('fault-smoke', [], None, 'validate')]),
    ]
    out = BASE / args.run; out.mkdir()
    result = dict(passed=False, drained=False, timing=False, cases=[], native_comparisons=[],
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  kernel_identity=old['kernel_identity'].check(old['TREE'], old['BUNDLE']),
                  build_receipt=str(BASE / 'build-1/result.json'), build_sha256=rt.digest(BASE / 'build-1/result.json'))
    rt.write_json(out / 'result.json', result)
    native = {}; fd = None; messages = ''; case = None

    def logs():
        nonlocal messages
        if fd is None: return
        while True:
            try: messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError: break
        (case / 'kernel.log').write_text(messages)
        assert not rt.FAULT.search(messages), 'kernel fault: retain module and evidence'

    try:
        for family, module, cases in plans:
            idle()
            validator = runpy.run_path(str(probes / family / 'run.py'))
            command(['insmod', probes / family / 'payload' / (module + '.ko')], out / (family + '-load.log'), 30)
            for name, flags, width, check in cases:
                case = out / name; case.mkdir(); messages = ''
                fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK); os.lseek(fd, 0, os.SEEK_END)
                client = new / 'client' if check == 'mixed' else probes / (
                    'resident_partial' if check == 'resident' else 'partial_unmap' if check == 'partial' else family) / 'client'
                argv = [client, *flags] + (['--pages', str(width)] if width else [])
                command(argv, case / 'client.json', 180)
                logs(); row = json.loads((case / 'client.json').read_text()); rejected = []
                if check in validators:
                    contract = validators[check]
                    evidence = contract['validate'](row, messages)
                    rejected = controls[check](row, messages, contract['validate'])
                    rt.write_json(case / 'receipt-controls.json', dict(passed=True, rejected_corruptions=rejected))
                    if check == 'mixed' and flags[0] in ('native', 'error') and row['native']:
                        native['error' if row['injection'] else row['shape']] = row
                    elif check == 'mixed' and flags[0] == 'error':
                        contract['compare_native'](native['error'], row)
                        result['native_error_comparison'] = dict(split=2, passed=True)
                    elif check == 'mixed' and flags[0] == 'mixed' and flags[1] in shapes:
                        result['native_comparisons'].append(contract['compare_success'](native[row['shape']], row))
                else:
                    evidence = (runpy.run_path(str(probes / 'partial_unmap/receipts.py'))['validate']
                                if check == 'partial' else validator[check])(row, messages)
                assert Path('/sys/module', module, 'refcnt').read_text().strip() == '0'
                for comm in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
                    try: assert not comm.read_text().strip().startswith(('pu_r', 'pu_w', 'ub_r', 'ub_w', 'fb_r', 'fb_w'))
                    except (FileNotFoundError, ProcessLookupError): pass
                result['cases'].append(dict(name=name, passed=True, drained=True, checks=row['checks'], evidence=evidence,
                                            negative_controls=len(rejected), client_sha256=rt.digest(case / 'client.json'),
                                            kernel_log_sha256=rt.digest(case / 'kernel.log')))
                rt.write_json(out / 'result.json', result)
                os.close(fd); fd = None
                print('PASS', name, json.dumps(evidence), flush=True)
                if name == 'mixed-suffix-far': print('MILESTONE all nine mixed layouts matched native; 18 different-task removals', flush=True)
            command(['rmmod', module], out / (family + '-unload.log'), 30)
            idle()
        expected = json.loads((PRIOR / 'control/expected-guest.json').read_text())['modules']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines()) == expected
        assert len(result['native_comparisons']) == 9 and len(result['cases']) == 27
        for name, digest in build['reused'].items(): assert rt.digest(Path(name)) == digest
        text = rt.command(['dmesg'], out / 'final-dmesg.log'); assert not rt.FAULT.search(text)
        result.update(passed=True, drained=True, idle=True, new_kernel_faults=[])
    except BaseException as error:
        result['error'] = repr(error); raise
    finally:
        try: logs()
        finally:
            if fd is not None: os.close(fd)
            rt.write_json(out / 'result.json', result)
    print(json.dumps(dict(passed=True, drained=True, cases=len(result['cases']))), flush=True)


if __name__ == '__main__': main()
