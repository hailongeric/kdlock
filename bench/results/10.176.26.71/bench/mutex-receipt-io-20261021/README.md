# Bounded guest receipt-I/O diagnostic, 2026-10-21

Status: protocol review, 49 serial basic/affected checks, one no-timing live
control and offline archive review completed. Endpoint refused; throughput
acceptance remains open.
New p95 measurements are deferred and missing p95 is not a throughput gate.
Existing latency and baseline artifacts remain unchanged. All seven mutex
causes remain unresolved under the original correctness, matched-work,
execution-class, retirement and environment requirements.

Fresh ownership checks at clean `9c22aac` found no source writer or index lock
on 380G10 and no in-flight project work in the existing recovery VM. The guest
retained boot `88449cfc-cea9-4647-a294-bc601e372146`, release
`6.1.159-kdclobber2` and the original 73 modules. Main is the sole writer and
VM executor; helpers review retained evidence/source read-only and touch no files.

The [preceding phase control](../mutex-phase-accounting-20261021/README.md)
located three worker births after the post-warmup capture and before cleanup.
This control observes the existing guest evidence writes to distinguish their
timing from control exchanges and later trace export. It does not identify the
initiating block request or rule out delayed earlier I/O/background activity.

One opt-in trace arms after the unchanged pre-warmup gate and fresh guest
comparison, records in memory for at most 60 seconds / 256 rows, and wraps only
existing `Path.write_text`/`write_bytes` calls inside the new evidence directory.
It preserves original arguments, bytes, return values, exceptions and order;
no fsync, write suppression, check removal or endpoint replacement is added.
Logical byte counts, guest clock/CPU brackets, phase request/reply byte counts
and starting/final process-I/O counters remain separate. Direct open-file,
copy, child-process, translator, SSH, background and prior I/O are outside its
write-hook coverage. Control byte counts cover phase messages only; large
boundary request/reply traffic and client pipe commands remain uncounted.
Text counts are encoded logical bytes before any explicit newline translation.
Overflow/errors make the diagnostic incomplete without
interrupting original writes or normal retirement.

After the original final receipt save and confirmed normal drain, two bounded
stdout records export the trace and its measured first-record send/flush cost.
No new guest trace file is written. Export adds pre-exit SSH traffic and delay;
the supervisor still waits for normal runner/SSH exit before the original full
endpoint capture. The trailer's own cost is bounded only by source receipt/EOF.
Malformed/missing/duplicate exports must not skip that endpoint. Source-side
raw logging remains in place. These observation effects prohibit treating the
control as throughput evidence or attributing the endpoint to a specific file.

Run basic and directly affected checks serially before one no-timing live
control, preserving the frozen provider/client/workload/translator and original
single warmup. Record exact gates, work/returned-body counts, owners/ACKs,
retirement, final idle, recovery and unchanged input hashes. No broad matrix,
kernel transition or new p95 collection is part of this diagnostic.

Separate read-only work prepares an RCUHT execution-class audit and distinct
actual-mmap/fault comparison plans. Experimental-kernel execution stays
separately scheduled after recovery diagnostics drain, in this same VM with
the recovery path preserved.

## Focused validation

Implementation `aba2dbf` synchronized while idle, verifying all 3,991 tracked
hashes and changing 16 files without deletion. `checks-1` passed 49 checks/programs
serially from 107 frozen sources: two rebuilt basic programs, eleven receipt
observer tests, five phase-accounting tests, nine trigger tests, four boundary
protocol tests, twelve pre-warmup tests and six recovery-gate tests. Sources
remained unchanged and final idle passed.

Read-only review identified and verified repairs for observer clock failures
changing original write behavior and optional export failures skipping the
endpoint. Tests inject those failures, preserve original effects/exceptions,
check logical text/binary byte counts, bounded overflow/expiry, excluded paths,
normal-drain-before-export and EOF/endpoint-before-trace-validation order.
An uncertain guest still cannot produce a fabricated endpoint or drain.
The reviewer found no remaining blocker for this focused live diagnostic,
touched no files and ran no tests, builds or remote actions.

## Completed live control

`probe-1` used supervisor `94920c7`, with diagnostic code tested at `aba2dbf`.
Original provider/client/workload/translator inputs remain unchanged, separately
bound to the retained public baseline and prior correctness receipts. The
single original five-worker warmup completed **9,331,584 operations** with
**5,881 matched JIT entries/returns**, zero address-guard delta, correct business
results and exact worker/collector placement. No measurement command was sent.
The 2-second measurement setting remains unused configuration; no new rate,
latency or timing variance is available from this control.

| Full capture | Tasks | Original gate | Capture CPU / wall time |
| --- | ---: | --- | ---: |
| Preflight | 67 | Pass | 392.987685 / 397.498149 ms |
| Pre-warmup | 67 | Pass | 462.698685 / 469.161249 ms |
| Immediate post-warmup | 67 | Pass | 316.189567 / 320.453159 ms |
| Original endpoint | 70 | **Refused** | 422.409859 / 427.916338 ms |

Both prepared boundaries passed the unchanged fresh guest comparison. The
pre-warmup hold was 59.858685596 seconds; twelve candidate decisions selected
scan 13 and one full capture. Scan start/finish preceded capture by
23.001535/13.232648 ms. The post request followed final worker completion by
1.547359 ms, including the original warmup-reply save and state checks. The
immediate post exchange was 414.581513 ms; no post-warmup settle or retry ran.

Origin acquisitions/releases balanced at **75,164/75,164**. Active waiters,
reserved nodes and active tasks ended at zero; exact retirement was
`state=2, modules=0, frames=0, writers=0`. Final health and archive sealing
confirmed idle, the original 73 modules, unchanged boot/kernel and all frozen
input hashes. No per-session fault match was recorded. Recovery remained
preserved; the failed endpoint is not repaired by successful guest drain.

## What the trace distinguishes

The trace contains 49 sequential events: **17 successful evidence writes** and
16 paired phase exchanges, with no drops, errors or expiry. Logical writes total
**4,874,247 bytes**, including six `session.json` saves totaling **3,618,281**
bytes and two `result.json` saves totaling **1,247,020** bytes. Phase traffic is
2,388 request bytes / 288 reply bytes. Process I/O separately increased by
4,945,721 `wchar` bytes and 4,927,488 `write_bytes`; these scopes must not be
equated with each other or with physical block requests.

| Endpoint worker / start ticks | Birth after post capture finished | Same-host phase location |
| --- | ---: | --- |
| 452912 / 98171692 | [100.746960, 110.746960) ms | Before cleanup; first seen at warmup-end marker |
| 452913 / 98171766 | [840.746960, 850.746960) ms | After unload-provider-end ACK, before cleanup-end ACK |
| 452914 / 98171771 | [890.746960, 900.746960) ms | After cleanup-end ACK, before final-verification-begin ACK |

Birth ticks use host BOOTTIME at 100 ticks/second; the post capture finished at
981716819253040 ns in that same domain. All 39 accounting scans completely
retained the original 67 task identities and placement. All three endpoint
workers have affinity `[63]` and were present in accounting sample 34 before
the final-verification-begin ACK. That ACK precedes verification, its ending
ACK and trace export. **Export cannot have initiated their births.** This
exclusion follows event causality without clock alignment. Export can still
add later activity and delay the endpoint.

This cohort differs from the preceding control, where all three endpoint
workers were born before the cleanup body. Keep the two source/observation
cohorts separate. Earlier preparation and delayed asynchronous I/O remain
possible initiators. Worker birth does not imply the initiating request was
issued at that instant.

The nearby writes can be compared only with explicit cross-clock bounds. For
each phase exchange, let `H` be the host ACK BOOTTIME; `hs/hr` its source-clock
request/receipt; `gr/ga` the source receipt of the guest phase and subsequent
guest-ACK send; and `gs/ge` the guest trace's phase-send/reply clocks. Then:

```text
local host-BOOT minus guest-MONO interval:
L = (H - hr) + (ga - ge)
U = (H - hs) + (gr - gs)
host birth [B0, B1) maps conditionally to guest [B0 - U, B1 - L)
```

These compose causal bounds through the source clock; no global fitted offset
or synchronized-clock assumption is used. They require locally stable clock
rates during the exchange. Applying them to adjacent writes additionally
assumes stability over that short extension; there is no measured drift bound.
Phase 21/34/35 widths are 11.412156/16.964742/12.178392 ms, plus the 10-ms birth
quantization. Under this conditional mapping, the first worker overlaps the
602,878-byte first large session save; the second overlaps the last kernel-log
write near cleanup completion; the third overlaps two subsequent session saves
and the first result save. **These are temporal overlaps, not file or I/O
causality.** The full brackets are retained in [review.json](review.json).

| Worker | Matched first-to-last CPU | Matched read / write bytes |
| --- | ---: | ---: |
| 452912 | 5.595259 ms | 110,592 / 3,420,160 |
| 452913 | 1.978181 ms | 28,672 / 1,245,184 |
| 452914 | 0.192593 ms | 0 / 167,936 |

First reads already contain cumulative activity; every lifetime continues past
the final sample, so tails are missing. These deltas are not phase-attributed or
whole-lifetime totals. No file descriptor, initiating syscall or block-request
binding was captured. Phase-only counts omit the large boundary reply and
client pipe commands. Unsampled background activity and delayed earlier I/O
remain unresolved, and sampled waiting states do not prove intervening idle.

## Observation cost and remaining throughput blocker

The guest trace spans 2.737508762 seconds. Existing writes' brackets total
13.360811 ms wall / 13.275934 ms CPU. Recorded hook bookkeeping CPU is a
**3.310882-ms lower bound**, excluding some wrapper entry/bookkeeping and
initial/final process-I/O snapshot overhead. Those snapshot brackets are
retained. The 17,830-byte first export envelope took 0.460375 ms wall /
0.458672 ms CPU from export entry through first flush, including freeze and
serialization. The completion trailer cannot measure its own flush. Its
source receipt to recorded normal guest finish was 39.488842 ms; that record
includes process wait, reader join and stream closure, not an exact EOF instant.
Recorded guest finish to endpoint dispatch was 15.813242 ms.

Host observer CPU totaled 1.939948816 seconds over 69.143879448 seconds,
2.805670% of one core. The armed 3.410981678-second interval had 25 scans;
scan plus post/endpoint-capture CPU alone was 911.889036 ms, a **26.733918%
lower bound** for that interval. Maximum armed unsampled gap was 518.321818 ms.
These costs remain intrusive and exclude SSH/sudo startup, source supervisor
CPU and an unobserved counterfactual. No continuously quiet interval or isolated
throughput overhead has been established.

The exact remaining blocker is the unchanged full endpoint: **70 rather than
67 tasks**. The trace excludes export as the birth initiator and identifies
receipt-write intervals worth investigating; it does not justify suppressing
writes, relaxing the gate or moving/replacing the endpoint. A next diagnostic
would need request/descriptor attribution or a separately identified control
that distinguishes existing receipt traffic from delayed/background activity.
Do not repeat broad timing matrices from temporal correspondence alone.
All seven mutex causes remain unresolved. New p95 is deferred and is **not**
the throughput blocker; correctness, matched work, execution classes and the
unchanged environment requirements still govern acceptance.

## Preservation and independent review

The [inert review](review.py) passed **2,626 checks** with no issues. It binds
source copies, prerequisites, original work, ownership/retirement, trace bytes,
phase clocks, failed endpoint and export ordering; [review.json](review.json)
retains the raw hashes and conditional overlap assumptions. Independent
read-only review reproduced the numerical findings and all three archives:
215 members, 186 regular files, six symlinks and 23 directories. All 107 tested
source hashes match; ten live helpers match tested bytes, and the supervisor
also retains the unchanged full-capture helper. Helpers touched no files and
ran no VM work.

Archive attempt 1 failed before creating any tar group because `metadata` is a
reserved automatic group. Its incomplete receipt and log are preserved; it is
not counted as a pass. Attempt 2 used automatic metadata grouping in a new
directory and completed with unchanged input inventory and final idle.

Guest evidence is sealed at
`/root/kdlock-evidence/10.176.26.71/bench/mutex-receipt-io-20261021`; the complete
archives are in the sibling `mutex-receipt-io-20261021-archives-2` directory.
The [collected manifest](../../raw/bench/mutex-receipt-io-20261021/archives-2/archives.json)
SHA-256 is `a46ee1fac2d8c217dc8c1b59f4a41638bc5d9bb9c7992fcc5ec7b9916def0545`.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 283,001 | `369f0d75972a7662fdbe318c9db6dfea3b6d5683feae35784a1a57e8ff4238c8` |
| `probe.tar.gz` | 226,391 | `a54246f48bea3af705540b281b3011466ea5eff7b0108125e27b38822b348dc7` |
| `metadata.tar.gz` | 37,633 | `98c4fd8d86f7e9046b3a6ada84d375464fc96796b86bc094b044f90987fa1d5b` |

Retained source-side evidence includes the
[receipt trace](../../raw/bench/mutex-receipt-io-20261021/probe-1/receipt-trace.json),
[observer stream](../../raw/bench/mutex-receipt-io-20261021/probe-1/observer.jsonl),
[supervisor](../../raw/bench/mutex-receipt-io-20261021/probe-1/supervisor.json),
[serial checks](../../raw/bench/mutex-receipt-io-20261021/checks-1.log),
[final health](../../raw/bench/mutex-receipt-io-20261021/final-health.log), and
[failed archive attempt](../../raw/bench/mutex-receipt-io-20261021/archives-1/archives.json).

The independent [RCUHT audit](../rcuht-class-audit-20261021/README.md) is complete
and narrows its no-JIT class to queue activity without combiner calls; it makes
no causal fix claim. Separate
[actual-mmap/fault plans](../../../../../kernel_integration/mmap_lock/COMPARISON_PLAN.md)
are prepared offline, with exact candidate/prerequisite identities and plain-only
throughput scope. Their new payload/client validation and later kernel-mode
execution remain pending; no experimental-kernel transition occurred here.
