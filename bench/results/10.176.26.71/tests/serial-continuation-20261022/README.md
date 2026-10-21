# Serial diagnostic and actual-MM continuation, 2026-10-22

Status: both bounded RCUHT sessions completed and drained. Their original
immediate endpoints failed, so both remain rejected for performance use.
The six candidate boot blocks and 24 separate plain sessions are pending.
All seven mutex causes remain unresolved. New p95 stays deferred.

The source checkout resumed clean at `01594c5` on `380G10`; its eight verified
archives remain unchanged. The supported OS process/CWD and Git-lock checks
found no competing writer. No supported application task-list interface was
available; no undocumented IPC or unrelated task history was accessed. Helpers
reviewed source read-only and reported no files touched. The main agent remains
the only repository writer and live executor.

The same VM was idle on recovery `6.1.159-kdclobber2`, boot
`ad05e2e3-1f03-40db-9486-b49166f946ae`, with the exact 73 runtime modules.
Host observation 1 found 76 threads; observation 2, about two minutes later,
found the original 67. No worker was killed and no host setting changed.
The snapshot and original CPU placement remained present.

## Recovery binding and bounded diagnostic

The new `transition-1` freshly verifies the live recovery kernel, source/config/
build identity, preserved recovery files, current boot/modules, boot logs and
all original guest environment/topology fields. It derives the replay driver's
`new_boot_id` schema from retained recovery evidence without modifying any old
receipt or original boot ID. Its SHA-256 is
`53d2bd0f162ae027aff7bc9aded564ca11740661487d89b792fc30a6d97abd46`.

Revision `78d8be2` keeps the original provider/caller/client/daemon/translator
and collector bytes, but runs each diagnostic arm in its own process through
the full original admission comparison. Both basic programs and eight affected
tests passed. OUTER precedes DIRECT; the latter binds the exact completed
predecessor and its preserved endpoint, including controller chronology and
source/receipt hashes. A failed predecessor endpoint remains failed even when
the next distinct arm later passes fresh admission. No session is rerun to
obtain a preferred execution class.

Both cases use two workers on CPUs 0/1, collector 63, repeat 0, original
48,000-operation per-worker warmup and original two-second measurement. Four
stable counter captures bracket the joined warmup and measurement; the gap is
kept separately. Counters are entry witnesses, not returned-body counts.

| Run | Warmup operations / entry witnesses | Measured operations / entry witnesses | Exact retirement | Immediate endpoint |
| --- | --- | --- | --- | --- |
| `outer-1` | 96,000 / 0 | 7,155,968 / 17 | state 2; modules/frames/writers 0 | Failed: 110 threads |
| `direct-1` | 96,000 / 0 | 6,593,280 / 8 | state 2; modules/frames/writers 0 | Failed: 76 threads |

Both completed with `execution_status=OK` and final idle. Warmup slowpath
counters were 1,973 OUTER and 580 DIRECT with zero combiner calls; measurement
reported 17/8 combiner calls and corresponding entry witnesses. This localizes
these counters to their phases but does not reproduce or explain the historical
no-JIT sessions. No throughput comparison or causal fix is accepted.

The source controller requests the host capture immediately after observing
normal guest SSH completion, before receipt retrieval or another test. Its
recorded interval covers capture-request initiation; actual host reads also
include SSH startup. This is a whole-session endpoint, not an instantaneous
worker-exit snapshot. OUTER admission observations 72 then 67 and DIRECT
observations 68 then 67 remain separate. The later quiet captures never replace
either failed endpoint.

Independent read-only archive review passed: six archives contain 187 regular
files, 56 directories and 72 preserved symlinks. All archive hashes, sizes,
inventory types and symlink targets match. The manifest SHA-256 is
`b7afa0e2000ddb5b2a8bd533c1455cf97a4a8d9b755511f61a826bc4910d4af1`.
All 340 baseline and 344 current RCUHT input bindings match their original
archives. The shared frozen-input manifest SHA-256 is
`df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73`.
Raw evidence: `raw/tests/serial-continuation-20261022/rcuht-archives-1`.

The local endpoint request began 1,500 ns / 669 ns after observing SSH exit;
request-to-return took 768.117 ms / 717.593 ms. These are controller chronology,
not instantaneous remote sampling. Neither arm supplies rerun variance.

## Actual-MM preparation

A separate measure-only wrapper at `78a1b04` passed two basic programs and ten
directly affected VM tests. It keeps the validated
preparation manifest and all frozen payload/client/runner files unchanged,
reuses completed both-mode correctness, enforces the documented boot/case
order, and gives each session its own full admission and original endpoint.
The API correctness suite will not be rerun without changed inputs or new
failures. Readers stay local, writers stay on their original task, shared-mm
untouched mapping stays separate from independent-mm fault cycles, and
unsupported TCLock MM workloads remain excluded.

The source-side coordinator passed read-only review and four focused VM control
tests. It records every child command and PID, preserves unknown drain after a
timeout, waits for a changed boot UUID after a reboot request, and never resends
an ambiguous request. Copied archives must match inventory, boot and base-path
bindings as well as every tar hash. A refreshed recovery health check confirms
the same boot and exact 73 modules before timing. The serial wrapper and all
683 frozen input bindings remain unchanged. The next stage is six distinct
boot blocks in native/KD, KD/native, native/KD order, each with separate
`mmap/1`, `mmap/16`, `fault/1`, `fault/16` sessions. Every admission uses the
original full gate. Failed fixed endpoints remain rejected; later observations
can only admit a distinct new session.
