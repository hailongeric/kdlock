# Phase accounting across warmup and cleanup, 2026-10-21

Status: focused validation, one live no-timing control and archive review
completed. The unchanged endpoint gate failed; performance remains unaccepted.
The checkout was clean at `bdd8472` on 380G10, without a source writer or index
lock. Fresh read-only checks found the same recovery VM drained, with its
original 73 modules, boot `88449cfc-cea9-4647-a294-bc601e372146` and kernel
`6.1.159-kdclobber2`. The main agent remains the sole writer/VM executor;
helpers perform read-only review and report no files touched.

The [previous control](../mutex-prewarmup-20261021/README.md) saw full gates pass
before and immediately after one original warmup, then an endpoint worker
failed the unchanged 67-task gate. Its five-second accounting cadence captured
no samples during warmup or any later phase. This control tests the specific
hypothesis that the endpoint worker is born during post-warmup validation or
cleanup/control I/O, rather than remaining from warmup. A birth interval wholly
after the post-warmup full capture would distinguish those alternatives. Phase
association cannot identify which operation caused a birth or delayed I/O.

Keep the existing five-second pre-warmup quiescence protocol, exact original
67 TIDs/names/placement and every full-gate/guest/ownership/ACK/lifetime check.
Use the same frozen provider, client, workload, translator and original warmup.
The guest runner is unchanged. After selecting the pre-gate full capture, arm
one uniquely identified **60-second, nonrenewable** window through the existing
observer connection after a passing host gate, taking a baseline accounting read before its ACK. The
added round trip precedes the guest pre-gate reply and is recorded separately;
the absolute arm budget is ten seconds. A missing/late ACK never releases the
guest, whose existing timeout retains uncertain state.

Within the window, read every **250 ms from the previous scan's completion**;
never issue catch-up reads. Also read at existing phase marker requests before
their ACK, retaining the preceding phase and the pending marker separately.
For full gates, capture first, then take a linked accounting read before the
capture ACK. Ready control requests take priority over periodic accounting;
an already-running read can still delay a request and is recorded. No deliberate
accounting read precedes the immediate post-warmup full capture. The endpoint
full capture remains in its original position, followed by accounting while
the window remains active; it is never replaced with a later quiet capture.
Window expiry is explicit and missing endpoint accounting remains a coverage
gap. The neutral `accounting-window-armed` label identifies observer state,
not the exact original-work interval. A failed following accounting read retains
the completed full capture plus its error; the coordinator does not release
the guest on a failed required ACK.

Keep continuous sample sequence numbers, TID/start-tick identity checks before
and after each read, partial/disappeared rows, CPU/I/O counters, BOOTTIME birth
intervals and per-task/scan clock brackets. Full capture CPU/wall cost stays
separate from following accounting and ACK latency. Preserve observer total
CPU/wall cost, source/guest control chronology and the changed preparation
history. No timed command, throughput matrix or performance acceptance is
permitted. Denser sampling still misses short lifetimes, exited-worker tails,
capture-length gaps and non-atomic changes; differently named extra threads
have identity but no worker-specific CPU/I/O read in the existing observer.

Run basic and directly affected checks serially before the live control, then
verify normal retirement, final drain, recovery state and frozen hashes.
Preserve all refusals and uncertain resources. All seven mutex causes and
acquisition latency remain unresolved; complete-operation p95 is separate.
Readers remain concurrent/local, mmap and faults stay separate, and unsupported
TCLock critical sections remain excluded.

## Focused validation

Implementation `7e1071c` synchronized while idle, verifying all 3,981 tracked
hashes. Guest `checks-1` passed serially from 105 frozen source files: two rebuilt
basic programs, five phase-accounting tests, nine trigger tests, four reply
protocol tests, twelve pre-warmup flow tests and six recovery-gate tests.
Source hashes remained unchanged and final idle passed. The new checks cover
expiry/nonrenewal, completion spacing, pending-control priority, capture before
accounting, preserved capture after sample failure, exact task identity,
unavailable counters and identity reuse/disappearance during a read.

Independent read-only review confirmed the fixes for preserving a completed
capture on accounting failure, suppressing guest ACKs on observation error,
arming only after a passed host gate and neutral observer-state labeling.
It reported no remaining blocker and touched no files.

## Completed control and exact drain

Run `mutex-phase-accounting-20261021/probe-1` used supervisor `1c57972` and
the tested implementation `7e1071c`. The original provider/client/workload and
translator stayed frozen; `unlock_run.py` was unchanged from the preceding
control (SHA-256
`d33f53a1dcc82c81b3b39ec1349efe0ac37c9164f38da874a4422203ed285e68`).
This is a separate observation cohort, not a revision of baseline measurements.
The original 64-vCPU, 24-GiB, two-node topology, worker CPUs 0–4, collector 63,
kernel, boot, recovery snapshot and exact original 67 host task identities and
placement were retained. No kernel change, reboot or concurrent test occurred.

| Full capture | QEMU tasks | Original gate | Capture CPU / wall time |
| --- | ---: | --- | ---: |
| Preflight | 67 | Pass | 389.896029 / 394.562084 ms |
| Before warmup | 67 | Pass | 374.616394 / 379.536967 ms |
| Immediately after warmup | 67 | Pass | 315.325633 / 318.448038 ms |
| Original endpoint | 70 | **Refused** | 342.700181 / 346.292567 ms |

Both prepared boundaries also passed the unchanged fresh guest comparison.
The pre-warmup hold was 29.572689472 seconds. Six candidate decisions selected
accounting sequence 7; its scan began 19.846223 ms and finished 12.207555 ms
before the one full pre-warmup capture began. There was no post-warmup settle
or capture retry.
The single original warmup completed **6,975,616 operations**, with **53,833
matched JIT entries/returns**, zero address-guard delta, every worker progressing
on its assigned CPU and both business checks passing. No measurement command
or rate was produced; the retained `duration_ms=2000` is unused configuration.

Origin acquisitions/releases balanced at **209,636/209,636**. Active waiters,
reserved nodes and active tasks ended at zero. Exact source retirement was
`state=2, modules=0, frames=0, writers=0`; normal cleanup and final idle passed,
with all original 73 modules, the same boot/kernel and unchanged frozen hashes.
No per-session kernel fault match was recorded. The preserved recovery kernel
and snapshot were not changed. The endpoint refusal remains a failure even
though guest correctness and drain passed.

## Worker births and phase association

The observer retained 33 complete scans of the original 67 lifetime identities;
25 scans occurred in the single armed window. There was no arm/accounting error
or window expiry. The arm baseline, four periodic reads and the read following
the immediate post capture contained no extra worker. Three new workers then
appeared; all survived through the endpoint and stop reads with affinity `[63]`.

| TID / start ticks | Birth interval after post capture finished | First observed pending marker | Matched CPU delta | Matched read / write bytes |
| --- | ---: | --- | ---: | ---: |
| 452267 / 97886305 | [96.849984, 106.849984) ms | `phase21-client-warmup-end` | 2.863806 ms | 90,112 / 2,039,808 |
| 452268 / 97886326 | [306.849984, 316.849984) ms | `phase26-measure-accounting-end` | 3.226673 ms | 0 / 1,986,560 |
| 452269 / 97886329 | [336.849984, 346.849984) ms | `phase27-cleanup-begin` | 0.712775 ms | 49,152 / 266,240 |

Birth bounds use host BOOTTIME and 100 start ticks/second, giving 10-ms
quantization; the reference capture finished at BOOTTIME 978862953150016 ns.
No host/guest or BOOTTIME/MONOTONIC subtraction is used for these bounds.
Worker 452267 was born before the warmup-end ACK, in the interval containing
fresh post-capture guest validation, receipt writes and control traffic.
Worker 452268 was born between check-after-boundary-end and
measure-accounting-end ACKs, after the business check. Worker 452269 was born
between measure-accounting-end and cleanup-begin ACKs. **All three births
precede execution of the cleanup body**, which follows its begin ACK.
The `measure-accounting` marker is retained runner bookkeeping: it does not
mean a timed measurement was sent.

These are newly born workers, not workers that persisted from the original
warmup. This does **not** exclude delayed I/O initiated during warmup or earlier
preparation. Phase association does not identify the initiating descriptor,
file, block request or background activity. The observer and its own control
traffic may contribute. Moving the endpoint, suppressing necessary writes or
treating these workers as harmless would change the acceptance contract.

The table uses first-to-last matched counter deltas, totaling **6.803254 ms
CPU, 139,264 read bytes and 4,292,608 written bytes**. First cumulative counters
already contained activity, including 606,208 written bytes each for the first
two workers; they are not attributed to an observed phase. All three lifetime
tails after the stop read are missing. Sampled futex-wait states do not prove
inactivity between reads. No whole-lifetime or causal I/O totals are claimed.

## Chronology and observer limits

The added arm round trip took 12.888305 ms; arm ACK receipt to the recorded
pre-gate `reply_sent` timestamp took another 20.752673 ms in the source clock
domain. The supervisor then saves its evidence before transmitting the guest
reply, so that interval excludes the final save and is not an exact send delay.
In the guest clock domain, fresh pre-validation took 9.837117 ms and the command
followed the completed pre-gate exchange by 8.676 us. Command to scheduled work
start was 50.239283 ms; the work interval was 1.000063967 seconds. Final worker
completion
to saved original reply was 1.102199 ms; reply validation took 73.793 us and the
required post-state snapshot 1.404373 ms. The post request followed final work
by 2.602270 ms. Its full exchange took 415.840151 ms, including a 9.377856-ms
fresh guest validation. Source receipt to capture dispatch was 606.873 us.
The cleanup marker interval was 502.750072 ms and includes control overhead.
These are same-domain durations; transport events link domains without assuming
synchronized clocks or an exact cross-machine latency.

Full captures precede their linked accounting reads. Seventeen remaining
markers, including stop, have matched sample-before-ACK records. The single
armed-to-stop interval lasted 3.274943636 seconds. Its 25 scans consumed
185.539511 ms CPU / 187.154002 ms wall time, with a maximum unsampled gap of
429.493358 ms. Across all 33 scans, maximum scan duration was 11.571805 ms and
median duration 7.977245 ms; the earlier five-second cadence had a maximum
5.006172505-second gap.

Total observer CPU was 1.722465142 seconds over 38.825502014 seconds, or
4.436427% of one core. That average includes the quiet pre-warmup wait. During
the armed interval, scans plus the post/endpoint captures alone consumed
843.565325 ms CPU, a **25.758163% lower bound** for that interval. Other observer
processing, SSH/sudo startup and source-supervisor CPU are not included in this
lower bound. The diagnostic is intrusive, and no unobserved counterfactual or
cache/I/O interference bound exists. Non-atomic reads, capture gaps, short
missed lifetimes and missing tails still prevent proof of continuous quiescence.
This single no-timing control provides no throughput or latency variance.

## Sealed evidence and independent review

The [inert review](review.py) passed **2,446 checks** with no issues; its
[machine-readable result](review.json) binds raw-file hashes and preserves the
failed endpoint, observer costs and unresolved dispositions. Independent
read-only review found no mismatches across three archives, 202 inventory
entries / 174 regular files, six cross-root references, ten supervisor source
copies and 105 tested-source copies. It independently reproduced the gates,
birth intervals, accounting, exact work/return counts and final drain. Both
review helpers reported no files touched and ran no VM work.

Guest evidence is sealed under
`/root/kdlock-evidence/10.176.26.71/bench/mutex-phase-accounting-20261021`, with
archives in the sibling `mutex-phase-accounting-20261021-archives-1` directory.
The collected [archive manifest](../../raw/bench/mutex-phase-accounting-20261021/archives-1/archives.json)
has SHA-256 `9cf8628e0e7e88ded927e85e1603d0790df61c45d97735680a7dc56bd0cda02f`.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 245,591 | `2e8ab4c51bbf57169adff69d1dc4675afcc9fc6d3ca34a199dcde819e7fa1630` |
| `probe.tar.gz` | 223,405 | `a956267c7e4d3f3d8d133bfad9d53d8f3b8075f8093e560677b16c304e8f33c0` |
| `metadata.tar.gz` | 36,056 | `8b7e2d06849e94344e53fe056c5ab4ffe287dcfd37142172823610945231477b` |

The [observer stream](../../raw/bench/mutex-phase-accounting-20261021/probe-1/observer.jsonl),
[supervisor record](../../raw/bench/mutex-phase-accounting-20261021/probe-1/supervisor.json),
[serial-check receipt](../../raw/bench/mutex-phase-accounting-20261021/checks-1.log)
and [final health receipt](../../raw/bench/mutex-phase-accounting-20261021/final-health.log)
retain the detailed evidence. Baseline and preceding control archives remain
unchanged and distinguishable by their run identifiers and source revisions.

## Remaining blocker and independent work

No complete accepted measurement protocol is established under the existing
contract: the required endpoint after normal validation and cleanup fails at
70 rather than 67 tasks. Passing pre/post-warmup snapshots do not establish a
quiet full session or justify a later replacement endpoint. All seven causes
(`c08/3`, `c08/4`, `c08/5`, `pipebytes/3`, `pipebytes/5`, `pipecap/5`, `rcuht/2`),
acquisition latency, preparation equivalence and performance acceptance remain
**UNRESOLVED**. Previously sampled complete-operation p95 stays a separate metric.

Three concrete tasks can proceed under the existing authorization while timing
is blocked; none requires another user decision to begin repository work:

1. Prepare a minimal receipt-I/O diagnostic that timestamps and counts bytes for
   existing guest save operations without reordering writes, removing checks or
   moving the endpoint. Retain a small in-memory trace until safe export and
   account for that observer's cost. Any live control follows serial basic and
   affected validation in the same idle VM; worker timing alone cannot prove
   file causality.
2. Prepare separate actual-MM comparison plans offline: untouched shared-mm
   mmap/munmap with zero payload faults, and pre-established mappings with
   independently checked fault cycles. Bind candidate kernel/mode, module set
   and correctness receipts; compare Native-control and KD-local on the same
   experimental image with concurrent local readers and no unsupported TCLock
   arm. Execution requires a separate scheduled kernel transition and unchanged
   gates, without interrupting the recovery-kernel investigation.
3. Audit the retained two-worker RCUHT source/ELF and per-repetition execution
   classes offline. Keep plain `WITNESSED_JIT`/`NO_JIT`/`WITNESSED_JIT` repetitions
   and instrumentation-induced class changes separate, distinguish actual entry
   witnesses from lifetime queue counters, and specify a small future
   discriminator without declaring a causal fix or scheduling broad timing.

Maintained validation/TODO indexes now distinguish completed selected
actual-mmap correctness from the older blocked integration audit. Completed
organization, recovery and rwlock continuation work are not new prerequisites.
