# Reader/writer correctness workload

`rwlock_test.ko` exposes `/dev/kd_rwlock_test`. Build-time `RW_BACKEND=native`
selects Linux rwlocks; `RW_BACKEND=kdlock` selects the public
[KD rwlock API](../../include/kd_rwlock.h). Each build owns its target lock.
The KD build prepares ABI3 writer continuations; readers execute locally. Native
code acquires writer admission before the body on both local and JIT routes.
Prepared publication alone is not proof of delegation; the test runner checks
returned bodies in its contended JIT phases.

Eight protected values must stay equal. Writers increment all eight; readers
verify consistency while recording concurrent reader overlap. Additional counters
check reader/writer and writer/writer exclusion. Each ioctl checks that preemption
and interrupt state were restored. Snapshots and preparation run only when no worker
ioctl is active. After the workers finish, both the KD count and gate must be zero.

[api.h](api.h) defines the preparation, worker and snapshot ioctls. A worker can
perform reads only, writes only, or one write every N operations. The runner
checks the exact number of completed reads and writes for every CPU and compares
aggregate writes with all eight values. This is a functional workload, not a
throughput comparison with TCLock.

Build and run only in the verified recovery guest, using
[the test guide](../../tests/kernel/rwlock/README.md). A loaded workload holds a
reference to its provider. Retire prepared JIT sources to release their pins before
unloading modules.
