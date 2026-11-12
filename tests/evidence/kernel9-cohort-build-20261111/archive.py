"""Audit saved kernel9 build records and preserve their exact provenance."""
from pathlib import Path
import base64,gzip,hashlib,json,subprocess
R=Path('/home/eric/vm/vm-shared/kdlock-main')
C=Path('/tmp/kdlock-kernel9-build-collection-20261111-01')
P=C/'payload'
D=R/'tests/evidence/kernel9-cohort-build-20261111'
assert not D.exists()
sha=lambda b:hashlib.sha256(b).hexdigest()
index=json.loads((C/'copy-index.json').read_text())
transport=json.loads((C/'transport.json').read_text())
assert len(index['files'])==len(transport['files'])==53
assert index['raw_bytes']==65113715 and sha((C/'transport.json').read_bytes())==index['transport_sha256']
for row,wire in zip(index['files'],transport['files']):
 raw=(P/row['path']).read_bytes()
 assert row['path']==wire['path'] and base64.b64decode(wire['data'],validate=True)==raw
 assert (len(raw),sha(raw))==(row['bytes'],row['sha256'])
 assert row['identity_before']==row['identity_after']==wire['identity_before']==wire['identity_after']
result=json.loads((P/'receipts/build-01/result.json').read_text())
identity=json.loads((P/'receipts/build-01/final-identity.json').read_text())
plan=json.loads((P/'input/plan.json').read_text())
assert result['status']=='KERNEL9_BUILD_AND_LINKED_IDENTITY_COMPLETE'
assert result['selected_commit']=='6e486ecec398111fb5d5e30ffc76495f32f557b7'
assert result['kernelrelease']==identity['kernelrelease']=='7.0.0-38-kdrebuild9'
assert identity['build_id']=='8198ffae09db584dce9b71d92b5743a4146ba80a'
assert len(result['commands'])==12 and all(x['returncode']==0 for x in result['commands'])
for row in result['commands']:
 log=P/'receipts/build-01'/(row['label']+'.log')
 assert (log.stat().st_size,sha(log.read_bytes()))==(row['log_bytes'],row['log_sha256'])
for name in ['source','protected','boot','tools','input_pins']:
 assert result[name+'_before']==result[name+'_after']
assert result['identity_after']['release']=='7.0.0-38-kdlock1' and result['identity_after']['taint']=='0'
assert result['identity_after']['boot']=='f1442f01-e060-46fa-a480-da508d7ce8a9'
assert not result['identity_after']['busy'] and not result['identity_after']['dthreads']
assert result['installed']==result['booted']==result['behavioral_test_performed']==False
assert [n for n in plan['package_files'] if plan['package_files'][n]!=plan['prior_package_files'][n]]==['kernel/mutex.c']
assert len(plan['package_files'])==78
assert sha((P/'source/mutex.c').read_bytes())=='014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564'
for name,row in identity['files'].items():
 if name!='vmlinux':assert (len((P/'build'/name).read_bytes()),sha((P/'build'/name).read_bytes()))==(row['bytes'],row['sha256'])
assert sha((P/'build/kernel/kdlock/kernel/mutex.o').read_bytes())==result['focused_object']['sha256']
warnings={k:len(v) for k,v in result['diagnostics'].items()}
assert warnings=={'kernel':22,'mutex-object':0,'nls':0,'olddefconfig':1}
D.mkdir();copies=[]
def copy(p,name):
 p=Path(p);assert p.is_file() and not p.is_symlink()
 before=p.stat();raw=p.read_bytes();after=p.stat()
 assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 compress=len(raw)>=65536 and p.suffix not in ('.gz','.o','.elf','.ko')
 stored=gzip.compress(raw,compresslevel=6,mtime=0) if compress else raw
 name=str(name)+('.gz' if compress else '')
 target=D/name;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_bytes(stored)
 read=target.read_bytes();assert (gzip.decompress(read) if compress else read)==raw
 copies.append({'source':str(p),'path':name,'raw_bytes':len(raw),'raw_sha256':sha(raw),'stored_bytes':len(stored),'stored_sha256':sha(stored),'gzip':compress})
def tree(root,prefix):
 root=Path(root)
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():copy(p,Path(prefix)/p.relative_to(root))
tree(C,'collection')
tree('/tmp/kdlock-kernel9-build-controls-20261111','controls')
tree('/tmp/kdlock-kernel9-cohort-build-20261111','source-build-preparation')
tree('/tmp/kdlock-kernel9-private-rwsem-preparation-20261111-01','unrun/private-rwsem-preparation')
tree('/tmp/kdlock-kernel9-install-preparation-20261111','unrun/install-preparation')
for name in ['kdlock-kernel9-build-preflight-20261111.py','kdlock-kernel9-stage-build-20261111.py','kdlock-kernel9-collect-build-20261111.py']:
 copy(Path('/tmp')/name,Path('helpers')/name)
copy(__file__,'archive.py')
report={'status':'SAVED_BUILD_RECORDS_AND_TRANSPORT_VERIFIED','runtime_validation':'blocked_by_platform_content_review','kernel_build_status':result['status'],'command_returncodes':[x['returncode'] for x in result['commands']],'source_commit':result['selected_commit'],'linked_build_id':identity['build_id'],'build_receipt_sha256':sha((P/'receipts/build-01/result.json').read_bytes()),'raw_guest_files':53,'raw_guest_bytes':65113715,'protected_inputs_unchanged':True,'normal_boot_unchanged':True,'no_install_boot_or_runtime_test':True,'warnings':warnings,'kernel_elf_retained_on_guest':{'path':identity['build']+'/vmlinux',**identity['files']['vmlinux']},'project_code_or_tests_executed_on_source_host':False}
(D/'audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
(D/'copy-index.json').write_text(json.dumps({'files':copies,'raw_bytes':sum(x['raw_bytes'] for x in copies),'stored_bytes':sum(x['stored_bytes'] for x in copies),'omitted_files':[]},indent=2,sort_keys=True)+'\n')
(D/'README.md').write_text('''# Kernel9 writer-cohort correction: build result and runtime block

Corrected core `6e486ece` compiled and linked successfully as
`7.0.0-38-kdrebuild9`, Build ID
`8198ffae09db584dce9b71d92b5743a4146ba80a`. The changed mutex object, full
kernel image and single NLS module all returned zero. All twelve recorded
commands completed; the outer observer returned zero after 397.35 seconds.
Kernel9 was not installed, booted or runtime-tested.
[Build receipt](collection/payload/receipts/build-01/result.json.gz),
[linked identity](collection/payload/receipts/build-01/final-identity.json),
[saved-byte audit](audit.json)

Only `kernel/mutex.c` differs across the 78 core inputs from kernel8. Cohort
await validates the exact published batch identity and permits its predecessor
to initialize that storage. The prepublication initialized checks and ordinary
sleepable rejection remain, with existing selection, physical ownership and
retirement checks intact. The linked await branch selects the identity check
at `0xffffffff8150b202`; success continues at `0xffffffff8150b092`, beyond the
ordinary initialized-byte rejection. Acquire still checks initialized before
calling enqueue. This is source/disassembly evidence, not executed queue
ordering or a deterministic reproduction of the failed timing window.
[Changed source](collection/payload/source/mutex.c),
[linked await](collection/payload/receipts/build-01/kd_mutex_await-disassembly.log),
[linked acquire](collection/payload/receipts/build-01/kd_mutex_acquire-disassembly.log),
[earlier failure and source review](../kernel8-mm-step-failure-20261111/README.md)

The independent source/output tree is
`/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01/{source,build}`. It copied
the already integrated kernel8 source and changed only the reviewed mutex
file; the installer was not reapplied. The config remained SHA-256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The focused object took 52.81 seconds; bzImage took 296.54 seconds; NLS took
4.02 seconds. These are build durations, not lock performance measurements.

The mutex-object and NLS logs contain no diagnostic records. The kernel log
retains 22 warnings: one maple-tree frame warning, one unused-variable warning
and twenty fortify fixture diagnostics. Olddefconfig retains one Kconfig
multiline-string warning. None is removed or called a test pass.
[Exact diagnostics](collection/payload/receipts/build-01/result.json.gz)

Before and after checks retain kernel8's 16 output identities, all 78 core
files, eight integration files, eleven native MM bodies and the normal source,
boot/default files and module namespaces. The guest stayed on normal
`7.0.0-38-kdlock1`, boot `f1442f01-e060-46fa-a480-da508d7ce8a9`, taint 0.
Final workload and D-state lists were empty. The build ended with
40,974,196,736 bytes free on the output disk. The failed-run snapshot and
existing recovery tag were verified on all three disks before the build.

Runtime validation is **blocked**. Platform content review stopped the
delegated rwsem module/build-and-run helper preparation as a possible
cybersecurity risk before any VM command from that task. The task was not
retried or recreated through another route. The separately reviewed kernel
build was already running and was allowed to finish. No private fixture module
build/load, corrected-kernel boot or additional mmap workload followed.
[Platform review stop](controls/platform-review-stop.json)

The earlier exact 143-file private-rwsem source preparation remains unrun with
fresh runtime bindings absent. The install-only draft is incomplete, unpeered
and unconditionally refuses dispatch; missing dependencies and source work are
listed in its status. Neither preparation establishes validation. The next
intended runtime scope was the existing private rwsem fixture only; it would
exercise cohorts and lifetimes but would not force this race deterministically.
[Unrun private preparation](unrun/private-rwsem-preparation/README.md),
[incomplete install draft](unrun/install-preparation/STATUS.md)

All 53 copied guest files, their complete transfer, source/control provenance,
changed object, linked disassembly, bzImage and public certificate are retained.
The full vmlinux remains at the guest path with its exact size/hash in the linked
identity. No private signing-key bytes are copied. Larger members use lossless
gzip with raw/stored hashes. Standard-library saved-byte checks verify every
transport member, command log and protected identity; no project test ran on
the source host. [Copy provenance](copy-index.json), [checksums](SHA256SUMS)
''')
manifest=[p for p in sorted(D.rglob('*')) if p.is_file() and p!=D/'SHA256SUMS']
(D/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+str(p.relative_to(D))+'\n' for p in manifest))
print(json.dumps({'archive':str(D),'copied_files':len(copies),'stored_bytes':sum(x['stored_bytes'] for x in copies),'audit':report['status']}))
