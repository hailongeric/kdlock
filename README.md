# kdlock

kdlock is an experimental x86_64 Linux lock library. A physical lock holder can
execute waiting callers' critical sections through generated code, then return
each caller after its completed work. The project goal is relevant in-kernel lock
replacement and evaluation of unchanged applications such as will-it-scale
`mmap1`.

The [roadmap](docs/ROADMAP.md) has three stages: demonstrate a useful lock
micro/nano performance envelope; establish scoped mmap/page-fault improvement or
parity; then complete declared kernel replacements and compare applications.
Favorable exploratory nano cases and scoped application measurements exist.
Repeated performance acceptance and broader kernel replacement remain open.
The isolated [original JIT correction](docs/design/kdlock_lock_replacement_contract.md)
has production source at `da55414f`. Subsequent frozen checks resolve the
observed component failures, including service acceptance/final ACK and
retirement fixtures. The [source-specific evidence](bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/README.md)
preserves every failed attempt and the limits of supplied task/CPU primitives.
The later [live probe](docs/design/kdlock_lock_replacement_contract.md#partial-live-probe-and-current-stop)
passes cold CALL and indirect-JMP handback at `58af0a53`. Its exact post-RET
observations accompany a failed overall checker result. Candidate `bccf877c`
adds untested harness fixes; that targeted probe remains failed. Later normal
mmap1 campaigns have separate source-specific receipts. The latest
[proxy-read point](bench/results/10.176.26.71/bench/mmap1-proxy-read-7e3c90b4-v3/README.md)
at `7e3c90b4` passed one compile-excluded eight-process interval: 25,670.9 pairs
per nominal second with selected-service counters enabled. Both mmap and munmap
returned every JIT entry across the whole fixed application; exact retirement,
unload and normal-kernel recovery passed. Quiet performance, Native improvement
and repeated acceptance remain open. The result does not validate the union
with master's independent flags-stack changes.

## Current platform and policy

The VM uses **Ubuntu 26.04.1 LTS** and normal kernel **`7.0.0-38-kdlock1`**, built
from authenticated Ubuntu `linux=7.0.0-38.38` source containing upstream 7.0.14.
The ordinary development image disables the mmap backend. Historical local-MM
experiments used `7.0.0-38-kdmm1` Native/KD modes; later scoped and retained
kernels have separately recorded source, configuration and boot identities.
Linux 6.1 development is retired; results and one legacy recovery version remain
preserved.
[VM operations](docs/operations/VM.md) owns paths, identity, dependencies and recovery.

Production trusts all kernel/module source, including loops. It skips semantic
safety, context/value and entry-input proofs; the compiler clobber-entry agreement
is assumed. Strings use ordinary decoded CALL/RET, without named models, services
or direct native bridges. Source leases, complete selected text, faithful lowering,
actual return words and exact runtime ownership/retirement remain required.
The checked analyzer is an explicit regression utility, `trusted_source=False`.
See [translation policy](docs/design/admission.md).

## Lock interfaces

These are the ordinary family interfaces. Separately activated retained service
capture has the additional root/owner contracts described in the correction.

| Family | Supported execution model |
| --- | --- |
| Spin | Exclusive ordinary pinned pair; eligible bodies may delegate; explicit IRQ/BH variants execute locally |
| Mutex | KD-owned physical exclusion; direct public blocking calls and aliases use ABI2; callable/signal/try/I/O forms execute locally |
| Rwlock | Concurrent local readers; exclusive ABI3 writers may delegate after writer admission |
| Rwsem | Concurrent local readers and ordinary local writers; explicit outer ABI2 writers reserve/drain before delegation |

The maintained mutex is 32 bytes with native alignment. It shares preallocated
CPU/slot storage between separate OSQ and delegation memberships. Defaults are
batch cap 1024 and NUMA boundary 1024, removing the earlier count-based local
cutoff. Terminal/deferred queue handling and bounded FIFO service remain intact.
KD spin retains its 1024-body limit. The user selected these defaults; no new
performance gain is established.

Published mutex waiters poll pinned; physical owners may sleep. Every user of an
object must follow one protocol. Public unlock retains exact acquisition routing.
Loading the provider does not replace unrelated Linux locks. Whole-kernel,
RT/ww_mutex/lockdep, broad oversubscription and complete mitigation coverage remain
separately unvalidated. [Lock APIs](docs/LOCKS.md) and [open work](docs/TODO.md)
define the current boundary.

The historical local MM adapter changes only the lock backend and minimal
API/lifetime wrappers; its native bodies run on the original task (O). Later
retained candidates execute unchanged native bodies on the executor (E) through
general lock and service routing. The selected correction uses the original JIT and returns untranslated
code to O at its current source position, without replay. This remains kdlock
lock replacement; operation-specific MM algorithms and prepared teardown are
retired. The contract separates required behavior from implemented and verified
behavior, including deferred flags/SIMD restoration and IRQ/NMI conflicts.

## Results and validation

The [October 28 Linux 7 catalog](bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
selects **52 full lock/API configurations plus three MM suites: 3,402 points**.
It keeps 29 checked-source, 22 trusted-source and one prepared lock/API cohort
separate, alongside distinct private/shared-MM identities. Each coordinate has
one two-second round at fixed 2 GHz host policy. All timing is exploratory;
strict qualification remains failed and no repeat variance is available.

That catalog's mutex nano profiles exceed Native and TCLock at the measured
60-worker point, with adverse/local points retained in their full curves. Its
shared-device-MM workload loses to Native at all 21 counts. The separate
[November 1 campaign](bench/results/10.176.26.71/bench/master-native-20261101/README.md)
runs unchanged mmap1 threads/processes and original-body syscalls, retaining
both gains and losses from one round per point. These workloads, source versions
and controls are not interchangeable, and no repeated acceptance gate follows.

The [indexed reached JIT record](bench/results/10.176.26.71/tests/reached-mm-jit-indexed-20261104/README.md)
contains later focused actual-mmap1 execution proofs for the superseded separate
emitter, with failed performance acceptance and no Nano run. It does not validate
the restored original JIT correction. See the original contract's
[current validation record](docs/design/kdlock_lock_replacement_contract.md#validation-and-remaining-work)
for its distinct passes, failures, partial live handback and remaining joins.

The [fresh normal-kernel basic checkpoint](bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
passed all four selected families with correct data, returned JIT bodies and final
drain. Failed partial campaigns, the initial MM witness failure and strict
unscored taskname `NO_JIT` control remain recorded. [Validation](docs/VALIDATION.md)
separates those verdicts. `NORMAL` means publication, not returned execution.

## Working in the repository

[Documentation index](docs/README.md) assigns one guide per responsibility.
[Code map](docs/CODE_MAP.md) locates implementation and test ownership.
[Public headers](include/README.md), [benchmark runners](bench/README.md) and
[test selection](tests/README.md) own their interfaces and commands.
[Historical evidence](docs/history/README.md) retains superseded protocols,
campaign plans and full earlier status narratives at fixed Git checkpoints.

`master` is maintained. Source edits, Git and static/offline review run on
`380G10`; all builds, tests, modules, daemons and timing run only in the designated
VM. Follow [development rules](AGENTS.md): preserve exact owners, source leases,
unlock ACKs and frame retirement; synchronize only while idle; verify recovery
before live work; never force unload or treat timeout as drain.
