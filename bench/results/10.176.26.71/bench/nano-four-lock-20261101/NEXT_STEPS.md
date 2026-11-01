# Next bounded iteration

No candidate in this record is promoted. Keep the restored production rwlock
path and the original master reachable; preserve all candidate sources and
scores. These are proposed follow-ups, not completed measurements.

1. For rwsem c01/w1 at eight workers, use separate unscored observations of
   first-probe success, speculative count rollback, slowpath entry and final-reader
   wake-queue tests. Obtain a matching baseline cycle/address profile. Split the
   reader-entry outline from the early drain-queue test if the component results
   point to that combined edit. Retain the eight-probe order, successful-grant
   priority, exact count/barrier and cancellation semantics. The current evidence
   does not justify removing PAUSE, extending cancellation latency, or claiming
   a sleeping problem.
2. For rwlock, redesign only the bounded read-admission prefix if its physical
   transfer cost can be reduced while retaining the same queue-head qualification
   decisions. Measure credited readers, physical gate transfers, returned writes
   and count RMWs separately. The withdrawn prefix raised locked-load count and
   altered qualification even where a remote-load event decreased. Repeat its
   exact-count, mixed-writer and IRQ/BH checks before new timing; read bodies must
   still execute on their original threads.
3. For rwsem split-node phases, obtain address attribution for reader count,
   admission, OSQ nodes and phase wait fields. Whole-client remote-DRAM loads
   cannot prove that predecessor checks caused those loads. A locality-aware
   reader queue would change admission ordering and belongs to a separate
   fairness decision; this iteration does not silently adopt it from TCLock.
4. Keep mutex and spin as controls. Their contended baseline scores exceed
   TCLock, and their equal-worker NUMA penalty is much smaller than rwlock's.
   Repair the optional observation module's allocation footprint before making
   any batch-length claim. Preserve the 1024/1024 mutex limits, exact owners,
   source/frame lifetimes and completion probes.

A new scored version gets one round per selected point. Diagnostic throughput
never replaces a score. A future full-grid candidate must retain every negative
observation, including controls and `NO_JIT` cases; narrow component comparisons
do not establish a regression pass.
