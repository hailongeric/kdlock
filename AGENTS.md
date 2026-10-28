# Development rules

The project goal is relevant in-kernel lock replacement and evaluation of
unchanged applications such as will-it-scale `mmap1`. Follow the three stages in
[the project roadmap](docs/ROADMAP.md): micro/nano performance evidence, scoped
mmap/page-fault improvement or parity, then broader kernel integration. Current
support and performance limits remain explicit; a future milestone does not
override the implementation or VM rules below.

Linux 6.1 kernel development is retired; no further adaptation targets it.
The development VM uses Ubuntu 26.04.1 LTS and the custom
`7.0.0-38-kdlock1` kernel from authenticated Ubuntu `linux=7.0.0-38.38`
source. The [port record](bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
separates source/build identity, boot, focused checks and live validation.
Use the source/output-separated build and schema-2 bundle in
[VM operations](docs/operations/VM.md). Preserve benchmark results and the
single legacy `6.1.159-kdclobber2` recovery version under the
[retirement record](docs/history/kernel-retirement-20261027.md). Legacy commands
and measurements are historical references only. The Linux 7 mmap backend is
disabled in the ordinary development kernel; enabled compilation does not
validate actual MM execution. Active call-depth tracking is refused because
its return thunk violates the native-escape flags contract. Complete mitigation
coverage of handwritten/generated returns remains a separate limitation.

The maintained branch is `master`. Preserve the KD-only foundation selected at
`d2a2304`: KD physical exclusion, ABI2, pinned published delegation waiters,
immutable mutex images and exact source/runtime lifetime accounting. The current mutex
keeps its 32-byte native-aligned layout, shares preallocated CPU/slot storage
between independent OSQ and delegation memberships, and uses a 768-body NUMA
locality boundary. At that boundary, eight or more deferred requests receive
handoff; a smaller prefix is serviced before a bounded FIFO remainder. Keep the
total cap at 1024 by default and preserve the separate links, cancellation and
retirement obligations. The 768 default was promoted at the user's request from
exploratory cross-NUMA evidence; it is not a universal performance guarantee.
Do not restore the rejected
owned/adaptive protocol, Linux mutex backing, or parked delegation producers.
Direct `kd_mutex_lock/unlock` calls and ordinary blocking aliases use the unified
ABI2 interface; callable lock symbols and signal/try/I/O APIs execute locally.
Public unlock retains exact provider routing for every successful acquisition.
All users of an object must follow one protocol. Whole-kernel replacement,
RT/ww_mutex and lockdep integration remain separately unvalidated.

The user explicitly selected trusted kernel and module source on October 27.
Current translation skips semantic safety admission, context/loop-value analysis
and entry-input proofs; the compiler clobber-entry contract is assumed. Translate
ordinary string callees through the normal backend without named helper models.
Keep source leases, complete decoded text, faithful lowering, actual CALL/RET
words, exact return routing and runtime ownership/retirement checks. The checked
analyzer remains an explicit regression utility (`trusted_source=False`), not
the production default. Trusting source does not add missing backend support or
validate whole-kernel replacement.

1. Read source and Git status before editing. Preserve unrelated work. Maintained
   prose and comments use English. Explain protocol purpose and ordering.
2. Source edits, Git, static inspection and read-only offline archive checks run
   on `380G10`. All builds, unit tests, modules, daemons and timing run only in the
   VM on `10.176.26.71`. Follow [VM operations](docs/operations/VM.md).
3. Use basic plus directly affected checks. Full suites require an explicit user
   request. Missing dependencies, skips and compile failures are not passes.
4. Keep exact physical owners, acquisitions, source leases, unlock ACKs and frame
   retirement. Approximate counters cannot replace ownership records. Never
   remove ownership/lifetime probes to hide a reproduced failure. Preserve the
   explicitly selected source-trust policy and label its evidence separately.
5. Share existing packet/frame storage with explicit lifetime transfer; prefer
   preallocation. Avoid whole-packet copies, blanket clears or a global lock
   added only to simplify lifetime accounting. Retain required capture/restore.
6. Preserve the two-word wrapper ABI. Spin/rwlock ordinary pairs protect
   preemption and IRQ/BH state. Explicit spin IRQ variants use native interfaces;
   rwlock IRQ/BH variants are unsupported. Published mutex waiters poll pinned;
   physical mutex owners/services can sleep. Oversubscription redesign is deferred.
7. Do not modify, build, install or reboot the guest kernel by default. Captured
   kernel experiments under `kernel_baseline/experiments/` are historical inputs.
   Spin still requires spin-clobber-v1; KD mutex owns its clobber entry.
   MM integration is limited to the lock backend and minimal API/lifetime wrappers.
   Keep native MM bodies and semantics unchanged and execute them on their original
   task. Operation-specific MM body delegation and prepared teardown are retired.
8. Synchronize only while idle and never edit frozen running inputs. Confirm a
   real recovery snapshot before live module/JIT work. Bound remote commands.
   A timeout does not prove drain. Never force unload or clear `/root/host_fs`.
9. Keep benchmark and shared payloads in `workload_modules/` and benchmark runners
   in `bench/`. Keep correctness-only code in `tests/`, with kernel payloads in
   a `payload/` subdirectory beside their `tests/kernel/` runner. Provider probes
   remain in `tests/kernel/`. Include private `.inc` files in snapshots.
10. Keep one guide per responsibility. Current instructions belong in maintained
    docs; historical protocols/results belong in history or fixed Git evidence.
    Preserve captured hashes, numeric evidence, failures and topology identities.
11. Permanent real-world API testing constraint: invoke the actual API through
    its userspace system call path. Restrict kernel-side experimental changes to
    the relevant critical sections' lock API calls and minimal required lock
    binding/routing/lifetime glue. Preserve native bodies, surrounding semantics
    and data structures; prefer leaving kernel source unchanged. Extracted-body
    calls and test ioctls are mechanism evidence, not real-world API substitutes.
    See [the workload contract](docs/BENCHMARK_WORKLOADS.md#permanent-testing-constraint).

## Git and reporting

Ongoing local commits and branch organization are authorized. Review staged
changes, commit coherent work and report validation limits. Use a reviewed
path-specific restore or revert for rollback, never reset unknown work.
Keep rejected experiments and user WIP reachable through explicit archive refs.
Do not claim a performance gain without measurements; do not pool source versions,
topologies, call shells, workloads or instrumentation settings. A NORMAL image
is publication evidence, not proof of a returned JIT body.
