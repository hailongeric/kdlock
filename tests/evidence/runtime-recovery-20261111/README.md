# Exact recovery after live2 compilation failure, 2026-11-11

Status: **the approved exact recovery completed and ordinary unload was
verified.** This is recovery evidence for the
[retained first-image compilation failure](../runtime-compilation-20261111/README.md),
not a successful compiler/JIT run. No image, producer or publication receipt was
fabricated to recover that failure.

The unchanged running kernel is `7.0.0-38-kdrebuild2`, boot
`dea66234-7f70-4e5b-acb6-40a6f2884919`. The relevant immutable source snapshot remains
`live2-2cc70fce-01a1bc4f/input` under
`/mnt/kdlock-builds/kdlock-main-work`. The source module/kernel/config identities
are the ones in the linked failed-attempt and kernel2 build/boot records.

## Actual assessment, then explicitly approved execution

[The assessment](recovery-assessment-01/result.json) is `READ_ONLY_RECONCILED`.
It used only public QUERY and read-only fixture status, retaining raw
[QUERY bytes](recovery-assessment-01/query-raw.bin), exact cached request/response,
saved claim and source export. It found BUILD_START operation2, sequence3,
status0, an actual empty claim and expected old image0. The unpublished phase
(loaded=false, update_started=false, committed=false) was inferred from this
actual cached command plus retained source ordering, not read from kernel memory.
The [prepared plan](prepared-recovery-plan.md) remains a proposal document; actual
execution is established separately below.

The [approved helper](approved-helper.py.txt), SHA256
`35bebf7d5951292c7509db9282384cd583e5ab41624ae3e0492ec1dc1ac65935`,
was explicitly authorized by the root controller after source review. It first
re-QUERYed and required the actual cache to remain byte-for-byte identical to the
assessment before adopting that exact exchange. It reconstructed only the
immutable exported source and actual empty claim. No LoweredImage or compiler
coverage was invented. The controller reports outer return0; that outer
observation is transcript-reported, not a separately saved outer timing log.

[The saved execution result](approved-recovery-01/result.json) records
`APPROVED_EXACT_RECOVERY_COMPLETE`, phase `NORMAL_UNLOAD_VERIFIED`, from
2026-11-10 17:44:55.829331 to 17:44:55.881916 UTC (local date November11). Every
actual request, ioctl envelope and response is retained. Each of these returned
status0 with matching exact identities before the next command:

| Sequence | Operation | Purpose |
| ---: | --- | --- |
| 4 | ABORT | Cancel the actual unpublished reservation |
| 5 | CLAIM_END | End the exact original empty claim |
| 6 | SHUTDOWN | Actual native/image/control drain checks and source closure |
| 7 | ARCHIVE_CLAIM | Obtain the actual closed-source archival claim |
| 8 | SETTLE | Record the actual archive content identity for exact keys |
| 9 | CLAIM_END | End the actual archival claim |

The actual archival claim also has zero rows. Its retained
[archive](approved-recovery-01/shutdown-archive.json) is **6,499 bytes**, SHA256
`0e9ad9999a75678e90ada110943be3d1157143a3ad9f791268a66481e7f09795`.
The existing archive writer used exclusive creation plus file and parent-directory
fsync. SETTLE is shutdown archival settlement, separate from coverage ACK;
zero keys do not imply emitted coverage or successful JIT execution.

The helper then closed the channel after exact END, required no workers/open
locks, issued ordinary fixture `destroy`, observed runtime0, closed fixture
control and performed normal `rmmod`. The actual rmmod returned0. Saved module
readback omits `kd_runtime_fixture`, and both fixture device paths are absent.
There was no forced unload, reset, source-body replay or automatic retry.

## Post-recovery state and evidence limits

Boot and taint stayed unchanged: bootdea66234, taint **12288** (out-of-tree and
unsigned module bits). The complete before/after dmesg bytes are identical; they
are retained, not filtered into an absence-of-error summary. Unload does not
clear sticky taint or establish the clean boot required before another live run.

The later [activity receipt](approved-recovery-01/activity-after.json), timestamped
17:45:50.857819 UTC, observes module/devices absent, unchanged boot/taint and
retains the full process listing. It shows no fixture/workload/build/recovery
execution beyond the actual read-only observer. It is a later observation, not a
timeout-based drain inference. The shutdown/destroy/unload results above provide
the actual scoped completion evidence.

[Copy metadata](copied-files.json) and [the guest index](guest-index.json) bind all
raw copied receipt bytes by SHA256/size. The assessment helper, approved helper
and prepared plan are copied with their exact source-host identities. Collection
performed only saved-file reads/copies; no module, control, build, test, arm or
reboot operation was dispatched by this collector. The original compilation
failure remains failed; this recovery does not establish publication, returned
JIT body completion, acceptance T01-T56 or performance.
