# Translation daemon

The daemon polls registered entries, launches the Python translator and uploads
images through one `/dev/kd_dev` session. [The project guide](../docs/PROJECT_GUIDE.md)
owns guest setup; [admission](../docs/design/admission.md) and
[register ABI](../docs/JIT_REGISTER_ABI.md) own translation/packet contracts.
Do not start a second daemon alongside a runner-managed session.
JIT means just-in-time compilation; ABI means application binary interface.
The [terminology guide](../docs/TERMINOLOGY.md) defines execution and lifetime terms.

## Build and command-line interface

Build and run in the recovery guest after loading the matching provider:

```sh
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cd daemon
./daemon --mode per-tgid
```

Put the pinned Python virtual environment's `bin` first in PATH: the daemon uses `execlp("python3", ...)`
and inherits PATH. `VIRTUAL_ENV` alone does not choose Python; do not upgrade global
packages. [requirements.txt](../disassem/requirements.txt) specifies dependency pins.

| Option | Meaning |
| --- | --- |
| `--mode per-tgid`, default | Workspace `<RIP>/<tgid>/`; aliases 2/v2 |
| `--mode flat` | Workspace `<RIP>/`; aliases 1/v1 |
| `--poll-us N` | Poll interval; default 100,000 microseconds |
| `--quiet` | Suppress routine progress |
| `--verbose` | Initialization/miss/compiler messages |
| `--metrics` | Additional compiler-child wall/CPU/resource JSON; off by default |

Kernel entries use pid 0 for lookup but keep the tgid of the process that registered
them. Here pid is a process identifier, tgid a thread-group identifier and RIP the
entry instruction address. Workspace mode changes directory organization; it does not select the lock,
JIT or benchmark mode. The daemon creates `asm/` and the callee/indirect-target tables
without a template. A newly discovered call target can be included in a later
compilation. The current invocation still finishes natively after an ordinary
CALL miss.

## Components

| File | Responsibility |
| --- | --- |
| [daemon.c](daemon.c) | Configuration, device session and polling loop |
| [workspace.inc](workspace.inc) | Workspace commands, learned targets and cache |
| [compiler.inc](compiler.inc) | Child launch/reap and optional measurements |
| [publication.inc](publication.inc) |ABI/layout checks, native-only status and upload |

Private components remain in one translation unit and are tracked by the daemon
build and basic daemon fixture. Entry identities 0/1/2/3 mean legacy/spin-clobber/
mutex-clobber/rwlock-writer-clobber. ABI3 uses the spin backend with native writer
admission before the prepared body; the emitted layout/backend must match before
upload. Rebuild the daemon and translator with ABI3 rwlock callers and provider.

## Device session and source residency

Open the device once with `O_RDWR|O_CLOEXEC` before preparing workspaces. Use that
same open file description for snapshots, code chunks and native-only publication.
If I/O fails, report the error. Silently reopening the device would start a different
provider session and lose the original lifetime guarantee.

Only the translator child inherits the internal `KD_DEVICE_FD`; do not set it
manually. Before reading real code, Python checks the device identity and access
mode, makes a duplicate that its own children cannot inherit, and queries source
INFO (source-session status) and CAPS (provider capabilities) through that same
session. Assembler and workspace children do not
inherit the descriptor.

The standalone translator CLI opens its own session. Code importing the translator
for real source inspection must explicitly enter `device_session.session()`. A
missing, closed or wrong inherited descriptor is an infrastructure error, not a
successful decision to run the body natively.

CAPS version 12 retains the checked mutex stack bound and static module per-CPU
arena introduced in v1/v2. Bits 3 and 4 describe immutable mutex images and
exclusive KD mutex objects; bits 5 and 6 describe checked instruction exits and
restricted ABI1 spin address exits. Bits 7 and 8 identify the original `strcmp`
and `strscpy_pad` APIs. Bit 9 states that these APIs rely on the original C
caller's valid memory and lifetime, without helper-specific checks. Current
translation requires bit 9 as well as the appropriate API bit before using
these service summaries.
Optional bit 10 permits direct original-helper calls inside one generated
invocation; otherwise eligible string bodies retain the dispatcher route.
Bit 11 separately permits immutable ABI1/3 root instruction exits, requiring
bit 5 as well. These images require exactly 33 and admit no nested control or
service continuation.

Ordinary images accept compatible versions 5 through 12. Mutex instruction
markers require versions 6 through 12 with bit 5; spin address-check images
require versions 7 through 12 with bit 6. Older service contracts remain readable
by observers, but do not authorize the current string summaries. Rebuild/reload
the provider, daemon and translator together. Fixed stack and module bounds
describe implementation behavior; they do not establish arbitrary object validity.

Real kcore text windows pin up to 64 distinct LIVE source modules, including learned
callees and cold extensions. Core text/rodata follow their declared ranges; init,
unknown/GOING text or capacity exhaustion refuses inspection. Device references
protect provider use; text pins do not retain arbitrary lock/object allocations.
[Source lifetimes](../docs/design/lifetimes.md) gives the precise boundaries.

## Publication and failures

The translator selects the code this invocation could reach, checks every block
it will emit, rewrites register and control-flow operations, and builds `jit.bin`.
If the code violates admission policy, it deletes stale outputs and returns 2
(native-only). Exceptions or failures to launch, build or access the device are
errors, not successful policy refusals. MINIMAL entry for ABI1/ABI2/ABI3 requires
the matching versioned entry. A legacy image cannot be relabelled as clobber code.

Images must fit 640 KiB and include the 48-byte protocol/ABI directory. Uploads
use chunks of at most 4,000 bytes with a common upload ID, image length and base
generation. Complete contiguous coverage and matching directory metadata are
required before NORMAL publication; NORMAL alone does not prove execution.

In the current implementation, mutex uploads stage a new immutable block and bind
its generation to each frame. Old versions remain until session teardown, and old
misses cannot overwrite current generation metadata. The first address-check
or string-service image similarly moves its ABI1 spin entry to immutable versions.
An ABI1/3 root instruction-marker image makes the same transition. Later uploads
remain immutable even without optional requirements. Other spin/rwlock entries
retain in-place storage. Deploy the matching provider,
daemon and translator together. Mutex instruction markers set directory
requirement bit 0; spin address checks set bit 1 and include a validated source
instruction directory. Read-only string services set bit 2; writing services
set bit 3 and cannot run on a provider advertising only the read-only contract.
ABI1/3 root instruction markers require exactly bits 0 and 5, value 33.
Direct string-call images additionally set bit 4, value 16, and contain a
`KDNC0001` directory naming generated CALL operands. Publication fills their
relative helper addresses in separate preallocated storage near kernel text.
The uploaded `jit.bin` still contains zero placeholders: evidence for executed
bytes must also retain the loaded generated image and its relocation receipt.
The benchmark reads these bytes outside worker timing. This checks generated
image construction and residency; it reads no helper or source CALL instructions.
A reached instruction marker or failed address check disables the stable entry
under the publication gate, so a concurrent upload cannot reopen it.
Translation refuses bodies needing both source constant-branch simplification
and spin address checks, because the flag proof must cover the original native
suffix, including branches that generated code might otherwise remove.

String services invoke the original kernel APIs with the original arguments.
No phase verifies the helper instructions. Runtime and publication perform no
string scans or destination-bound rechecks. The translator still accounts
for each API's register and memory effects; the caller supplies valid stable
memory as for a native call. Common KD ownership, frame and pending CALL return
bookkeeping remain mandatory. The limits are 128 `strcmp` calls and 16 other
continuations, including `strscpy_pad`; quota fallback retains the unexecuted
CALL and earlier effects. Every session must drain and retire normally. The
[API admission rules](../docs/design/admission.md#original-strcmp-service)
define the caller's obligations and separate writing effects.

The optional [direct-call route](../docs/design/admission.md#direct-original-helper-calls)
accepts only a pristine ABI1 spin root and cannot reenter after a FULL exit.
It preserves the actual source CALL word and enforces the same invocation
allowances, returning an excess unexecuted call to the original waiter. Its
private result counters do not change the two-word wrapper ABI or KD mutex
protocol. The final `05876a4` bridge passed its
[focused wrapper and live checks](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks).
Its [diagnostic profiles](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#final-diagnostic-profiles)
completed with tracing restored. The separate
[standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed 567 validated sessions for read-only taskname and xattr tail with 16
and 128 entries. Archive audits and the additional live quota control remain
separate from these throughput results.

The preceding v10 dispatcher implementation passed
[focused VM correctness checks](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md#final-live-acceptance)
through candidate 6 and completed all 567 sessions of the
[`88bb5a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
with validation and drain. This does not establish mutation-case delegation,
performance parity with Native/TCLock, a full-suite pass or whole-kernel support.
The frozen `c79d84f` checked implementation's
[functional receipts](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
and [comparison record](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/README.md)
remain historical evidence for that source version. Its preliminary string
checks and resulting native fallback are no longer current behavior. See
[checked spin exits](../docs/JIT_REGISTER_ABI.md#checked-spin-address-exit) and
[the mutex compatibility backport](../docs/history/legacy_mutex_compatibility.md)
for their independent contracts.

## Optional translation measurements

`--metrics` emits `KD_TRANSLATION_METRICS` on stderr for each reaped child: entry,
pid/tgid/backend, child identity, wait status and classified result 0/2/-1.
`wall_ns` spans launch through reap, including Python analysis/build children and
scheduling. It excludes polling, workspace preparation, upload and JIT execution.
`user_ns/system_ns` are wait4 CPU observations; `maxrss_kib` is largest-process RSS,
not a sum across the tree. Keep errors/refusals and incomplete records.

A compiler gain does not prove publication or execution. Do not add overlapping
translation and preparation durations. Separate function profiling uses the existing
[translator CLI](../disassem/README.md) in an isolated workspace after workers/daemon
drain, with the source session still ACTIVE; it does not upload that image.

## Shutdown

Stop new calls and wait for daemon/translators before source retirement and unload.
A surviving translator keeps the device/provider reference even if its parent exits.
On EBUSY or a blocked child retain the evidence/pins and diagnose; never force unload.
Replace workload/provider/JIT sessions together rather than reusing stale RIP keys.
