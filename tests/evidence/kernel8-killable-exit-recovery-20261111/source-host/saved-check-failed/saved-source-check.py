from pathlib import Path
import hashlib,json,sys
repo=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'tests/kernel'))
from disassem.wire import SourceExportLimits,WireLimits,decode_source
from disassem.session import source_export_from_frame
from run_runtime_fixture import scan_operation_calls
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
old=base/'managed-killable-live-01';raw=(old/'source-export.bin').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='d7751fd6e99af063d21f29d8cc327578f45ea912c963b31e43cbc2058b996a89'
original=(old/'result.json').read_bytes();assert hashlib.sha256(original).hexdigest()=='ffd70cfe0dbc43302a9e49d3bea79d1c5467f144db714e504bee1982452ecac7'
v=json.loads(original);sizes=v['sizes'];limits_bytes=(base/'managed-killable-input-01/limits.json').read_bytes();assert hashlib.sha256(limits_bytes).hexdigest()=='23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8';b=json.loads(limits_bytes)
limits=WireLimits(b['frame_capacity'],b['wire_rows'],b['wire_version_bytes'],b['wire_symbol_bytes'],b['wire_artifact_bytes'])
frame=decode_source(raw,SourceExportLimits(3+b['dependency_page_limit'],b['entry_capacity'],b['total_source_byte_limit']),limits)
exported=source_export_from_frame(frame,raw);body_rows=frame.regions[:3];assert len(body_rows)==3 and len({start for start,data in body_rows})==3
named={}
for (name,key),(start,data) in zip((('killable','killable_size'),('writer','writer_size'),('step','step_size')),body_rows):
 matches=[r for r in exported.snapshot.regions if r.start==start and r.data==data]
 assert len(data)==sizes[key] and len(matches)==1
 named[name]=matches[0]
assert exported.snapshot.regions[0].start==0xffffffff8276eee0 and len(exported.snapshot.regions[0].data)==2
assert exported.snapshot.regions[0] is not named['killable'] and exported.snapshot.regions[1] is not named['writer']
out.mkdir(mode=0o700);snapshot,roots,calls,indirect=scan_operation_calls(exported,'/usr/bin/objdump',out,60)
proof={}
for index,(name,region) in enumerate(named.items()):
 lock_calls=[c for c in calls if region.start<=c['site']<region.end and c.get('operation')=='lock']
 assert len(lock_calls)==(0 if name=='step' else 1)
 proof[name]={'provider_row':index,'start':region.start,'length':len(region.data),'sha256':hashlib.sha256(region.data).hexdigest(),'lock_calls':lock_calls,'post_CALL_roots':[c['site']+c['length'] for c in lock_calls]}
old_metadata=(old/'source-metadata.json').read_bytes();assert hashlib.sha256(old_metadata).hexdigest()=='3aa79275fef3109dfc8d41deae8475a9fcd112454a9e6cee1af444291307800b'
previous=json.loads(old_metadata);assert calls==previous['calls'] and list(roots)==previous['roots'] and list(indirect)==previous['near_indirect_call_sites']
assert len(roots)==2 and exported.expected_old_image_identity==0
assert hashlib.sha256((old/'source-export.bin').read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()
result={'scope':'Saved bytes only; unloaded original module identities grant no current execution authority. No kernel/JIT/syscall/image operation.',
        'raw_source_sha256':hashlib.sha256(raw).hexdigest(),'original_failure_sha256':hashlib.sha256(original).hexdigest(),
        'named_source_spans':proof,'roots':list(roots),'calls':calls,'indirect':list(indirect),'current_image_at_original_export':0}
(out/'named-source-proof.json').write_text(json.dumps(result,sort_keys=True,indent=2)+chr(10));print('SAVED_SOURCE_NAMED_SPANS_COMPLETE 3')
