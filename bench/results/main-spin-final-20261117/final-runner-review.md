# Static review of the prepared final runner

This note reads only main source and the prepared host evidence. No builds,
tests, VM access or timing were performed. It applies to the copied
`run-final.py` and `collect-final.py` hashes in `copied-inputs.json`, with main
source identity `18dad4a1c372d77a1155db671d56c148918344da`.

The loops schedule 413 points: 27 local, 36 daemon-off including warmups,
two learning, eight phase-change, nine delegation-check, 12 phase-check,
four mixed rwlock, 180 three-way including warmups, 96 post=0 including
warmups, 36 packed NUMA including warmups, and three forced checks. There is
one API ioctl before these grids. The separate six-entry fixture is outside
the runner and needs its own result and unload receipt.

The final runner preserves the queue runner's 1104-byte ioctl layout and
worker-counter indexing. It checks all worker progress, exact aggregate sums,
positive elapsed time, protected-data delta and zero reader mismatches. The
mixed rwlock rows use lines=16 and write_pct=20. Their per-worker positive
reads and writes are checked later by `collect-final.py`, which asserts
`0 < wr < op` for every worker in every `rwlock-mixed-sixteen-check` point.
Thus the runtime point's `ok` alone does not close that additional condition.
The revised collector explicitly asserts exactly 413 total points and four
mixed rows, in addition to those per-worker conditions. Its archive selects
seven named final module build logs, avoiding unrelated older logs copied
into the reused output directory. The initial prepared collector is retained
as `collect-final-before-count-check.py`; it printed cardinalities without
asserting them. The completed guest collection receipt now records successful execution.
This report author reviewed exported data only; no guest collection was run
by this reviewer. See `runtime/collection.json` and `runtime/offline-data-review.json`.

Queue-phase default Y and phase-wait default 0 are asserted before parameter
writes. Every point records actual queue-phase, phase-wait and NUMA values and
requires polling to stay zero. The campaign records its initial boot UUID and
checks it before marking measurements complete. Backend order rotates, and
timed rows carry actual elapsed_ns plus matching event deltas. Warmup and
functional points remain separate. TCLock quiescence is checked after its
points. Shared stop/drain accounting has the same limitations as described in
`queue-runner-review.md`; drain completions count, drain time is excluded.

The `finally` block intends to restore original parameters, stop the daemon,
close the device, require TCLock quiescence, clear its target pointer and
normally unload modules in reverse order. Any exception during cleanup may
prevent later steps, so the source block and measurements-complete marker
cannot replace a successful cleanup receipt and idle inspection. Module unload
is never forced by this runner. Kernel warning strings stop the campaign.

No profile, universal exclusion proof, arbitrary IRQ/nesting coverage, or
physical proxy-chain measurement follows from this runner. The old queue
review's 741 points and three API invocations do not apply to this final plan.

## Completed evidence

The final campaign returned rc=0 with exactly 413 checked points, including
four mixed rows and all 80 mixed workers showing both reads and writes. The
API ioctl reported zero failed checks, the daemon exited with rc=0, and all
five comparison modules unloaded normally. The final independent state
receipt has no active test process, no startup job and delegation=0, with
original parameters restored. Raw evidence and narrower coverage limits are
linked from README.md; these runtime receipts do not turn the static review
into exhaustive concurrency coverage.
