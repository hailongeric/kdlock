# Building the private core in the selected kernel tree

[The package Kconfig](../../Kconfig) exposes the opt-in bool
`CONFIG_KDLOCK_REBUILD` for x86_64 without PREEMPT_RT. It has no explicit default
or resource settings. [Kbuild](../../Kbuild) declares one built-in composite group
containing the private runtime C units and the three concrete assembly entries.
[The C target header](../target.h), force-included by the package's C flags,
rejects another architecture, PREEMPT_RT or a kernel outside the Linux 7.0 series.
It does not validate a specific source/configuration incarnation or select any
additional API, debug or context policy.

This is source packaging. It performs no mutex aliasing, task allocation,
fork/exit integration, source capture/provider construction, generated-code
allocation/publication or compiler/feedback transport. The exact kernel tree
and configured build output are absent from this repository. No Kconfig/Kbuild
parser, preprocessing, compilation, assembly, linking or runtime check has run
for these files. Builds and tests remain deferred until the overall ordinary
lane and its integration duties are complete; when authorized, all builds,
modules, tests and timing run only in the development VM. Source edits and
static inspection remain on the source host.

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
2. Rebase and inspect [the task field template](task_struct.patch) against that
   exact tree. `task_struct.kd_root_context` is a build prerequisite. The copied
   child's alias must be cleared before child publication or cleanup can use it;
   the template supplies no task-time allocation/attach or exit/drain hook.
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
5. Wire [current-task setup and teardown](README.md) and the actual task lifecycle
   before any converted ordinary source pair can run. Storage, count, auxiliary
   bounds/cursor and full control-stack requirement are explicit caller inputs.
   This flag supplies none of them. Original tasks, child tasks, callback/module
   code and all escaped users need their actual final-use proof before teardown
   or stack/storage release. Numerical ranges do not prove auxiliary scheduler,
   IRQ, stack-overflow or unwinder compatibility.
6. Convert only the declared ordinary mutex lane, rebuilding every user of each
   selected object under one physical protocol. The private `struct kd_mutex`,
   initializer and `kd_mutex_lock`/`kd_mutex_unlock` source macros are not automatic
   replacements for Linux `struct mutex` or every mutex API. Audit object
   initialization, all call sites and context/lifetime use together; keep native
   protected bodies and surrounding semantics unchanged. The packaging flag
   enables no callable, signalable, trylock, I/O, reader, mode or IRQ lane.

The explicit core list includes `episode`, image slots/owners, source epochs,
canonical state/JIT bridges, MCS arbitration/release, task roots, request pools,
owner progress, task setup/progress and native entry/API C units.
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

The Kbuild form was inspected against the Linux 7.0
[makefile documentation](https://docs.kernel.org/7.0/kbuild/makefiles.html),
[build rules](https://github.com/torvalds/linux/blob/v7.0/scripts/Makefile.build)
and [flag rules](https://github.com/torvalds/linux/blob/v7.0/scripts/Makefile.lib).
That primary-source read supports the declared build structure and flags; it is
not a parsed or compiled receipt for the selected vendor tree. The target field
patch, actual provisioning/lifecycle/provider hooks and full auxiliary/context
integration still need their own source and execution evidence.
