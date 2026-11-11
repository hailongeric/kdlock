# Ordinary Linux rwsem compatibility checks

This source fixture selects one private, freshly initialized `rw_semaphore`
onto the rebuilt KD gate with `source_calls=false`. It invokes the ordinary
Linux APIs through source forms, callable function pointers and cleanup
constructors. It supplies no source packet or managed JIT configuration.
Compilation and execution are pending. These cases establish no mmap syscall,
generated-execution or performance result.

Module parameters `native_capacity` and `wait_timeout_ms` are required and have
no nonzero defaults. Capacity must cover at least three simultaneous records,
which is the largest controlled scene. All pool and object storage is allocated
before the misc device is registered. The device is `/dev/kd_rwsem_api` with
mode 0600. Privileged callers use `_IO('Q', 1)` with argument zero to RUN once,
and `_IO('Q', 2)` with argument zero for ordinary STOP/drain. Reading the device
returns JSON status, saved case outcomes, grant/pending flags, cumulative worker
creation/join counts and native event counters. State values are COLD0,
RUNNING1, PASS2, FAILED_RETAINED3 and DRAINED_FAILED4. Native counters are read
acquire/release, write acquire/release, real downgrade, cancellation, try miss
and MCS enqueue, in that order.

The twelve fixed cases cover concurrent real readers with writer exclusion, trylock
success1/failure0 and failed-try no-enqueue/no-grant observations, callable and
cleanup-constructor routing, real writer-to-reader downgrade admitting another
reader before matching up_read, and nonowner release after the acquiring kernel
thread has actually exited. Controlled blocked waits check interruptible read
with SIGUSR1 and killable read/write with SIGKILL. Those three scenes require
-EINTR while the original writer still holds its grant. The canceled queued
writer's persistent queue user is checked before releasing that blocker.
A separate cancellation scene holds a real READ credit and waits until the
killable writer has its exact MCS turn, initialized batch and writer-pending
reader drain. After SIGKILL it requires -EINTR, no native WRITE grant, no pending
writer or queue tail, and the original READ still held. The saved
turn_wait_proved and turn_cleanup_proved flags identify these observations.
Its MCS physical callback is not interpreted as a WRITE grant.
Available-grant cases enter read interruptible, read killable and write killable
with their corresponding signal already pending, and require successful grant.
Every completed case checks ordinary release and exact pool quiescence.

Controllers own no long-lived semaphore grant. Each worker releases its own
owned grant after an explicit completion. STOP opens those control completions,
waits for actual worker completion, joins each thread and releases any exact
nonowner transfer credit. A timeout preserves the module reference, controls,
object and worker records. Closing an fd does not discard that retained state.
STOP can be issued by another privileged caller. It does not force unlock,
force unload or treat elapsed time as a join. The outer VM controller must
retain an outstanding attempt if an ordinary join itself remains unfinished.
A failed RUN remains a failure after successful cleanup.

Keep the source snapshot, explicit parameter values, normal kernel/config/module
identities, RUN/STOP return values and status JSON. Future execution belongs in
the VM after source review and a verified recovery/idle/headroom gate. This
fixture covers native-local compatibility. Mixed managed/native credits need a
separate provisioned managed fixture, and real mmap/munmap validation uses the
separate [userspace syscall check](../mmap_api/README.md).
