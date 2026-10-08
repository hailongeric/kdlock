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

Kernel entries use lookup pid 0 but retain their registering tgid. Workspace mode
is independent of lock/JIT/benchmark mode. A workspace gets `asm/`, callee and
indirect-target tables without a template. New miss targets affect future compilations;
an ordinary CALL miss finishes its present invocation natively.

## Components

| File | Responsibility |
| --- | --- |
| [daemon.c](daemon.c) | Configuration, device session and polling loop |
| [workspace.inc](workspace.inc) | Workspace commands, learned targets and cache |
| [compiler.inc](compiler.inc) | Child launch/reap and optional measurements |
| [publication.inc](publication.inc) |ABI/layout checks, native-only status and upload |

Private components remain in one translation unit and are tracked by the daemon
build and basic daemon fixture. Entry identities 0/1/2 mean legacy/spin-clobber/
mutex-clobber; the emitted layout/backend must match before upload.

## Device session and source residency

Open the device once with `O_RDWR|O_CLOEXEC` before workspace work. Snapshots,
chunks and native-only publication all use that description. I/O errors never
silently reopen it into another provider session.

Only the translator child inherits the internal `KD_DEVICE_FD`; do not set it
manually. Python validates device identity/access, duplicates it non-inheritably,
checks source INFO and queries CAPS on the same lease before inspecting real text.
Assembler/workspace children do not inherit it. The translator CLI opens its own
lease; imported real-text callers explicitly enter `device_session.session()`.
A missing/closed/mismatched inherited descriptor is an error, not policy refusal.

CAPS v2 advertises the checked mutex stack bound and static module per-CPU arena.
Unknown/old contracts clear optional bounds; current translation requires the module
arena and fails before text inspection if unavailable. Rebuild/reload matching
code rather than overriding capabilities. These bounds are not mutable admission
flags, runtime address guards or executable generations.

Real kcore text windows pin up to 64 distinct LIVE source modules, including learned
callees and cold extensions. Core text/rodata follow their declared ranges; init,
unknown/GOING text or capacity exhaustion refuses inspection. Device references
protect provider use; text pins do not retain arbitrary lock/object allocations.
[Source lifetimes](../docs/design/lifetimes.md) gives the precise boundaries.

## Publication and failures

The translator selects a reachable episode, screens all emitted blocks, lowers
registers/control flow and builds `jit.bin`. Policy refusal removes stale outputs
and returns2 (native-only); exceptions, launch/build or device failures are errors,
not successful refusals. ABI2/ABI1 MINIMAL requires matching versioned entries;
legacy artifacts cannot be relabelled clobber.

Images must be nonempty and fit 640 KiB. Upload uses chunks up to 4,000 bytes; the
final complete chunk publishes NORMAL. NORMAL does not prove execution. Current
recompilation overwrites a RIP-keyed block in place; source residency and workspace
isolation do not provide immutable code versions or complete-image generation checks.
Those changes are deferred in [TODO](../docs/TODO.md#c3-immutable-jit-publication-and-lifetime).

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
