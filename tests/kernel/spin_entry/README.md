# Contended spin entries

Build and run only in the verified 380G10-local VM, against its exact kernel
output, with recovery available and no translator or benchmark running.

The module runs two workers on CPUs 0 and 1 through plain, IRQ, IRQ-save,
IRQ-save with interrupts already disabled, BH and clobber entry pairs. Each
pair must observe contention, finish exactly 30,000 operations per worker,
preserve entry interrupt/preemption state and maintain exclusive access.
The atomic overlap check is correctness instrumentation, not a timing workload.

A worker completes through `kthread_complete_and_exit`, so an init failure
cannot free module text while that worker returns through it. Waits do not
pretend a timeout is drain: a stuck acquisition requires stopping the campaign
and retaining the VM for diagnosis, never forced module unloading.

After successful insertion, check all six printed records and normally unload
`kd_spin_entry_check`. This exercises the changed local slow entries; it does
not establish delegated IRQ-context execution or exhaustive concurrency safety.
