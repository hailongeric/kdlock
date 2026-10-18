# Archived 16K-poll candidate review

Reviewed candidate `768fc20cd981bfe28cc223825d25b5c9c2552757`
(`archive/rwsem-opt-xlong-20261018`) directly through Git objects, against
`485729f` and selected mutex `d2a2304`. No working-tree source identity was used;
the checkout was temporarily restored for independent baseline measurements.

No blocking static correctness finding was identified. The complete candidate
diff changes exactly three files: `include/kd_rwsem.h`,
`kernel_module/kd_rwsem.c`, and `tests/kernel/rwsem/module.c`.

- Ordinary readers, ordinary writers and delegation-capable writers make at
  most 16,384 unsuccessful/successful condition probes before consuming one
  successful acquisition or entering the unchanged normal wait-event path.
  Success is never evaluated again. `need_resched()` terminates unsuccessful
  polling early. Preemption remains enabled; delegation has not published yet.
- The finite counter remains necessary even if `need_resched()` stays false.
  The bound is on outer predicate probes, not elapsed time or a predicate's
  internal atomic retry loop. It adds no bounded-wait or fairness guarantee.
- The phase queue is woken only after reopening admission. Reader drainage is
  woken after the last exact read count disappears. The fully ordered RMWs and
  existing native enqueue/recheck protocol retain lost-wakeup protection.
- Reader count, phase admission and both queue locks have separate alignment.
  The local reservation read is only a failure hint: a successful acquisition
  still requires the existing authoritative compare-and-exchange.
- Interruptible/killable admission, cancellation rollback, physical KD gate
  ownership, downgrade ordering, and origin-side delegation release after the
  existing unlock/ACK are preserved. The outer wrapper bytes are unchanged.
- No asynchronous reader-grant code remains. Relative to archived 1024-probe
  provider `72a0a0e3`, the provider source changes only the two `1024` literals
  to `16384` (budget and explanatory comment).
- The original twelve result fields and runner bytes are unchanged. All 53
  original `check(...)` call occurrences remain (with the old shared drainage
  queue assertion mapped to the correct new reader-drain queue). Nine new
  assertions check queue roles and phase-to-reader-drain movement. The JSON
  lexical inventory additionally counts the unchanged macro formal parameter,
  reporting 54 versus 63 occurrences.
- Existing checks still force actual switched-out readers and writers sharing
  CPU 0, exact pre-publication queue emptiness, ordinary downgrade with queued
  delegates, ten cancellation cases, worker joins, and final gate/count/both-
  queue idleness. A timeout is still not accepted as drain.

`selected-16384-review.json` records candidate Git blob hashes and complete
comparisons: all 16 mutex-specific files and the same 112 baseline runtime
files match `d2a2304`; all 115 other runtime provider/header/translator/daemon
files match `485729f`. Earlier exclusions are explicit. [selected-16384.patch](../../bench/rwsem-optimization-20261018/selected-16384.patch)
is the exact complete Git diff, SHA-256
`c3dbc10a8c6921e4889654b6fc699ebed05548a3bc63a3a07750deb53362f9e8`.

The independent design reviewer reached the same conclusion. This static
receipt does not claim a runtime or performance pass, binary equivalence,
frozen-guest source identity, a universally optimal polling budget, RT/lockdep
coverage, oversubscription support, or whole-kernel integration. Native sample
variation must remain in the measured result evidence; these source changes do
not by themselves establish its cause.
