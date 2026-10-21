# Pre-warmup quiescence control, 2026-10-21

Status: completed and archived. Both observed prepared gates passed; the
post-cleanup endpoint refused. No timing or performance acceptance is established.
The source checkout started clean at `e477c86`. The same VM is drained on boot
`88449cfc-cea9-4647-a294-bc601e372146`, kernel `6.1.159-kdclobber2`, with the
original 73 modules. Only the main agent edits files or executes VM checks.
Helpers review read-only and report no files touched. A read-only preflight
initially used the wrong runtime import directory and failed before inspection;
the corrected import completed the existing idle and exact-module checks.

This separate diagnostic retains the prepared client, provider, source and host
observer connections. After original check-before and translator shutdown, wait
for the unchanged full host gate and fresh guest comparison **before** releasing
one original warmup. The exact original 67 TIDs/names/affinities remain required.
Accounting scans only select capture opportunities; the existing bounded
sample-trigger policy, freshness checks, maximum four candidate captures and
120-second terminal capture remain unchanged.

After the one original warmup reply, take the required exact drained-state
snapshot and request **one immediate full post-warmup capture**. Do not wait for
another quiet sample, add a cooldown, retry a refusal or send a measurement
command. Use distinct ordered stages and fresh nonces. Check loaded placement
before warmup. Compare physical/publication state and exact counters within each
hold; across warmup permit only its exact operation and matched returned-body
counter deltas. A fully observed pre-gate refusal skips warmup and retires
normally. Coordination or lifetime uncertainty retains resources.

Record snapshot start/end, pre-capture, guest revalidation, warmup command/reply,
immediate post-request/capture, validation, cleanup and endpoint chronology.
The frozen reply reader writes `warmup.json` before returning. State snapshots,
fresh validation, control messages and guest background I/O can also cause host
activity. The pre-gate receipt stays in guest memory until the post observation;
the source supervisor retains it independently. No phase-end acknowledgement or
ordinary preparation save precedes the post request. The reused warmup-begin
host marker is only a causal lower bound, never a simultaneous clock reading.
Report actual delays/observer overhead, non-atomic reads, missed worker lifetimes
and departed accounting tails without attributing all activity to warmup.

Frozen provider, workload, client, translator and old evidence stay unchanged.
The [fixed-capture refusals](../mutex-boundary-20261021/README.md) and the
[triggered pass with failed 70-task endpoint](../mutex-boundary-trigger-20261021/README.md)
remain separate. Waiting changes admission clock history; it does not reset
heat or establish original preparation parity. All seven regression causes and
acquisition latency remain unresolved. Complete-operation p95 is separate.
Readers stay local/concurrent; mmap and page-fault tasks remain separate;
unsupported TCLock critical sections remain excluded.

## Focused validation

Implementation `7682076` synchronized while idle and verified all 3,975 tracked
file hashes. Guest `checks-1` passed serially: two rebuilt basic programs,
nine trigger tests, four reply-protocol tests, twelve pre-warmup ordering and
failure-path tests, and six unchanged recovery-gate tests. Tests ran from 104
frozen committed source files; current and retained hashes matched afterward
and final idle passed. The new integration tests exercise the actual runner
methods with a fake client, including safe pre-refusal, malformed replies,
invalid joined work, wrong placement and immediate post-capture ordering.

Read-only review caught and corrected unsafe handling of malformed warmup
replies before this test run. Such replies now retain resources as `UNDRAINED`;
they cannot cause ordinary unbind/unload. Original-reply and in-memory-validation
timestamps are recorded separately. The `client-warmup` phase marker brackets
the pre-wait plus warmup; actual command timestamps define the work interval.

## Live result and chronology

Run `mutex-prewarmup-20261021/probe-1` used supervisor `481d3dc`, a documentation
successor to tested/synchronized `7682076`. The frozen provider/client/workload
and every previous correctness, ELF and owner/ACK prerequisite were retained.
The original five workers used guest CPUs 0–4, collector 63, and the loaded
mutex remained at cacheline offset 32. The original warmup minimum was 48,000
operations per worker and one second. No timed command or rate was produced.

| Full observation | QEMU tasks | Unchanged full gate |
| --- | ---: | --- |
| Initial preflight | 70 | Refused |
| Preflight at 15 seconds | 67 | Passed |
| Prepared, before warmup | 67 | Passed; fresh guest comparison passed |
| Immediate after warmup | 67 | Passed; fresh guest comparison passed |
| After normal cleanup and final validation | 68 | Refused |

The pre-warmup hold lasted **45.362982407 seconds**, including capture and
guest revalidation. Accounting scans 5–12 were refused as candidates; scan 13
matched the exact original 67 identities. One full capture began **24.312415 ms**
after that scan began, within the existing freshness budget. No candidate full
capture was refused in this hold and no terminal retry was used. The held
client, binding, physical idle state, immutable publication, zero frames/writers
and exact counters remained unchanged. Only one original warmup followed.

That warmup completed **8,272,256 operations**, with exact call delta 8,272,256
and **54,599 JIT entries = 54,599 returns**. All five workers met the original
duration/progress requirements with correct placement and no worker/collector
errors. The address-guard delta was zero. These are joined warmup observations,
not a throughput measurement or a comparison with earlier warmups.

| Interval and clock domain | Observed duration |
| --- | ---: |
| Pre-capture full read, host | 422.394705 ms |
| Fresh pre-warmup guest validation, guest | 9.138475 ms |
| Completed pre-gate to original warmup command, guest | 11.975 µs |
| Command to original scheduled work start, guest | 50.318991 ms |
| Original work start to final worker completion, guest | 1.000091155 s |
| Final worker completion to parsed/saved original reply, guest | 1.084985 ms |
| In-memory joined-reply validation, guest | 35.379 µs |
| Required exact state snapshot before post request, guest | 1.401742 ms |
| Saved original reply to post request, guest | 1.458649 ms |
| Final worker completion to post request, guest | 2.543634 ms |
| Post-request receipt to full-capture dispatch, source host | 0.692897 ms |
| Immediate post full read, host | 257.302227 ms |
| Fresh post guest validation, guest | 7.585608 ms |
| Complete post exchange, guest | 354.542082 ms |
| Normal cleanup, guest | 456.832970 ms |
| Cleanup-end host acknowledgement to endpoint read, host | 556.009687 ms |

Source-side capture ACK to guest reply took 49.555290 ms before warmup and
59.412322 ms afterward, including retained evidence and protocol processing.
There was **no post-warmup quiet wait, sample selection or retry**. The one post
capture preceded the ordinary warmup phase-end, preparation fault/save checks
and measurement-accounting phase. The latter ran only a business check: no
`measure` command, `measure.json`, measurement record or rate field exists.
Clock domains remain separate; request/ACK brackets are causal bounds rather
than synchronized timestamps. Snapshot/file reads are non-atomic.

Normal cleanup balanced **211,473 origin acquisitions/releases**. Active
waiters, reserved nodes and active tasks were zero. Source retirement was
`state=2, modules=0, frames=0, writers=0`; final idle passed with the original
73 modules, unchanged recovery boot/kernel and no recorded per-session kernel
fault. Health validation rechecked all frozen input/harness hashes. No kernel,
snapshot, CPU placement, frequency/security or network setting was changed.

## Activity, overhead and remaining gap

There were 14 five-second accounting scans, ranging from 67 to 72 tasks. The
pre-warmup held scans observed 72 → 69 → 68 → 67. Matched worker intervals in
that hold contain 1.572644 ms runtime, zero recorded read-byte delta and 471,040
written bytes. These are only observed intervals: first samples can contain
earlier work, and departed worker tails are missing. They do not identify the
cause of preparation or background I/O.

**The last accounting scan preceded the pre-warmup full capture. There are no
accounting samples during or after warmup.** Consequently this probe cannot
attribute worker CPU/I/O to warmup or rule out workers created and destroyed
between observations. The immediate full capture saw the original 67 tasks,
but the later endpoint saw worker **451627**, pinned to host CPU 63, with no
start-tick/accounting sample. The last accounting count of 67 is not the
68-task endpoint. Original warmup reply-file I/O, state reads, fresh validation,
business checks, retirement, control traffic and guest background I/O all
intervene; the evidence does not identify which created the endpoint worker.

The observer consumed 1.956363983 CPU seconds over 69.145488192 seconds,
**2.829344% of one core**, including five full captures. Capture CPU costs were
253.991384–430.881417 ms and wall costs 257.302227–435.717540 ms. Maximum scan
wall time was 15.173684 ms; maximum unsampled gap was 5.414850623 seconds.
SSH/sudo startup and source supervisor overhead are outside that observer CPU
counter. No unobserved control exists for isolating the observer's own effect.

This run establishes one observed pre-warmup pass followed by one observed
immediate post-warmup pass under the declared diagnostic. It does not establish
continuous quiescence, old preparation equivalence, or a passing endpoint.
Do not rerun the failed endpoint after settling and relabel it as passed.
The next unresolved boundary is the interval from the successful post-warmup
capture through normal validation/cleanup to the failed endpoint; this run has
no accounting coverage there. Preserve all seven unresolved causes:
`c08/3`, `c08/4`, `c08/5`, `pipebytes/3`, `pipebytes/5`, `pipecap/5`, `rcuht/2`.
Acquisition latency is unresolved. This no-timing cohort provides no performance
variance, and complete-operation p95 remains a separate metric.

## Preserved evidence

Guest base `/root/kdlock-evidence/10.176.26.71/bench/mutex-prewarmup-20261021`
is sealed; archives reside in the sibling `mutex-prewarmup-20261021-archives-1`.
Source-host raw evidence is under
`bench/results/10.176.26.71/raw/bench/mutex-prewarmup-20261021/`.
Run identifiers are `checks-1` and `probe-1`; the source supervisor files and
complete observer/workload streams are under raw `probe-1/`.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 242,655 | `03c0de15eb03d96fd1d82779ea1166a25782f5ee13c071af504dbdb7182f0c64` |
| `probe.tar.gz` | 223,221 | `3571aff7ad04a8c3c18b3dc2599f7316fda2a5dd24a7d6e14d5bb8df37fc98a7` |
| `metadata.tar.gz` | 35,975 | `7e15a675a9a99fe0c8128623071f5b1a8bdd28e4efe0612bb5f386b9bd258217` |

Archive manifest SHA-256:
`c32a258290915dd8c61a978113b8a533126405a34d62df094ec1821233b75c39`.
[The inert integrity review](review.json) passed **2,390 checks**, including
archive inventory, cross-archive references, tested/supervisor/guest sources,
unchanged prerequisites, stage ordering, exact ownership/counter accounting and
absence of timing. [The reviewer](review.py) never executes archived code.
Its first report-construction attempt failed on an incorrect audit summary
attribute; the empty failed output and development note are retained. The
corrected audit passed; no VM run was repeated or evidence changed to obtain it.

Independent read-only review verified all three archives, 200 inventory members
(172 regular files), six cross-root symlinks, ten supervisor source copies and
104 tested-source copies. It independently reproduced the full gates, nonce
chains, state/counter/retirement checks, chronology and observed worker deltas.
An initial review comparison looked for non-gate `argv` metadata absent from the
held environment; using the exact maintained gate keys corrected that offline
review assumption. No gate or evidence was changed. The reviewer touched no
files and ran no builds, tests or remote commands.
