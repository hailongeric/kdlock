#!/usr/bin/env python3
"""Audit saved verification receipts without executing tests or archived code."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT/'bench/tclock_compare'))
import mutex_local_study as local
from session import check_owned_caller_policy, check_kd_parameters, check_jit_evidence
from summarize import valid
from bench_runtime import require, digest, FAULT, validate_measurement


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    raw = a.raw.resolve()
    h = local.generic_helpers()

    def file(path):
        return dict(path=str(path.relative_to(raw)), sha256=digest(path), bytes=path.stat().st_size)

    def test(name):
        return raw/'tests'/('mutex-linux-local-' + name + '-20261014')

    first = test('c1-unit')
    results = h.read(first/'results.json')
    require([r['returncode'] for r in results] == [0, 0, 0, 0, 1], 'initial test history differs')
    require('Unit tests: 13 passed, 0 failed' in (first/'00.log').read_text(), 'basic/affected unit result differs')
    remaining = (first/'remaining.log').read_text()
    require('Ran 75 tests' in remaining and 'Ran 18 tests' in remaining and remaining.count('\nOK\n') == 2,
            'corrected runner/auditor checks did not pass')
    unit_groups = {}
    for stage in ('c1', 'c3', 'c4', 'c5'):
        folder = test(stage + '-unit')
        unit_groups[stage] = [file(f) for f in sorted(folder.iterdir()) if f.is_file()]
    require('Unit tests: 2 passed, 0 failed' in (test('c5-unit')/'unit.log').read_text(), 'final core/preflight failed')
    final_runner = (test('c5-unit')/'runner.log').read_text()
    require('Ran 76 tests' in final_runner and 'Ran 18 tests' in final_runner and final_runner.count('\nOK\n') == 2,
            'final runner/auditor result differs')
    live = {}
    for name in ('c1-wait', 'c1-task'):
        folder = test(name)
        result = h.read(folder/'result.json')
        require(result['passed'] and result['drained'], 'live resource probe failed')
        sources = h.read(folder/'sources.json')
        for relative, sha in sources.items():
            require(digest(folder/'source'/relative) == sha, 'changed probe source')
        identity = h.read(folder/'identity.json')
        require(digest(folder/'kdlock_km.ko') == identity['module_sha256'], 'changed probe binary')
        logs = list(folder.rglob('kernel.log'))
        require(logs and all(not FAULT.search(f.read_text()) for f in logs), 'resource probe kernel fault')
        live[name] = dict(result=result, result_file=file(folder/'result.json'),
                          sources=file(folder/'sources.json'), identity=file(folder/'identity.json'),
                          kernel_logs=[file(f) for f in logs], jit_bodies=0)
    functions = {}
    for scenario in ('nested', 'early'):
        folder = test('c5-' + scenario)
        env = h.read(folder/'environment.json')
        # Fixed-iteration functional runs have no progress collector.
        require(env['kernel_identity']['ok'] and
                env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
                env['topology']['online_cpus'] == list(range(64)) and
                env['collector_topology'] is None and
                {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split()) and
                '(voluntary)' in env['preemption'], 'functional environment differs')
        receipt = h.frozen(folder)
        plan = h.read(folder/'plan.json')
        require(len(plan) == 1, 'functional plan differs')
        path = folder/plan[0]['name']
        r = h.read(path/'session.json')
        require(all(r.get(k) == v for k, v in plan[0].items()) and valid(r) and
                r['functional'] and r['scenario'] == scenario and r['owned_mutex_force_full'] and
                r['owned_mutex_reuse_spins'] == 32 and r['cpus'] == list(range(8)) and
                r['cpu_nodes'] == [0]*8 and r['duration_ms'] == 0,
                'functional identity/result differs')
        check_owned_caller_policy(r)
        check_kd_parameters(r['parameters'], r, r['layout']['lock_addr'])
        classified = dict(r)
        check_jit_evidence(classified)
        require(r['jit_bodies'] == r['jit_after']-r['jit_before'] > 0 and
                classified['jit_acceptance'] == r['jit_acceptance'] == 'PASS', 'functional JIT missing')
        m = h.read(path/'measure.json')
        validate_measurement(m, r, r['iterations'])
        require(m == r['measurement'], 'functional raw measurement differs')
        pub = r['published_before']
        require(pub == r['published_after'] and
                r['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'functional source did not drain')
        image = path/'workspace/daemon'/hex(pub['entry']['entry'])/str(pub['entry']['tgid'])/'asm'
        for name, sha in pub['images'].items():
            require(digest(image/name) == sha, 'changed functional JIT image')
        log = (path/'kernel.log').read_text()
        require(not FAULT.search(log) and 'reason=OWNED_CONTROL_NATIVE ' in log, 'missing checked FULL or kernel fault')
        ack = h.log_counts(log, 'kd_native stats:')
        require(ack == r['owned_full_ack'] and ack['started'] == ack['completed'] > 0 and ack['unlocks'] >= 2,
                'FULL owner ACKs did not drain')
        stats = h.log_counts(log, 'kd_mutex stats:')
        tasks = h.log_counts(log, 'kd_mutex tasks:')
        require(stats['active_waiters'] == stats['reserved_nodes'] == stats['frame_failure'] == tasks['active_tasks'] == 0 and
                stats['origin_acquires'] == stats['origin_releases'] and h.read(path/'drain.counts.json')['active'] == 0,
                'functional resources did not drain')
        if scenario == 'early':
            require(r['owned_observations']['early_releases'] > 0, 'early control not executed')
        functions[scenario] = dict(frozen=receipt, completed=m['completed'], jit_bodies=r['jit_bodies'],
            full_ack=ack, owned=r['owned_observations'], passed=True,
            artifacts=[file(path/n) for n in ('session.json', 'measure.json', 'kernel.log', 'drain.counts.json')])
    folder = test('c5-closeout')
    closeout = h.read(folder/'results.json')
    health = h.read(folder/'health.json')
    require(len(closeout) == 3 and all(r['returncode'] == 0 for r in closeout) and
            health['idle'] and health['normal_build'] and not health['project_modules'], 'closeout failed')
    require(not FAULT.search((folder/'kernel-tail.log').read_text()), 'closeout kernel fault')
    warnings = [line for line in (folder/'1.log').read_text().splitlines() if 'warning:' in line]
    normalize = lambda lines: sorted(re.sub(r'\+0x[0-9a-f]+', '+OFFSET', line) for line in lines if 'warning: objtool:' in line)
    require(normalize(warnings) == normalize(remaining.splitlines()) and len(normalize(warnings)) == 12,
            'objtool warning set differs from the initial candidate')
    manifest = h.read(raw/'bench/mutex-linux-local-c5-reuse32-screen-20261014/source-sha256.json')
    matches, changed = {}, []
    for relative, sha in manifest.items():
        path = ROOT/relative
        if not path.is_file():
            continue  # Private build copies have separate frozen evidence.
        if digest(path) == sha:
            matches[relative] = sha
        else:
            changed.append(relative)
    require(set(changed) <= {'bench/tclock_compare/README.md', 'bench/tclock_compare/mutex_local_study.py',
                             'kernel_module/owned_mutex/linux-source.json'}, 'runtime changed since acceptance')
    result = dict(schema=1, passed=True, full_suite=False, unit_receipts=unit_groups,
        initial_failure='C1 runner fixture used Path.startswith; corrected 75-test rerun passed; later C5 has 76.',
        profiler_failure='C4 mutation-marker failure caught changed ABI2 return mask; fixed before live use; repaired 17-mutation check passed.',
        unit_scope='C1 basic plus 11 affected groups; ABI4 14 mutations, delegation 22, profiler 17; C3/C4/C5 affected delta checks.',
        live_resource_probes=live, actual_jit_functional=functions,
        closeout=dict(commands=closeout, health=health, warnings=warnings,
                      artifacts=[file(f) for f in sorted(folder.iterdir()) if f.is_file()]),
        accepted_source_matches=matches, later_documentation_only_paths=changed,
        limitation='Incremental source-specific checks, not a full suite, general fairness or higher-thread acceptance.',
        auditor_sha256=digest(Path(__file__)))
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(passed=True, functional_jit_bodies={k:v['jit_bodies'] for k,v in functions.items()},
                          final_idle=health['idle'], objtool_warnings=12)))


if __name__ == '__main__':
    main()
