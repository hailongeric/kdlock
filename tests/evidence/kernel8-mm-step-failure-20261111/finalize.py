"""Finish the saved failure archive and reconcile current evidence descriptions."""
from pathlib import Path
import gzip,hashlib,json
R=Path('/home/eric/vm/vm-shared/kdlock-main')
D=R/'tests/evidence/kernel8-mm-step-failure-20261111'
ix=json.loads((D/'copy-index.json').read_text())
for name in ['kdlock-kernel8-mm-step-failed-raw-evidence-20261111.md','kdlock-kernel8-mm-step-failed-raw-audit-20261111.json','kdlock-kernel8-mm-step-failed-raw-audit-20261111.py']:
 p=Path('/tmp')/name;raw=p.read_bytes();compressed=len(raw)>=65536
 dest=D/'review'/(name+('.gz' if compressed else ''));assert not dest.exists()
 stored=gzip.compress(raw,compresslevel=6,mtime=0) if compressed else raw
 dest.write_bytes(stored)
 ix['files'].append({'source':str(p),'path':str(dest.relative_to(D)),'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'stored_bytes':len(stored),'stored_sha256':hashlib.sha256(stored).hexdigest(),'gzip':compressed})
ix['raw_bytes']=sum(x['raw_bytes'] for x in ix['files']);ix['stored_bytes']=sum(x['stored_bytes'] for x in ix['files'])
(D/'copy-index.json').write_text(json.dumps(ix,indent=2,sort_keys=True)+'\n')
(D/'README.md').write_text('''# Kernel8 five-region mmap attempt, failure and recovery

The single five-region attempt **failed** during its third syscall round.
The first kernel BUG is `kernel/kdlock/kernel/jit.c:855`,
`kd_jit_acquire+0x45d/0x4b0`, with writer acquisition returning `-EBUSY`.
Repeated `exit.c:916` lifetime assertions then reached the kernel oops limit
and panicked the guest. The timeout and panic remain failures.
[First fault](controls/serial-full-01/first-diagnostic.txt),
[failed runner result](collections/recovered/payload/runtime/result.json.gz)

This attempt added the actual `do_mmap` span to the prior four-region profile:
five regions and 3,214 source bytes. It used kernel8 core `0d42063e`, Build ID
`a33dd4d11d0f0c6649107507e685b6e86e716c1a`, boot
`4a98638f-c01c-4fc9-8de8-69a74346aa0f`, frozen source `0798c1ab`, and the
unchanged signed provider, client and runner. Configuration SHA-256 is
`3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1`.
The accepted 16 KiB native-helper premise and conditional 44,024-byte control
estimate remained explicit assumptions; complete AUX coverage is unproved.
[Activated input](collections/recovered/payload/input/host-config.json),
[source review](../kernel8-mm-source-review-20261111/README.md)

Two rounds have complete receipts: 128 worker iterations, 384 successful mmap
calls and 256 successful munmap calls. The saved binary prefix has 19,248
events without overflow. It proves 81 mmap entries reaching the typed writer
query, 81 successful query results, and exact native handback at the post-query
cursor when image 1 lacks that entry. The 81 following entry attempts are
lookup refusals, with no executed fragment. Another 45 executed munmap prefixes
hand back at the staged `do_vmi_munmap` callee entry.
[Raw audit and exact lifetime joins](review/kdlock-kernel8-mm-step-failed-raw-evidence-20261111.md)

Two images were constructed and published. Image 2 admits the post-query
cursor, but no saved execution uses it, and no saved handback reaches
`__get_unmapped_area`. Publication does not establish that deeper execution.
Both coverage ACK replies contain zero keys. Forty-five distinct direct-CALL
facts were claimed; no shutdown archive, SETTLE or final ordinary cleanup
receipt exists. The third-round amount of completed work is unknown. Full
protected-MM completion and performance remain unestablished.

Source review found a concrete race: after W publishes its writer-cohort node,
C may select it and initialize W's exact reserved batch before W enters await.
The old post-publication initialized check then wrongly returns `-EBUSY`.
Commit `6e486ece` validates the exact batch identity during cohort await and
retains both prepublication freshness checks, selection/result ordering and
all physical-owner/retirement checks. Independent static review found no
issues. This archive contains no executed test of that correction.
[Source diagnosis](review/kdlock-kernel8-mm-step-acquire-refusal-review-20261111.md),
[independent review](review/kdlock-mutex-cohort-await-independent-review-20261111.md),
[exact patch](review/kdlock-mutex-cohort-await-fix-20261111.patch)

The first fault's canonical source-state address is absent from the retained
events. Its node/acquisition addresses occur only in two earlier, retired
incarnations with different source states. Those reused addresses cannot prove
the failed request's queue order. The race is source-proved; attribution of
this run to that exact interleaving remains an inference.

After SSH became unavailable, the complete existing serial log and current
boot slice were preserved. Snapshot `kd-mm-step-failed-20261111-01` retained
failed RAM and all three disks alongside the existing recovery snapshots.
One QEMU reset then recovered normal `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`f1442f01-e060-46fa-a480-da508d7ce8a9`, taint 0, with no workload or D-state
task observed. The one-shot boot entry is empty. Reset recovery is not
ordinary drain or successful settlement of the failed run.
[Failure snapshot](controls/failure-snapshot-01/result.json),
[reset receipt](controls/recovery-reset-02/result.json),
[normal recovery check](controls/recovery-postboot-01/result.json)

The archive preserves the failed configuration assertion, diagnostic parse
error, diagnostic process-list timeout, SSH collection timeout and first
pre-reset snapshot-name assertion. That first reset helper stopped before
issuing a reset; the corrected helper verified the actual three-disk recovery
tag. An earlier operator agent turn was stopped by platform content review;
it was not retried. Its interruption record distinguishes the completed VM
preparation commands from the unissued remaining step.
[Operator interruption](controls/operator-interruption.json)

All 224 recovered guest files and their complete transfer are retained,
alongside source-host controls, both collection attempts, review artifacts and
the exact before/after mutex source. Large files use lossless gzip with raw and
stored hashes. The saved-byte audit checks transport membership, cumulative
events and exact identity joins using only the standard library. These archive
checks execute no project code or workload on the source host.
[Copy provenance](copy-index.json), [archive audit](archive-audit.json),
[checksums](SHA256SUMS)
''')
# Keep maintained descriptions current without changing older receipt verdicts.
p=R/'README.md';s=p.read_text();needle='The current source adds ordinary sleepable rwsem read/write operations and\n'
assert s.count(needle)==1
s=s.replace(needle,'''The subsequent [five-region mmap attempt](tests/evidence/kernel8-mm-step-failure-20261111/README.md)
completed two rounds and 81 typed queries, then failed with a writer-acquire
`-EBUSY` BUG and kernel panic. Its state and receipts are preserved; the guest
was recovered to the normal kernel. Source correction `6e486ece` removes a
post-publication cohort-batch refusal while retaining exact identity and
lifetime checks. Static review is complete; corrected-kernel validation is
separate from the failed run.

'''+needle);p.write_text(s)
p=R/'docs/design/kdlock_redesign/04_evidence_and_reconciliation.md';s=p.read_text();needle='## 1 Active authority and scope\n';assert s.count(needle)==1
s=s.replace(needle,'''The subsequent [five-region attempt and recovery](../../../tests/evidence/kernel8-mm-step-failure-20261111/README.md)
records two completed rounds, 81 typed queries and exact post-query lookup
handback. Image 2 was published, but its execution is absent from the saved
prefix. The third round failed with writer-acquire `-EBUSY` at `jit.c:855`,
followed by a kernel panic. No final drain or settlement is inferred. Failed
RAM/disks and complete serial were preserved before reset recovery to the
normal kernel. Source correction `6e486ece` retains prepublication freshness
and exact batch identity while permitting predecessor initialization before
cohort await. Static review is complete; this failure archive does not validate
the correction or establish the failed request's exact queue interleaving.

'''+needle);p.write_text(s)
p=R/'kernel/integration/RWSEM.md';s=p.read_text()
s=s.replace('| Proposed next input | Exact kernel8 scope | Expected progress, conditional on actual captured bytes and construction |','| Source input | Exact kernel8 scope | Reached or proposed progress |')
s=s.replace('These are proposed inputs, not an activated profile. The saved `do_mmap` ELF\n','''The five-region `do_mmap` profile was activated in a later
[failed attempt](../../tests/evidence/kernel8-mm-step-failure-20261111/README.md).
It recorded 81 successful typed queries and exact post-query native handback;
the published reentry image has no saved execution. A third-round writer-acquire
`-EBUSY` BUG led to panic and reset recovery. Source correction `6e486ece`
addresses a post-publication cohort-batch race; the failure's exact queue
interleaving is unrecorded. `do_vmi_munmap` expansion remains proposed.
The saved `do_mmap` ELF
''')
s=s.replace('Under the same unmeasured native/IRQ premises, the proposed five-region\n','Under the same unmeasured native/IRQ premises, the attempted five-region\n')
p.write_text(s)
# Validate every copy, complete recovered transport and source-fix identities.
for row in ix['files']:
 stored=(D/row['path']).read_bytes();raw=gzip.decompress(stored) if row['gzip'] else stored
 assert (len(stored),hashlib.sha256(stored).hexdigest())==(row['stored_bytes'],row['stored_sha256'])
 assert (len(raw),hashlib.sha256(raw).hexdigest())==(row['raw_bytes'],row['raw_sha256'])
audit={'status':'SAVED_ARCHIVE_BYTES_VERIFIED','copied_files':len(ix['files']),'raw_bytes':ix['raw_bytes'],'stored_bytes':ix['stored_bytes'],'omitted_files':[],'project_code_executed':False,'runtime_verdict':'failed_retained','ordinary_drain':False,'fix_runtime_validation_in_this_archive':False}
(D/'archive-audit.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
(D/'finalize.py').write_bytes(Path(__file__).read_bytes())
files=[p for p in sorted(D.rglob('*')) if p.is_file() and p!=D/'SHA256SUMS']
(D/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(D))+'\n' for p in files))
print(json.dumps(audit))
