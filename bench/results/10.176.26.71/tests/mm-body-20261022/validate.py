#!/usr/bin/env python3
"""Source-side serial correctness coordinator for the approved MM candidate."""
import argparse
import datetime
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
C = runpy.run_path(str(HERE.parent / 'serial-continuation-20261022/campaign.py'))
BASE = '/root/kdlock-evidence/10.176.26.71/tests/mm-body-20261022'
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-body-20261022'
SOURCE = '/root/host_fs/kdlock'
KERNEL = '/root/kdlock-kernel-work/mm-body-20261022/candidate-1/linux'
BUNDLE = '/root/kdlock-kernel-baselines/mmap-kdmm2-20261022'
C['boot'].__globals__['PRIOR'] = BASE + '/control'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('native', 'kd', 'recovery'), required=True)
    parser.add_argument('--run', required=True)
    a = parser.parse_args()
    assert a.run.replace('-', '').isalnum()
    local, guest = RAW / a.run, BASE + '/' + a.run
    local.mkdir()
    C['guest']('mkdir -- ' + guest, local / 'mkdir.log', 30)
    state = dict(passed=False, accepted=False, timing=False, mode=a.mode, run=a.run, results=[])
    C['save'](local / 'result.json', state)
    try:
        transition = C['boot'](a.mode, guest, local)
        state['transition'] = transition
        C['save'](local / 'result.json', state)
        if a.mode != 'recovery':
            host = C['capture'](local / 'host-functional.json')
            # Use the immutable original task set, not an expanded preflight.
            original = C['fetch']('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json',
                                  local / 'reference-host.json')
            assert C['sha'](local / 'reference-host.json') == '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
            admission = runpy.run_path(str(ROOT / 'bench/basic/run.py'))['functional_host'](
                original, host, datetime.datetime.now(datetime.timezone.utc))
            C['save'](local / 'functional-admission.json', admission)
            C['copy_in']([local / 'host-functional.json', local / 'functional-admission.json'], guest + '/', local / 'copy-host.log')
            tasks = [('api', 'tests/kernel/mmap_lock/run.py', ['--mode', a.mode])]
            if a.mode == 'kd':
                tasks.append(('body', 'tests/kernel/mmap_lock/body/run.py', []))
                tasks.append(('body-cancellation', 'tests/kernel/mmap_lock/body/run.py', ['--cancellation']))
            tasks += [
                ('mmap', 'tests/kernel/mmap_lock/mapping.py', ['--mode', a.mode,
                    '--api-result', guest + '/api/result.json', '--writer-sites', BASE + '/control/writer-sites.json']),
                ('page-fault', 'tests/kernel/mmap_lock/faults.py', ['--mode', a.mode]),
                ('completed-fault', 'tests/kernel/mmap_lock/page_fault_completed/run.py', ['--mode', a.mode]),
            ]
            for name, runner, arguments in tasks:
                print('RUN', a.run, name, flush=True)
                args = [SOURCE + '/' + runner, *arguments, '--kernel-source', KERNEL,
                        '--kernel-baseline', BUNDLE, '--output', guest + '/' + name]
                C['guest'](C['remote'](args), local / (name + '.log'), 900)
                row = C['fetch'](guest + '/' + name + '/result.json', local / (name + '.json'))
                assert row['passed'] and row['drained'] and row['boot_id'] == transition['boot_id']
                state['results'].append(dict(name=name, receipt=guest + '/' + name + '/result.json',
                                              sha256=C['sha'](local / (name + '.json'))))
                C['save'](local / 'result.json', state)
                print('PASS', a.run, name, flush=True)
        script = """import json,runpy,sys
from pathlib import Path
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as rt
root=Path('/root/host_fs/kdlock');base=Path(GUEST)
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
modules=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
expected=json.loads(Path(EXPECTED).read_text())['modules'];assert modules==expected
messages=rt.command(['dmesg'],base/'final-dmesg.log');assert not rt.FAULT.search(messages)
rt.write_json(base/'final-health.json',dict(idle=True,boot_id=BOOT,modules=modules,new_faults_in_retained_dmesg=[]))
""".replace('GUEST', repr(guest)).replace('BOOT', repr(transition['boot_id'])).replace('EXPECTED', repr(BASE + '/control/expected-guest.json'))
        C['guest'](C['PY'] + " - <<'PYG'\n" + script + '\nPYG', local / 'health.log', 120)
        state['health'] = C['fetch'](guest + '/final-health.json', local / 'final-health.json')
        state.update(passed=True, final_idle=True)
    except BaseException as error:
        state.update(error=repr(error))
        raise
    finally:
        C['save'](local / 'result.json', state)
    print(json.dumps(dict(run=a.run, mode=a.mode, passed=True, final_idle=True)), flush=True)


if __name__ == '__main__':
    main()
