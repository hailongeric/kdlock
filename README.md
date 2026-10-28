# kdlock

kdlock is an experimental x86_64 Linux lock library. A physical lock holder can
execute waiting callers' critical sections through generated code, then return
each caller after its completed work. The project goal is relevant in-kernel lock
replacement and evaluation of unchanged applications such as will-it-scale
`mmap1`.

The [roadmap](docs/ROADMAP.md) has three stages: demonstrate a useful lock
micro/nano performance envelope; establish scoped mmap/page-fault improvement or
parity; then complete declared kernel replacements and compare applications.
Favorable nano cases exist. The current actual shared-MM performance objective
remains unmet, and broader kernel replacement remains planned.

## Current platform and policy

The VM uses **Ubuntu 26.04.1 LTS** and normal kernel **`7.0.0-38-kdlock1`**, built
from authenticated Ubuntu `linux=7.0.0-38.38` source containing upstream 7.0.14.
The ordinary kernel disables the mmap backend. A separate `7.0.0-38-kdmm1` image
has explicit Native/KD modes for actual shared-MM experiments. Linux 6.1
development is retired; results and one legacy recovery version remain preserved.
[VM operations](docs/operations/VM.md) owns paths, identity, dependencies and recovery.

Production trusts all kernel/module source, including loops. It skips semantic
safety, context/value and entry-input proofs; the compiler clobber-entry agreement
is assumed. Strings use ordinary decoded CALL/RET, without named models, services
or direct native bridges. Source leases, complete selected text, faithful lowering,
actual return words and exact runtime ownership/retirement remain required.
The checked analyzer is an explicit regression utility, `trusted_source=False`.
See [translation policy](docs/design/admission.md).

## Lock interfaces

| Family | Supported execution model |
| --- | --- |
| Spin | Exclusive ordinary pinned pair; eligible bodies may delegate; explicit IRQ/BH variants execute locally |
| Mutex | KD-owned physical exclusion; direct public blocking calls and aliases use ABI2; callable/signal/try/I/O forms execute locally |
| Rwlock | Concurrent local readers; exclusive ABI3 writers may delegate after writer admission |
| Rwsem | Concurrent local readers and ordinary local writers; explicit outer ABI2 writers reserve/drain before delegation |

The maintained mutex is 32 bytes with native alignment. It shares preallocated
CPU/slot storage between separate OSQ and delegation memberships. Defaults are
batch cap 1024 and NUMA boundary 768, with handoff for at least eight deferred
requests and bounded FIFO service after a smaller prefix. The promoted locality
policy is an exploratory choice, not a universal optimum.

Published mutex waiters poll pinned; physical owners may sleep. Every user of an
object must follow one protocol. Public unlock retains exact acquisition routing.
Loading the provider does not replace unrelated Linux locks. Whole-kernel,
RT/ww_mutex/lockdep, broad oversubscription and complete mitigation coverage remain
separately unvalidated. [Lock APIs](docs/LOCKS.md) and [open work](docs/TODO.md)
define the current boundary.

The MM adapter changes only the lock backend and minimal API/lifetime wrappers.
Native mmap/munmap/advice/fault bodies execute unchanged on their original task.
Operation-specific MM delegation and prepared teardown are retired.

## Results and validation

The [completed Linux 7 catalog](bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
selects **52 full lock/API configurations plus three MM suites: 3,402 points**.
It keeps 29 checked-source, 22 trusted-source and one prepared lock/API cohort
separate, alongside distinct private/shared-MM identities. Each coordinate has
one two-second round at fixed 2 GHz host policy. All timing is exploratory;
strict qualification remains failed and no repeat variance is available.

Both mutex nano profiles exceed Native and TCLock at the measured 60-worker
point, with adverse/local points retained in their full curves. Actual shared-MM
KD throughput is below Native at all 21 measured worker counts. Those observations
do not establish universal gains or scoped MM parity. See
[performance](docs/PERFORMANCE.md) for current tables and interpretation.

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
