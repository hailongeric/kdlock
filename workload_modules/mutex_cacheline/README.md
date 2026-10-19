# Ordinary mutex workload

`module.c` supplies separate Native/TCLock/KD ordinary mutex functions and
produces `mutex_cacheline.ko` with `/dev/mutex_cacheline`. It includes shared
payload/ioctl/timing helpers from `../spin_cacheline`; operation bodies do not
branch on a runtime lock-kind flag. The runner selects cacheline or RCUHT at
build time, using the same payload source for all three arms.

| Build arm | Lock object and operations |
| --- | --- |
| `SC_BACKEND=native` | Original `struct mutex`; `(mutex_lock/unlock)` bypass the experiment's caller-clobber macros |
| `SC_BACKEND=tclock` | `struct komb_mutex`; actual upstream ordinary mutex port and fixed-affinity worker registration |
| `SC_BACKEND=kdlock` | 32-byte, native-aligned `struct kd_mutex` plus lazy delegation records; outer caller CAS/cookie pair, contended direct clobber entry and named `mc_entry_*` JIT continuations |

The paired KD outer cookie records the exact local acquisition result for one lexical
acquisition. General direct mutex interfaces remain available for nested
control calls; they are not substituted for the outer caller's fast path.
See [mutex implementation](../../docs/design/mutex_implementation.md) and
[ownership protocols](../../docs/design/lock_protocols.md).

Clients register TCLock workers after pinning/naming and before reporting ready.
Context allocation and registration occur before measurement. After every
worker joins, TCLock context drain may return EBUSY while an exiting task is
still alive; the client retries outside timing. KD keeps its selected pinned
waiter policy; TCLock supports parking. The target lock is never shared between
these incompatible backend protocols.

For a standalone Native build in the recovery guest:

```sh
make -C workload_modules/mutex_cacheline \
  KDIR=/root/linux-6.1.159-kdclobber2 SC_BACKEND=native
```

The [mutex runner](../../bench/tclock_compare/run_mutex.py) builds the other
arms with the correct provider/include paths and `Module.symvers`, prepares
KD translations, registers all workers, performs warmup, verifies payload and
returned-body JIT/delegation evidence, and drains/retire/unloads in order.
Commands, the full thread set, UBSAN-off provider policy and statistics are
maintained in the [comparison README](../../bench/tclock_compare/README.md).
KD-only low-contention native samples remain distinct from JIT positives.

This workload supports plain ordinary mutex operations. Spin nested/early
scenario recipes do not automatically apply to this mutex module. General
oversubscription, PI/RT/WW mutexes and arbitrary context-sensitive bodies are
outside its validated scope. Build and run only under the documented
[guest operations procedure](../../docs/operations/VM.md).
