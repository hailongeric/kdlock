# KD rwsem optimization validation evidence

The selected implementation with separate wait queues and a finite 16,384-probe
polling stage passed the scheduler/API probe, two basic C programs and all 44
focused workload checks. Every workload check completed correctly and drained;
all four strict JIT checks observed returned delegated writer bodies.
[validation.json](validation.json) records **PASS**, with no failed or missing
checks in this scope. Builds and live execution ran in the recovery VM at
`10.176.26.71`; the source host only replayed captured evidence for this report.

| Selected check | Result | Scope |
| --- | --- | --- |
| `xlong-probe` | PASS | Exact twelve-field scheduler/API result |
| `final-basic` | PASS | Two basic C programs |
| `final-functional` | 36/36 PASS | Native/KD, c01/c08/RCUHT, 0%/1%/20% writes, 1/8 workers |
| `final-local` | 4/4 PASS | Ordinary local KD shell, c08, 0%/20% writes, 1/8 workers |
| `final-jit` | 4/4 PASS | Outer ABI2 KD writers, c08/RCUHT, 80%/100% writes, 16 workers |

The functional and ordinary-shell controls use 100,000 iterations per worker.
The 36 functional sessions observed 343 returned JIT bodies, all in c08 at 20%
writes and eight workers; their other sessions returned none. The four ordinary
KD controls returned none. These are correctness checks with no scored
throughput. The [performance report](../../bench/rwsem-optimization-20261018/README.md)
separately covers the full rwsem grid and spinning-rwlock reference.

## Strict writer-delegation acceptance

Each strict check used 200,000 iterations per worker, completing 3,200,000
operations. Entries and matching outer-unlock completion deltas agree:

| Workload | Writes | Returned JIT writer bodies |
| --- | ---: | ---: |
| c08, 80% writes | 2,560,000 | 892,769 |
| c08, 100% writes | 3,200,000 | 3,174,542 |
| RCUHT, 80% writes | 2,560,000 | 197,319 |
| RCUHT, 100% writes | 3,200,000 | 3,182,228 |

The four checks returned **7,446,858** delegated bodies in total. Each required
a nonzero completion count, correct protected effects, reader consistency,
worker progress and final drain. A published `NORMAL` image alone would not
satisfy this acceptance check.

## Sleeping API and scheduling probe

The selected probe returned the original twelve-field payload exactly:

```text
errors=0, api_checks=8, readers_slept=2, writer_slept=1,
late_reader_slept=1, cancellation_checks=10, colocated=1, idle=1,
outer_readers_slept=2, outer_writer_slept=1,
downgrade_checks=1, publication_checks=3
```

The [probe](../../../../../tests/kernel/rwsem/README.md) retains sleeping readers,
ordinary and outer writer exclusion, late-reader blocking, same-CPU progress,
trylocks, ordinary downgrade, ten interruptible/killable cancellation cases,
exact absence of publication while readers remain, worker joins and final
count/gate/queue idleness. New assertions distinguish phase admission from
reader drainage. Its outer body executes locally without a registered image;
this probe supplies no returned-JIT evidence.

The basic checks are `basic/test_control_call` and `basic/test_daemon_policy`.
Their source manifest, command, successful log and absence of skips are
captured. No separate executable-hash manifest was captured for these two
programs; this is not a claim that the full unit suite ran.

## Earlier experiments and diagnostic profiles

The `poll-probe`, `split-probe` and `long-probe` each passed their twelve-field
checks. The rejected `grant-probe` passed its thirteen-field checks, including
the additional reader-grant assertion. Those results remain separate from the
selected implementation; passing correctness did not establish acceptable
performance. The selected code contains no asynchronous reader-grant mechanism.

`baseline-profile` and `final-profile` each completed six c01 sessions at 20%
writes and 60 workers: Native/KD, three repetitions each. Their diagnostic
status, per-session tracing restoration and 768 raw per-CPU profile hashes were
verified. Both captures are excluded from throughput scores.

## Final health and source preservation

The captured guest health receipt reports idle, unchanged boot ID
`b65f0205-c8f9-4385-8b13-039cbce243a6`, no Linux mutex imports, and no kernel faults
in **1,423 retained session logs**. Tracing ended at `nop`, with function
profiling disabled and no enabled functions. This offline validator directly
checked 61 kernel logs in the tests/metadata/profiles archives; the broader
1,423-log statement comes from the retained guest health receipt. The final
dmesg ring is retained, not a complete boot-long log.

The captured kernel is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The probe and workload receipts retain
their available kernel, topology and snapshot identities separately.

[final-source-equivalence.json](final-source-equivalence.json) verifies 112
preserved runtime files against `d2a2304`, including all 16 selected mutex files.
A separate comparison verifies 115 unchanged provider/header/translator/daemon
files against `485729f`, excluding the two changed rwsem runtime files. These
scopes overlap. All 233 frozen inputs in each final-grid and final-reference
manifest match the reviewed source tree. The
[selected-candidate review](selected-16384-review.md) records the archived
candidate, unchanged mutex protocol and retained probe assertions.

## Evidence and limits

The [archive receipt](../../bench/rwsem-optimization-20261018/archives.json)
and [performance report](../../bench/rwsem-optimization-20261018/README.md)
link the complete capture. This validation reader verifies the tests, metadata
and profiles archives against their captured compressed hashes and source/binary
manifests. Its [checker](validation-report.py) executes no captured project
source. Source-byte comparisons use the separate
[source-equivalence checker](source-equivalence.py).

`validation.json` preserves commands, return codes, raw manifest hashes,
canonical source-content IDs, caller shells, JIT counters and the health receipt.
Raw JSON hashes and canonical content IDs are different identities. These
focused results establish neither whole-kernel replacement, mmap integration,
RT/lockdep support, oversubscription safety nor throughput parity.
