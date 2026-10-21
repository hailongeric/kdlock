# Setup and measurement-boundary feasibility, 2026-10-21

Status: focused diagnostic completed and archived; the scheduled full boundary
gate refused every capture. No timing was sent and no performance acceptance
is established. Fresh checks on clean `98f9ea9` found no competing repository
writer and the same drained recovery VM, boot
`88449cfc-cea9-4647-a294-bc601e372146`, kernel `6.1.159-kdclobber2`, 73 original
runtime modules. Main agent alone writes and executes VM work; helpers review
read-only. Recovery artifacts and all earlier evidence remain intact.

The preceding [phase controls](../qemu-workers-20261021/README.md) establish that
all six observed extra workers existed before the measured command, not their
cause or absence of interference. This stage asks whether the established
control connection can retain a prepared session while host workers naturally
retire, then pass the unchanged full gate without fresh guest SSH/setup.

The first probe keeps original frozen OUTER/provider/client/translator bytes,
ordinary preparation and exactly one original five-worker warmup. It then
observes the full original gate at spaced, bounded points while the client is
quiescent. No timed command will be sent. The same held client/source/provider
must pass publication, counter stability, business and exact retirement checks.
Refusal or failure remains evidence, not a pass.

A post-warmup wait changes elapsed time since hotlock sampling, cache residency
and scheduling history. Hotlock heat is sampled on contention, not reset by a
wall-clock timer; idle time can affect the next comparison. Rewarming would be
an additional workload and may recreate host activity. Therefore this probe
does not preserve the previous timing preparation contract and cannot produce
comparable rates, even if the full boundary gate passes. It measures feasibility
and preserves an explicit changed-contract label.

Use one persistent guest connection and one persistent read-only host observer.
Host accounting samples are spaced five seconds apart; full-gate captures use
bounded 0/15/30/60/120-second observation points. Record capture CPU/wall cost,
causal reply brackets, worker TID/start ticks and missing tails. Snapshot queries
and guest validation themselves are observations, not proof of zero overhead.
All original gate conditions remain required; a count of 67 alone is insufficient.

## Source and preflight stage

`7308a6f` synchronized successfully: 3,962 tracked hashes verified, 17 paths
updated, no project files deleted. Guest `checks-1` rebuilt and passed the two
basic programs, four boundary-protocol tests and six unchanged recovery-gate
tests serially. Tested source hashes remained unchanged and final idle passed.
Protocol coverage includes partial replies, EOF, oversized/malformed replies,
timeout, nonce/hash binding and capture ordering. Existing frozen correctness,
owner/ACK, ELF and immutable-input prerequisites remain mandatory for the probe.

`probe-1` refused its initial full host gate at 72 tasks (five extra workers).
It opened no guest session and loaded no modules. Raw preflight, observer and
supervisor evidence is retained under the separate `probe-1` identifier.
The next revision permits only spaced preflight observations at 0/15/30/60/120
seconds on the same host connection; every original gate condition still must
pass before guest setup. This does not change the separate post-warmup hold.

Review identified that the frozen mutex payload has no `quiescent` sysfs field.
The probe uses its existing privileged `RA_DRAIN` ioctl, which reads exact
physical owner, queue, delegation and waiter records without modifying them.
The client's binding and owner descriptors remain live. Uncertain held state
retains resources with unsafe `UNDRAINED`; a coordinated gate refusal retires
normally and reports `passed=false`, independently of diagnostic completion.

## Completed held-session diagnostic

`probe-2` used source-host supervisor `8613df2`; guest source remained the
verified `7308a6f` synchronization. Only the source-host preflight loop and this
report changed between those revisions. The guest runner/protocol and frozen
provider/client/workload bytes were identical. Its first preflight passed the
complete original gate at 67 tasks; all existing correctness, owner/ACK, ELF,
source and kernel-identity prerequisites passed before setup.

One original five-worker warmup completed **6,724,992 operations**. Workers
0–4 and collector 63 matched their requested CPUs, all workers progressed and
both business checks passed. The held session retained its binding and owner
descriptors for **120.611930188 seconds**, with identical physical-idle,
publication/image, source and exact drained-counter records before and after.
The cumulative preparation-plus-warmup counters were 42,094 JIT entries and
42,094 completions, with zero address-guard exits. These are not a warmup-only
delta or a timed rate. Source state stayed OPEN with one source module and zero
frames/writers. Cleanup retired to state 2 with zero modules/frames/writers;
origin acquisitions/releases both totaled 132,069, with zero active waiters,
reserved nodes and active tasks. There were no per-session kernel fault matches. Final health reverified all
frozen inputs, the same boot/kernel and the original 73 runtime modules.

| Scheduled hold offset | Full-capture QEMU tasks | Original gate |
| --- | ---: | --- |
| 0 s | 75 | Refused |
| 15 s | 75 | Refused |
| 30 s | 70 | Refused |
| 60 s | 68 | Refused |
| 120 s | 68 | Refused |

The guest independently reran the unchanged full comparison against the final
capture and retained `passed=false`, `diagnostic_completed=true`,
`measurement_skipped=true`, `final_idle=true`. No client `measure` command,
measurement record or throughput field exists. The immediate **post-cleanup
full capture was 70 tasks**, distinct from the last accounting sample's 68.

## Timeline and limits

The five-second observer retained 26 samples, from 67 initially to a maximum
of 75. Eleven consecutive scans (sequences 14–24) saw the complete original 67
identities at held-marker offsets **63.176099477–113.336509781 seconds**.
Those are accounting scans, not full environment captures; they do not repair
any failed full gate. Worker 450014, start ticks 97280218, appeared afterward.
Its BOOTTIME birth bracket is `[972802180000000,972802190000000)` ns, about
113.442–113.452 seconds after the held marker. Only one accounting sample saw
it, with cumulative runtime 444,487 ns and 16,384 written bytes. No matched
counter interval exists for that worker; a zero computed delta is not evidence
of inactivity.

Matched worker intervals wholly inside the hold recorded 9.533635 ms of
runtime, 585,728 read bytes and 2,637,824 written bytes. Boundary intervals and
departed tails remain separate or missing. This establishes observed host
worker activity despite no new client command during the hold; it does not
identify the guest or host subsystem responsible. No workers were killed and
no host/VM settings changed.

Observer CPU was 3.053876585 seconds over 129.353918649 seconds, **2.360869% of
one core**, including seven full host captures. Capture CPU cost ranged from
327.618 to 426.106 ms, wall cost from 331.474 to 431.817 ms. Maximum unsampled
gap was 5.006251904 seconds. These costs exclude SSH/sudo startup and source
supervisor overhead. Reads and captures are non-atomic, and complete worker
lifetimes or accounting tails can fall outside samples. This single diagnostic
does not estimate variance or historical interference.

Natural retirement produced a sampled candidate interval, but the predeclared
five full captures did not establish a passing boundary. The evidence-backed
next discriminator is a separately identified, bounded **no-timing** probe
that requests the same full capture when an existing sample first contains
the original exact 67 identities. The sample is only a trigger: all original
full-gate checks must still pass. Even success would establish post-warmup
feasibility only. A wait after warmup changes the original preparation contract;
moving the wait before warmup requires a separate test because warmup may
create workers again. Neither path currently justifies controlled timing.

## Preservation

Guest archives are sealed at
`/root/kdlock-evidence/10.176.26.71/bench/mutex-boundary-20261021-archives-1`.
Local raw evidence is under
`bench/results/10.176.26.71/raw/bench/mutex-boundary-20261021/`, including
`probe-1/`, `probe-2/`, sync/check logs, `observer-review-2.json`, final health
and `archives-1/`. The [inert review](review.json) passed **2,004 checks** for
archive preservation, Git/source and prerequisite bindings, nonce/hash and
causal ordering, original settings, worker progress, unchanged held state,
refusal semantics and exact retirement. Its `raw_sha256` map binds every local
raw file; no archived code was executed. Helpers remained read-only and
reported no files touched. Independent review also confirmed all three archive
hashes, 162 inventory members, eight supervisor source bindings, 76 tested
source copies and 36 phase acknowledgement chains.

Archive manifest SHA-256:
`4d49332fadb5c80bbd6a99392a4d7d64d9346e8151f599247dc985fac5bb5fb6`.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 140,035 | `727154a16c427a2fc596c3abe83ab73d7d9aa3e022357564a56b5ec814590257` |
| `probe.tar.gz` | 138,619 | `d7b81236aa611c4939b3853e785da44f8d2b2622903284d963ea2660cf98d1c0` |
| `metadata.tar.gz` | 29,057 | `1924a65ddb25c523c8dbb6faf235a9c56ba8ea1aadd6571530dea2c2263d0a6b` |

All seven regression causes and acquisition latency remain unresolved. The
unlock derivative remains the whole routing/control-flow transformation,
including removed native cookie bytes and changed generated code. Earlier six
paired results remain unaccepted; complete-operation p95 is separate. Readers
remain local/concurrent, mmap and page-fault tasks separate, and unsupported
TCLock comparisons excluded.
