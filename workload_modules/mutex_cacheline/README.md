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
| `SC_BACKEND=kdlock` | Original `struct mutex`; outer caller CAS/cookie pair, contended direct clobber entry and named `mc_entry_*` JIT continuations |
| `SC_BACKEND=kdlock SC_MUTEX_OWNED=1` | Separate 32-byte KD `struct kd_mutex`; owned outer cookie, registry kind 3, default ABI2 or opt-in ABI4, c01 only |

The owned arm includes `kd_owned_mutex_direct.h`, initializes with
`kd_mutex_init`, prepares with `kd_owned_mutex_prepare`, and checks
`kd_owned_mutex_is_idle` after all workers join. It uses the same lock alignment and
payload counters as Native. It does not reinterpret a Linux mutex
or share its object with native consumers. Other cacheline sizes and the hash
payload are rejected for this initial implementation; kernel-owned real-API
workloads continue using the legacy interface. Module metadata records the
actual compiled implementation for the runner to verify.

`KD_OWNED_MUTEX_CABI=1` selects the ordinary-C ABI4 caller, which tries KD-owned
local acquisition before late capture. The runner's measured c01 profile also
sets `--owned-mutex-reuse-spins 32`; that is an explicit selection, while the
provider default is 0. Both arms retain the same 32-byte public object and
64-byte-aligned lock slot, separate from the shared counter line. The payload's
[post-work source](../spin_cacheline/post_work.h) currently selects 64 rounds.
Optional origin-readiness and NUMA policies belong to the provider and runner;
they do not change this c01 body or its object layout. Use the separate
[policy comparison](../../bench/tclock_compare/README.md#owned-origin-and-numa-comparison)
to measure them against fresh frozen-KD, Native and TCLock controls.

The paired KD outer cookie records the exact acquisition route for one lexical
acquisition. Owned SELF uses KD's physical owner and borrowed FULL uses exact
owner ACKs; it never routes the target to Linux mutex APIs. General direct mutex
interfaces remain available for nested control calls; they are not substituted
for the outer caller's fast path.
See [mutex implementation](../../docs/design/mutex_implementation.md) and
[ownership protocols](../../docs/design/lock_protocols.md).

Clients register TCLock workers after pinning/naming and before reporting ready.
Context allocation and registration occur before measurement. After every
worker joins, TCLock context drain may return EBUSY while an exiting task is
still alive; the client retries outside timing. KD delegates use blocking waits
after bounded result polling, retaining migration pins while asleep. Owned SELF
uses separate Linux-style optimistic spinning and sleeping. TCLock supports
parking. The target lock is never shared between
these incompatible backend protocols.

For a standalone Native build in the recovery guest:

```sh
make -C workload_modules/mutex_cacheline \
  KDIR=/root/linux-6.1.159-kdclobber2 SC_BACKEND=native
```

The [mutex runner](../../bench/tclock_compare/run_mutex.py) builds the other
arms with the correct provider/include paths and `Module.symvers`, prepares
KD translations, registers all workers, performs warmup, verifies payload and
returned-body JIT/delegation evidence, and drains, retires sources and unloads modules in order.
Commands, the full thread set, UBSAN-off provider policy and statistics are
maintained in the [comparison README](../../bench/tclock_compare/README.md).
Owned `KD_SELF`/`ADAPTIVE_SELF`, legacy native execution and returned-JIT samples
remain distinct. The [full-grid command](../../bench/tclock_compare/README.md#owned-c01-full-grid)
uses the owned profile explicitly; the general runner still defaults to legacy.

The default workload supports plain ordinary mutex operations. Owned c01 also
supports `SC_SCENARIO=1` (nested) and `2` (early outer release), selected only by
the runner's `--functional` KD-only one-round mode. A distinct aligned inner
owned mutex uses the direct clobber interface; both objects must be idle at drain.
The owned early probe alternates LIFO and early release using protected counter
parity. Native early A release cannot combine while B remains held; LIFO callers
provide executors for queued early-release bodies. Acceptance requires a returned
JIT body and an observed delegated early outer release. This probe never scores
as c01 throughput. `--owned-mutex-force-full` additionally requests one validated
post-control native continuation, requiring both physical-owner acknowledgments.
The plain timed body has no inner object or scenario operations. General
oversubscription, PI/RT/WW mutexes and arbitrary context-sensitive bodies are
outside its validated scope. Build and run only under the documented
[guest operations procedure](../../docs/AGENTS.md).
