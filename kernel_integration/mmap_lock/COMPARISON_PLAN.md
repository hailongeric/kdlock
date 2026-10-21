# Separate actual-mmap and page-fault throughput plans

Status: offline plans prepared; new payload/client validation and timing are
pending. New p95 and sampled/plain comparisons are deferred, with existing
latency evidence preserved. Missing p95 is not a throughput prerequisite.
Execution is separately scheduled in the same VM after recovery-kernel
diagnostics drain. Retain the usable recovery image/snapshot and strict host
admission and immediate endpoint checks; never replace a failed endpoint later.

## Shared candidate and validation binding

Compare Native-control (`kd_mmap=off`) with KD-local (`kd_mmap=on`) on the same
`6.1.159-kdmm1` image, using concurrent local readers and original-task writers.
Exclude TCLock MM workloads. No arbitrary MM-body delegation, all-callback
coverage or whole-kernel replacement is claimed.

| Candidate artifact | Identity |
| --- | --- |
| Build ID | `687ff5a29315d732f93a618e50ac407c794bbf9b` |
| `bzImage` SHA-256 | `cb82b0d1ccf3c2b5ce27571783fa2001d7b971d8f36ff1316c114972ff354f0d` |
| `vmlinux` SHA-256 | `7c7305c78f5466276a79e3cde4d2809dce67a9677896b30e268d8f4e3d08f236` |
| Captured manifest SHA-256 | `3243e17005ed55c83af417ed3979ca9e89c077b89fcacd99dab5ae117c06b34b` |

Use candidate source `/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux`
and bundle `/root/kdlock-kernel-baselines/mmap-kdmm1-20261021`, with the existing
exact kernel verifier. The completed
[selected correctness stage](../../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md)
has these retained receipt hashes:

| Receipt | SHA-256 |
| --- | --- |
| `native-api-3.json` | `bbb2346ce712a7a9246d6e52393676f49c35bbeff9ce49acc343e503d567f032` |
| `kd-api-1.json` | `503d8b17e861716f08500d17fed45453d5a07195a7df9c5370b4123eed80f436` |
| `native-mapping-2.json` | `f2ff05a71e34336d33ef4cb1faede1b98a9357c2726a3172bb852a52490744d0` |
| `kd-mapping-1.json` | `80f067e9eda690302927d8866b4f4b69cb113bcf04fbf041df97a2879fc94571` |
| `native-faults-2.json` | `b8df9cc7d7212602e4c956b8ce47fcc1abba810654eebf53e7791c584a70f061` |
| `kd-faults-1.json` | `d69abf254130fce75e6ab2c9f52322ea4e9e034ad16f948f3f97fd4dde3d12fc` |
| `native-completed-1.json` | `6f63906a21f38381180fde8bcd91d83f7221cb551f0ba4e5b442b434e2ce5b5b` |
| `kd-completed-1.json` | `bb0617ba2862a53f04cdcd9f1bd914cab333007b0f616fe2b8dd2a89125802b3` |

The stage's final-health SHA-256
`92483de18c7be441966a000d5e060ab0c2f9986e43e70bba30697cb60f962e99` binds the
exact 73-module set and preserved recovery. The six-group archive manifest is
`3733a6e7f3ec2b3f02474cad22d408360e36137771f017941c5f6e110582c69e`.
These receipts establish selected prior scope; every new boot needs fresh
mode/identity readiness, and new payload/client binaries need focused validation.

## Task 1: actual shared-mm mmap/munmap

Use pthreads sharing one exact mm, with descriptors, output and barriers prepared
outside timing. Each operation is read-only mmap plus munmap without touching
the mapped range. Require exact mm/lock/TGID identity, distinct worker TIDs,
maps = closes = completed, zero fault callbacks/clones/errors, complete joins
and zero live VMAs. Reuse the existing
[plain mmap loop](../../bench/mmap_writer/timed_client.c) and its
[timing oracles](../../bench/mmap_writer/timing.py); keep `observe=0`.
Replace unconditional Native-lock metadata only with the explicitly verified
candidate mode, never by relabelling a private backing lock.

The prior two mapping source manifests match at
`c1d0bb88c654e33b304054f3035feda62b4d231f096ed752f624d068a46929b0`, but the
independent payload builds differ: Native
`cdd16eb0eaf99457b5363334d8c779f487e5bad433fb2046fba214d51f14a060`, KD
`b2f310a3f4a4e41d0927d38cf091378cd164e53bbc37c11902dd8004155cde3b`.
Freeze one new payload/client pair and validate those exact binaries in both
modes, retaining the mode-specific writer-chain proof in
[mapping.py](../../tests/kernel/mmap_lock/mapping.py) and
[writer_sites.json](../../tests/kernel/mmap_lock/writer_sites.json).

## Task 2: actual-mm fault cycles

Retain the existing independent-process/mm topology. Prepare resident backing
pages and one untouched mapping per worker before the barrier. Each operation
discards PTEs with MADV_DONTNEED then reads/checks the immutable value. Require
fault callbacks = backing-reader starts = backing-reader ends = completed,
no writer/scoped-fault activity or errors, joined workers and final VMA/file
release. This measures whole fault cycles including PTE reset, not isolated
hardware-fault or lock-acquisition time, and does not create same-mm contention.

The existing [fault client](../../bench/mmap_fault/timed_client.c) provides this
loop, but the old runner's KD/TCLock arms select private backing locks and load
external providers. They cannot represent actual mmap-lock kernel modes. Add an
explicit Native-only build profile to the payload
[Makefile](../../workload_modules/mmap_fault/Makefile) and
[mapping.c](../../workload_modules/mmap_fault/mapping.c), preserving default
builds. Compile out KD/TCLock backing dispatch, reject non-Native requests and
audit undefined imports to prove no external provider dependency. Use the same
Native backing rwsem/client backend 0 in both modes, recording `kernel_mmap_mode`
separately. Load only that payload; do not invent JIT-retirement receipts.
Validate fixed-work/plain-client cases and rejected backends in both modes
before timing; prior private-lock payload passes do not cover the new build.

## Serial schedule, runner changes and throughput requirements

Each separately named task has 12 sessions: 1/16 workers × two kernel modes ×
three plain repetitions. Retain two-second work, workers 0..N−1, collector 63,
100-ms start lead, 10-ms progress observations, 256-operation publication,
32-operation stop-clock checks and 300-ms settling/peak windows. Existing clients
have no separate warmup; do not silently add one. Modes are immutable at boot:
predeclare paired boot blocks Native/KD, KD/Native, Native/KD, running each task
and count serially within a block. Keep each boot ID/order and block variation;
do not describe this as in-boot arm rotation.

Add an explicit candidate profile to the existing common runner while retaining
its recovery release/boot profile. Verify candidate identity, exact off/on boot
mode, recorded boot, voluntary preemption, dependencies, topology, module set
and unchanged host controls. Bind the applicable correctness receipts and new
binary hashes. Plain-only summaries must mark p95 and sampling-cost fields
deferred; the old summary requires both sampled/plain and must not manufacture
an absent pair. Historical sampled plans and their validation remain intact.

Focused negative checks must still reject wrong mode/kernel/modules, mismatched
mm/TID, any fault in mmap-only work, missing callback/read end, live VMA, missing
join, invalid progress and wrong CPU. Require complete business oracles and
normal unload. Report every repetition, min/max, median, explicitly defined CV,
paired ratios and conservative peak; three repetitions are descriptive, not
significance evidence. Common callback/progress overhead remains unisolated.
No timing is accepted on a failed endpoint, and these plans resolve none of the
seven mutex causes by implication.
