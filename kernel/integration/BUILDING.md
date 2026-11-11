# Building the private core in the selected kernel tree

The [current evidence checkpoint](../../docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#current-evidenced-checkpoint)
records exact build/boot and scoped execution results, retained failures and
current validation limits. This guide states integration duties; its source
instructions do not establish support or performance evidence.

[The package Kconfig](../../Kconfig) exposes the opt-in bool
`CONFIG_KDLOCK_REBUILD` for x86_64 without PREEMPT_RT. It has no explicit default
or resource settings. [Kbuild](../../Kbuild) declares one built-in composite group
containing the private runtime C units and the three concrete assembly entries.
[The C target header](../target.h), force-included by the package's C flags,
rejects another architecture, PREEMPT_RT or a kernel outside the Linux 7.0 series.
It does not validate a specific source/configuration incarnation or select any
additional API, debug or context policy.

This flag packages source; it performs no automatic mutex aliasing or deployment
configuration. Managed task allocation/fork/exit, source provider, executable
loading/publication and compiler transport now have source in the package. The
flag alone does not create or configure those components. The exact kernel tree
and configured build output are absent from this repository. At source checkpoint
`c6becf81`, package target parsing/build/runtime checks were still unrun. Later
receipts now record exact target application, 26 C plus three assembly core
units, full kernel builds, kernel2 install/boot and limited native/fork execution.
Kernel3 adds one observation C unit, with separate build/boot and scoped
protected JIT fixture receipts. Kernel4 compiles the plain-spin source extension
at `2d0ad60b` with 67 exact package inputs and the same 27 C plus three assembly
units. The core and full-kernel commands returned 0. Its full-link warnings
include five handwritten returns, an indirect call, function fallthrough and
`kd_spin_native_resume` stack realignment, with the vendor and locale warnings
retained. The current checkpoint keeps these exact build stages alongside the
earlier 12 host-pipeline checks.
[Kernel4 build receipt](../../tests/evidence/kernel-build4-20261111/README.md).

Kernel4 installation and boot cover a limited module closure containing the
checked signed `nls_iso8859-1.ko` and the declared built-in boot/network
dependencies. The first spin fixture stopped at a source frontier, then
renewed ordinary recovery archived and SETTLED its five remaining facts before
normal destroy/unload. Corrected `db7d7d6e` modules built successfully and ran on
a fresh kernel4 boot. Separate spin and mutex receipts record scoped protected
recursion, with physical release and final retirement checked independently.
Full mitigation and auxiliary-stack unwind coverage remain outstanding.
[Kernel4 installation](../../tests/evidence/kernel-install4-20261111/README.md),
[corrected module builds](../../tests/evidence/module-spin-db7-build-20261111/README.md),
[current checkpoint](../../docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#current-evidenced-checkpoint).

All authorized builds, modules, tests and timing run only in the development VM.
Source edits and static inspection remain on the source host.

Use the following layout when integrating the package into the selected kernel
source tree, retaining its internal relative paths:

```text
<kernel-source>/kernel/kdlock/
    Kconfig
    Kbuild
    kernel/          private C units, headers and integration documents
    include/         private headers and assembly sources/templates
```

1. Pin the actual Linux 7.0 source revision and vendor patch set, exact `.config`,
   architecture and compiler/assembler/linker identities before integration.
   Record the kdlock source commit and any dirty changes together with the
   copied source/header/template hashes. Keep source and output trees separate
   in the future VM build. A 7.0 version check does not establish those identities.
2. Inspect [the task/lifecycle template](task_struct.patch) and
   [exact-context installer](apply_target.py) against that tree. The one root
   field and managed fork/failure/exit hooks are integration prerequisites.
   The template has synthetic hunk positions and is not an applied-tree receipt.
   The installer verifies pinned whole files and unique literal contexts; it
   refuses ambiguity, unknown partial changes and protected normal inputs.
3. Source this package from the target kernel's Kconfig hierarchy, for example
   inside its General setup menu, and add the matching descent to its
   `kernel/Makefile`:

   ```kconfig
   source "kernel/kdlock/Kconfig"
   ```

   ```make
   obj-$(CONFIG_KDLOCK_REBUILD) += kdlock/
   ```

   These are intended source insertions, not a patch applied by this package.
   Kbuild prefers this directory's `Kbuild` file over a same-directory Makefile.
4. Select `CONFIG_KDLOCK_REBUILD=y` only for that integration. The bool adds the
   core to the kernel rather than defining a loadable core-module interface.
   Kbuild uses its normal composite-object and source/output-path rules; no
   custom host invocation or generated-source rule is added here. Linux 7.0 may
   expand built-in composite members directly into `built-in.a`, so the logical
   `kdlock_rebuild.o` goal does not promise a separate intermediate file.
5. Install the managed lifecycle hooks and configure
   [current-task setup and teardown](README.md) before converted ordinary source
   pairs can run. Initial parent entry is explicit; managed children receive
   independent backing, while unmanaged tasks stay outside the lane. Storage, count, auxiliary
   bounds/cursor and full control-stack requirement are explicit caller inputs.
   This flag supplies none of them. Original tasks, child tasks, callback/module
   code and all escaped users need their actual final-use proof before teardown
   or stack/storage release. Numerical ranges do not prove auxiliary scheduler,
   IRQ, stack-overflow or unwinder compatibility.
6. Convert only a declared source lane, rebuilding every user of each selected
   object under one physical protocol. Ordinary mutex and plain-spin interfaces
   have distinct objects, initialization and source macros. Audit initialization,
   all call sites and context/lifetime use together, preserving native protected
   bodies and surrounding semantics. Plain spin source requires IRQ-enabled task
   context and preemption pins through matching source unlock. The corrected
   fixture records scoped protected completion for that lane. Callable,
   signalable, trylock, I/O, reader, mode and IRQ lanes retain their own scope.
   [Mutex source API](../../include/kd_mutex_api.h),
   [plain-spin source API](../../include/kd_spin_api.h).

At `c6becf81`, Kbuild lists 26 C units: `episode`, image slots/owners, source
epoch/provider/stack, feedback producer/pool/publication, channel/control/compiled
images/runtime/exports, canonical state/JIT, MCS/release, task roots, request
pools, owner progress, task setup/storage/lifecycle/progress and native entry/API.
Historical `a65016e3` had 15 C units and `5989fbbb` had 17; those counts describe
those revisions. `1b50e373` adds `observation.c`, making 27 C units; kernel3's
receipt records 30 object targets and the complete normal kernel build.
`include/mutex_api.S`, `include/mutex_entry.S` and `include/native_resume.S` are
concrete entries. `include/wrapper.S` contains the per-image entry/body template:
compile only a separately constructed image with those placeholders resolved,
never that unexpanded template as part of the core. Host Python/compiler sources
are not kernel build inputs of this Kbuild group.

Per-image assembly and C input metadata must match the actual source epoch,
load/configuration identities, packet/IO ABI and baked `current_task` GS offset.
The core's include paths do not establish that correspondence, acquire provider
holds or select an image loader. [Image ownership](IMAGES.md) retains those
separate construction, publication, module/code and reclamation duties. Capture
the generated metadata and the actual loaded source/build identities in any
future receipt; keep static construction, compilation, publication, returned
execution and performance evidence distinct. Record the complete mitigation,
instrumentation and unwinder configuration rather than inferring compatibility
from the version/architecture gates.

## Exact target installer

Use an isolated candidate source and separate output tree; preserve normal,
recovery, unrelated and frozen inputs. Copy the pinned package to
`<source>/kernel/kdlock` first. The stdlib installer exposes inspect, plan, apply
and verify modes. Every mode requires --tree, --build, --package,
--source-identity and --package-identity. Establish external --source-fingerprint,
--config-sha256 and --package-fingerprint pins before plan/apply/verify; inspect
output alone is not external provenance. The source fingerprint covers the top
Makefile and all five integration files, not the whole vendor tree.

Apply also requires a fresh --receipt-dir, every relevant --protected-tree and
--idle-confirmed. That flag records an actual prior controller idle/recovery
check, not a VM check performed by the installer. Before changing the five files,
it fsyncs before/after backups, exact patch, manifest and journal. New-inode
replacement preserves hardlinked normal inputs without chmod, chown or source
cleanup. Unknown partial application is refused, not automatically resumed.
Verify reconstructs pins and the exact recipe, then checks actual applied bytes.
No mode builds, enables configuration, installs or reboots. Retain exact apply/
verify receipts separately from source-only review of the synthetic template.

The Kbuild form was inspected against the Linux 7.0
[makefile documentation](https://docs.kernel.org/7.0/kbuild/makefiles.html),
[build rules](https://github.com/torvalds/linux/blob/v7.0/scripts/Makefile.build)
and [flag rules](https://github.com/torvalds/linux/blob/v7.0/scripts/Makefile.lib).
That primary-source read supports the declared build structure and flags; it is
not itself a parsed or compiled receipt for the selected vendor tree. Actual
target application/build results are retained separately in the current
checkpoint. Managed provisioning/lifecycle/provider hooks are source-present;
limited native/fork execution does not complete auxiliary/context proof.
