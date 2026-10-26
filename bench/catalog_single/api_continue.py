#!/usr/bin/env python3
"""Guest-only continuation of unchanged API plans after drained helper refusal."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

HELPER_FAILURE = 'helper learning did not establish complete delegation within configured waves'


def idle(ns):
    ns['idle']()
    for name in ('real_api', 'tclock_backend_km', 'tclock_mutex_backend_km',
                 'tclock_rwlock_backend_km', 'tc_allocator_guard'):
        assert not Path('/sys/module', name).exists(), 'remaining module: ' + name


def permitted_failure(error, record):
    return (getattr(error, 'status', None) == 'PREPARATION_FAILED'
            and not getattr(error, 'unsafe', True) and str(error) == HELPER_FAILURE
            and record.get('kind') == 'xattr' and record.get('arm') == 'kdlock'
            and record.get('execution_status') == 'PREPARATION_FAILED'
            and record.get('drained') is True and 'measurement' not in record
            and 'cleanup_error' not in record)


def main(request):
    argv = request['argv']
    runner = Path(argv[0]).resolve()
    assert runner == Path('/root/host_fs/kdlock/bench/real_api/run.py')
    out = Path(argv[argv.index('--output') + 1])
    assert out.parent == Path('/root/kdlock-evidence/10.176.26.71/bench/catalog-single-20261026')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runner.parent))
    sys.argv = argv + ([] if request['resume'] else ['--build-only'])
    ns = runpy.run_path(str(runner), run_name='catalog_api_resume' if request['resume'] else '__main__')
    idle(ns)
    frozen = json.loads((out / 'source-sha256.json').read_text())
    assert ns['sources']() == frozen, 'API source changed before continuation'
    for item in json.loads((out / 'binaries.json').read_text()).values():
        assert ns['digest'](Path(item['path'])) == item['sha256'], 'frozen API binary changed'
    plan = json.loads((out / 'plan.json').read_text())
    assert len(plan) == 63 and all(s['kind'] == 'xattr' and s['repeat'] == 0 for s in plan)
    prior = []
    if request['resume']:
        original = (out / 'records.json').read_bytes()
        backup = out / 'records-before-continuation.json'
        assert not backup.exists(), 'continuation already attempted'
        backup.write_bytes(original)
        prior = json.loads(original)
        request['prior_records_sha256'] = hashlib.sha256(original).hexdigest()
    by_name = {r['name']: r for r in prior if r.get('execution_status') != 'NOT_RUN'}
    assert set(by_name) <= {s['name'] for s in plan}
    for spec in plan:
        old = by_name.get(spec['name'])
        if old is not None:
            assert all(old.get(k) == v for k, v in spec.items()), 'original plan identity changed'
            assert old['drained'] is True
            assert old['execution_status'] == 'OK' or (
                old['execution_status'] == 'PREPARATION_FAILED'
                and old.get('error') == HELPER_FAILURE and 'measurement' not in old
                and 'cleanup_error' not in old)
    ns['write_json'](out / 'continuation-tool.json', request)
    try:
        for i, spec in enumerate(plan):
            if spec['name'] in by_name:
                print(f'{i+1}/63 RETAIN {spec["name"]}: {by_name[spec["name"]]["execution_status"]}', flush=True)
                continue
            assert not (out / spec['name']).exists(), 'unaccounted existing session'
            idle(ns)
            print(f'{i+1}/63 {spec["name"]}', flush=True)
            session = ns['SyscallSession'](out, spec)
            try:
                session.execute()
            except ns['Failure'] as error:
                if not permitted_failure(error, session.record):
                    raise
                idle(ns)
                print('  PREPARATION_FAILED; no timed measurement; drained=True', flush=True)
            else:
                r = session.record
                print(f'  {r["whole_throughput_ops_s"]/1e6:.3f} M/s; '
                      f'JIT entries {r["jit_bodies"]}, complete {r["jit_completions"]}; drained=True', flush=True)
            by_name[spec['name']] = session.record
    finally:
        records = [json.loads((out / s['name'] / 'session.json').read_text())
                   if (out / s['name'] / 'session.json').exists()
                   else by_name.get(s['name'], dict(s, execution_status='NOT_RUN', drained=False))
                   for s in plan]
        ns['write_json'](out / 'records.json', records)
    assert ns['sources']() == frozen, 'API source changed during continuation'
    idle(ns)
    ns['command'](['dmesg'], out / 'dmesg-after-continuation.txt')
    assert all(r['drained'] is True and r['execution_status'] in ('OK', 'PREPARATION_FAILED') for r in records)
    ns['write_json'](out / 'continuation-result.json', dict(
        attempted=len(records), measured=sum(r['execution_status'] == 'OK' for r in records),
        preparation_failures=sum(r['execution_status'] == 'PREPARATION_FAILED' for r in records),
        drained=True, strict_qualified=False))


if __name__ == '__main__':
    main(json.loads(sys.argv[1]))
