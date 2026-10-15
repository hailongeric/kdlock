# Translation daemon

The daemon polls registered entries, launches the Python translator and uploads
images through one `/dev/kd_dev` session. [The project guide](../docs/PROJECT_GUIDE.md)
owns guest setup; [admission](../docs/design/admission.md) and
[register ABI](../docs/JIT_REGISTER_ABI.md) own translation/packet contracts.
Do not start a second daemon alongside a runner-managed session.

## Build and CLI

Build and run in the recovery guest after loading the matching provider:

```sh
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cd daemon
./daemon --mode per-tgid
```

Put the pinned venv's `bin` first in PATH: the daemon uses `execlp("python3", ...)`
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
them. Workspace mode changes directory organization; it does not select the lock,
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
| [publication.inc](publication.inc) | ABI/layout checks, native-only status and upload |

Private components remain in one translation unit and are tracked by the daemon
build and basic daemon fixture. Entry ABIs 0/1/2/3/4 mean spin-full-context/spin-clobber/
owned-mutex-clobber/rwlock-writer-clobber/owned-mutex-ordinary-C. ABI3 uses the spin
backend with native writer admission before the prepared body. ABI4 uses owned
lock kind 3 and the late-capture nonvolatile-register contract. The emitted
layout/backend/ABI must match before upload. Replace callers, provider, daemon
and translator together when changing those identities.

## Device session and source residency

Open the device once with `O_RDWR|O_CLOEXEC` before preparing workspaces. Use that
same open file description for snapshots, code chunks and native-only publication.
If I/O fails, report the error. Silently reopening the device would start a different
provider session and lose the original lifetime guarantee.

Only the translator child inherits the internal `KD_DEVICE_FD`; do not set it
manually. Before reading real code, Python checks the device identity and access
mode, makes a duplicate that its own children cannot inherit, and queries source
INFO and CAPS through that same session. Assembler and workspace children do not
inherit the descriptor.

The standalone translator CLI opens its own session. Code importing the translator
for real source inspection must explicitly enter `device_session.session()`. A
missing, closed or wrong inherited descriptor is an infrastructure error, not a
successful decision to run the body natively.

CAPS v3 advertises the checked mutex stack bound, static module per-CPU arena and
immutable owned-image publication. Current translation rejects a missing image
capability before text inspection, and requires the module arena. Raw observers
can still inspect older CAPS contracts. Rebuild/reload matching code rather than
overriding capabilities; these bounds are not runtime address guards.

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
the matching versioned entry; ABI4 requires its CALLEE_ENTRY contract and owned
backend identity. A full-context spin image cannot be relabelled as clobber or
ABI4 code.

Images must include the 48-byte wrapper directory and fit 640 KiB. The 64-byte
version 2 upload header identifies the entry ABI, context requirements, upload,
declared length and base generation. Chunks cover the image contiguously; the
final validated chunk publishes NORMAL. That status does not prove execution.
Owned images stage in separate blocks and publish immutable descriptors retained
until session teardown. A replacement cannot change a frame's bound version;
an old miss cannot overwrite a newer version's status. The 64-block pool rejects
exhausted replacements. Interrupted uploads return only their unpublished block.
See [the publication lifecycle](../docs/JIT_EXECUTION.md#owned-image-publication-protocol-2).
Spin/rwlock image families still overwrite their RIP-indexed block, as tracked in
[TODO](../docs/TODO.md#c3-immutable-jit-publication-and-lifetime).

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
