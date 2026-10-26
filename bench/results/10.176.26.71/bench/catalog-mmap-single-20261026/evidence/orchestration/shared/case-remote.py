import datetime
import json
import sys
from pathlib import Path

r = json.load(sys.stdin)
sys.path.insert(0, '/root/host_fs/kdlock/bench/mmap_lock')
import paired
sys.path.insert(0, r['aggregate_source'])
import aggregate
assert paired.rt.digest(Path(aggregate.__file__)) == r['aggregate_sha256']
assert r['threads'] in list(range(1,9)) + list(range(12,61,4))
assert r['mode'] in ('native','kd')
ready, inputs = paired.readiness(Path(r['ready']))
assert ready['mode'] == r['mode'] and ready['boot_id'] == r['boot_id']
paired.writer.check.idle(Path('/root'))
out = Path(r['output']);out.mkdir()
spec = paired.specification(paired.cases_for('plain-scaling-v1').index((r['threads'], 'plain')),
                            0, r['mode'], 'plain-scaling-v1')
result = dict(passed=False, drained=False, backend=r['mode'],
              run_kind='single_aggregate_control', paired_campaign_accepted=False,
              boot_id=r['boot_id'], source_commit=r['source_commit'],
              aggregate_sha256=r['aggregate_sha256'], spec=spec)
try:
    paired.rt.command(['insmod', inputs['binaries']['payload'], 'observe=0'], out/'load.log')
    paired.check_kernel(r['mode'], r['boot_id'], loaded=True)
    paired.fault_check(out, 'after-load-dmesg')
    paired.health(0)
    result['post_setup_settling'] = paired.window.post_setup_wait()
    paired.window.check_settling(result['post_setup_settling'])
    data = paired.rt.command([inputs['binaries']['timed'], str(r['threads']), 'plain'],
                             out/'client.jsonl', timeout=120)
    rows = [json.loads(line) for line in data.splitlines()]
    result['measurement'] = aggregate.validate(rows, spec)
    result['raw'] = paired.bind(out/'client.jsonl')
    result['health'] = paired.health(1)
    paired.fault_check(out, 'before-unload-dmesg')
    paired.rt.command(['rmmod', paired.MODULE], out/'unload.log')
    paired.fault_check(out, 'after-unload-dmesg')
    paired.check_kernel(r['mode'], r['boot_id'])
    paired.common.verify_maps(inputs['files'])
    result.update(passed=True, drained=True, completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
except BaseException as error:
    result['error'] = repr(error)
    raise
finally:
    paired.rt.write_json(out/'result.json', result)
print(json.dumps(result), flush=True)
