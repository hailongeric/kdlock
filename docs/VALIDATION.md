# Validation index

Validation applies to recorded inputs and scope. Source/build identity, a
published image, entered/returned generated code, correct data, final drain and
performance qualification are separate observations. Basic plus directly affected
checks are the default; use [test selection](../tests/README.md) for commands.
This index does not claim a full suite or arbitrary-kernel equivalence.

## October 29 API implementation checkpoints

The [API checkpoint](../bench/results/10.176.26.71/tests/api-semantics-20261029/README.md)
separates the archived strict pin candidate from later integrated API sources.
At `893c16b5`, ten selected spin checks passed, with a separate shell-receipt
failure retained. At `428e068a`, basic/affected rwlock checks and the live IPI
reader probe passed and drained without JIT. At `1b186f5d`, the rwsem/config unit
group passed 7/7, runner groups passed 25 and 12 cases, the live rwsem probe passed
17 API/10 cancellation/3 publication checks, and the prepared rwsem JIT escape
completed and drained all four phases. Exact source hashes, counters and guest
paths are in the checkpoint. Thirteen evidence trees (26 tar archives) are now
preserved on the host with read-only hash and complete inventory verification;
archive integrity does not change their original verdicts.

The later `ee7ace66` mixed mutex-to-spin code passed affected fixtures after two
fixture-only corrections at `5f96dd5c`, with the original failed runs retained.
Its mixed public-spin JIT probe completed and drained all four phases. That
probe exercises successful CAS and borrowed-spin native escape; it cannot
validate failed-CAS owner transfer. The `40353f4f` live transfer attempt timed out
in setup: C took a node-less gate route, so the required queued-waiter condition
never occurred and W never started its ioctl. Normal cleanup later completed;
the failed verdict remains. The corrected `20baf5c2` probe passed actual owner
handoff, exact prefix/suffix, physical unlock ACK, C's later reacquisition and
retirement, with 10,006 competing trylocks and zero thefts. Six runner checks
passed; an initial affinity preflight refusal is retained separately. Four-family
basic checks at `5f96dd5c` subsequently completed
1,600,000 operations each with returned JIT bodies and final idle; the checkpoint
retains exact counts. The 60-point nano comparison from that frozen source
completed all ten blocks with zero return status and exact data/drain. Single-round
losses, including rwlock c01/1% at eight workers (-14.38%), require investigation;
a separate 44-observation frozen-input recheck completed. Its rwlock c01/1%
losses persisted at eight (-4.14%) and twenty (-6.12%) workers, while several
rwsem coordinates changed sign. Emitted rwlock
uncontended instructions are unchanged, but contended-reader code and subsequent
loop placement change; this is static evidence, not a measured cause.
Earlier API passes do not validate this later source, and performance neutrality
is not established. Immediate queued role exchange remains unimplemented.
RT/debug/lockdep configurations are explicitly refused by the shared build
contract. The strict selected-waiter pin candidate remains archived for its
measured contended regression; bounded-selection policy is still pending.

## Current full nano rerun

The [630-point nano rerun](../bench/results/10.176.26.71/bench/nano-cohort-20261028/README.md)
at `edf1cc06` passed all 630 measured and 630 warmup receipt/oracle checks,
including exact data, placement, frozen inputs, publication and final drain.
Of 210 KD measured points, 130 recorded returned JIT bodies and 80 remained
local NO_JIT. Each point has one measured round; no real-world API was run.
The guest remained on the recorded Linux 7 boot and finished idle. Timing
remains exploratory and does not qualify whole-kernel or MM execution.

## Rwsem reader-cohort admission

The [cross-NUMA rwsem record](../bench/results/10.176.26.71/bench/rwsem-numa-20261028/README.md)
binds source `acc4dbc2e283` to the passing affected unit fixture, including sixteen
negative mutations, and live rwsem probe. The policy delays a new writer phase
behind queued readers while preserving positive-cohort joins, exact reservations
and local reader execution. The fixture covers the empty-reader-queue wake and
full-barrier ordering; it does not establish global starvation freedom.
Four-family basic checks passed with returned JIT bodies and final drain;
two read-only and four ordinary-writer mixed controls also passed.
The single-round throughput observations are exploratory, and the earlier MM
results do not qualify this source or its changed admission policy.

## Linux 7 functional port

The [port receipt](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
binds authenticated Ubuntu `linux=7.0.0-38.38`, upstream 7.0.14 content and custom
release `7.0.0-38-kdlock1`. Its schema-2 identity distinguishes source, output,
installed files and running policy. Build ID:
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`.

Initial unsigned-module/signing and first-boot failures remain recorded. Signing
repair and the subsequent clean boot passed. Eight Native/TCLock controls and
separate OUTER-mutex/spin native-escape probes validated their declared data,
original-task continuation, flags and retirement scopes.

The later [normal-boot basic controller](../bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
passed on boot `15dc5977-59d3-4471-a196-d71f03f450ed`. Each case used sixteen
workers and completed 1,600,000 correct operations:

| Family | Preset | Matched JIT entries/completions |
| --- | --- | ---: |
| Spin | c01 | 1,597,271 |
| Public mutex | c01 | 1,587,779 |
| Rwlock | c01, 20% writes, post4 | 26,269 |
| Rwsem | c16, 100% writes, post4 | 1,573,729 |

All cases retired normally with zero frames, source modules and writers. The
offline audit verified 2,112 archive files, 1,286 source-manifest entries,
eighteen binary entries, 22 control files and twelve published-image hashes.
Taint changed from clean 0 to expected unsigned/out-of-tree 12288 after probes.
These are fixed-iteration functional checks, not throughput scores.

## Trusted ordinary translation

The [trusted-translation record](../bench/results/10.176.26.71/tests/ordinary-string-translation-20261027/README.md)
records 22 passing affected unit drivers and five MM runner drivers with 34
methods. Its executable ordinary-byte fixture covers scan, nested copy/padding
and arithmetic flags. Earlier fixture/setup and checked-analysis failures remain
retained under their original identities.

Production trusts all kernel/module source, skips semantic/context/loop-value
and entry-input proofs, and uses ordinary decoded string callees. The clobber-entry
input contract is assumed. Explicit `trusted_source=False` regression passes do
not mean those proofs ran in production.

The recorded read-only taskname functional control completed 1,600,000 correct
reads with 1,592,658 matched entries/returns, ordinary `strnlen`/`sized_strscpy`
translation, zero string-hostcall/direct-helper activity and final drain. Its
concurrent unscored MM build excludes a performance claim. The separately frozen
four-family controller and later normal-boot run retain their own scopes.

## Native shared-mm mmap writers

Normal `kdlock1` disables the mmap backend. The separate
[enabled-MM checkpoint](../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
binds `7.0.0-38-kdmm1`, Build ID
`ac9ea2ec7f24be8b910547bdfdbfb071176677e6`, with Native/KD runtime-mode identities.
Fresh API/lifetime, mapping, fault and completed-fault prerequisites passed in
both measured modes, followed by 42 shared-MM timings and normal drain. Both arms
use the same source/configuration/image and prepared binaries. Normal `kdlock1`
was restored and freshly checked afterward.

The original KD1 mapping `contention_ok` failure remains failed despite correct
operation counts. Separate normal cleanup and the subsequent diagnostic do not
promote it. The [mapping diagnostic](../bench/results/10.176.26.71/tests/linux70-kdmm1-mapping-diagnostic-20261027/README.md)
preserves the exact blocked-state/call-chain witness, unstable brackets, six
functional cases and nine negative controls. No witness or ownership probe was
removed to hide that failure.

The [shared-MM result](../bench/results/10.176.26.71/bench/catalog-linux70-mm-shared-20261028/shared-mm/README.md)
is exploratory and below Native at all 21 counts. Correctness and completed
measurement do not establish parity, full Linux semantics or kernel-wide support.
Native MM algorithms and original-task execution remain unchanged.

## Opt-in module-owned mapping and faults

The separately frozen [private-MM campaign](../bench/results/10.176.26.71/bench/catalog-linux70-mm-trusted-20261027/README.md)
completed 21 independent-mm mappings and 63 private-backing fault cycles on
`kdlock1`. The actual mmap lock remains Native. The
[mapping/fault contract](design/mmap_fault.md) distinguishes backing references,
RETRY/NOWAIT/COMPLETED ownership and original-task callbacks from actual mmap-lock
substitution. These results do not validate a generic actual-backend fault driver.

## Completed single-round catalog

The [canonical coverage index](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
selects 52 complete lock/API configurations: 29 checked-source / 1,827 points,
22 trusted-source / 1,386 points, and one prepared / 63 points. The separate MM
suites add 126 points: **3,402 selected observations**, with no pooled rates.
Its evidence index binds 402 files across plans, tables, audits and receipts.

The [trusted completed-subset audit](../bench/results/10.176.26.71/bench/catalog-linux70-trusted-20261028/AUDIT.md)
passed source/binary, data, publication, retirement and host checks for all 22
full workloads. KD records 214 returned-JIT and 248 successful local points;
755,527,522 entries equal returns. The eight xattr profiles are local by design.

The [prepared mixed-taskname audit](../bench/results/10.176.26.71/bench/catalog-linux70-taskname-prepared-20261028/AUDIT.md)
passed for all 63 points: 42 controls, six KD returned and fifteen KD local,
with 99,339 matching timed entries/returns. Each KD point completed existing
ordinary-callee learning before timing and retained an unchanged NORMAL image.

All timing remains exploratory under the authorized CPU63 auxiliary-worker policy.
Fixed 2 GHz readbacks, sampled effective-frequency counters and endpoints do not
supply strict qualification, continuous health coverage or repeat variance.

## Retained failures and limits

| Attempt | Preserved outcome |
| --- | --- |
| Earlier checked taskname-w00 | Two successful controls, one failed KD preparation and sixty unattempted points |
| Original trusted taskname-w20 | 23 valid points, one timed KD8 failure with one JIT entry/zero returns, 39 unattempted points |
| [Telemetry namespace preflight](../bench/results/10.176.26.71/tests/linux70-telemetry-namespace-20261028/README.md) | Zero timed points; stale stop-marker collision; later campaign-qualified lifecycle checks passed without deleting the old marker |
| [Strict taskname functional control](../bench/results/10.176.26.71/tests/taskname-w20-preparation-20261028/README.md) | Correct data and returned preparation, but measured zero JIT entries/returns; extra `--require-jit` verdict remains FAILED / NO_JIT |
| Initial enabled-MM contention check | Failed exact witness; cleanup/diagnostic and fresh later prerequisites are separate |

Only the new prepared cohort restores the existing helper-wave setting; it does
not change translation, ownership or acceptance thresholds. No failed point is
silently retried or overwritten. Full-suite, arbitrary-source equivalence,
whole-kernel/ww_mutex support and mitigation coverage remain open. RT/debug/lockdep
configurations are explicitly refused, not pending support milestones.

## Historical evidence

Earlier mutex layouts, rwsem acceptance, helper-service/native-escape studies,
branch consolidation and Linux 6.1 validation retain source-specific outcomes in
[history](history/README.md) and result directories. The complete pre-cleanup
validation chronology remains available at its fixed Git checkpoint. An old pass
is not inherited by a new source, topology, call shell or instrumentation mode.
