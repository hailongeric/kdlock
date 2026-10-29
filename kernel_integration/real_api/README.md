# Scoped native syscall lock binding

This candidate preserves the native Linux 7 `set_close_on_exec`, pipe
`FIONREAD` and `F_GETPIPE_SZ` bodies. It changes their lock call shells and the
initialization, routing and destruction of the two affected lock classes.
All other users of a bound file table or pipe acquire the same KD word locally.
The Native control uses the same added object layout and syscall call shells.
Existing copied-body adapters are mechanism evidence, not acceptance for this
integration. No performance result or whole-kernel support is claimed.

The authenticated input is Ubuntu `linux=7.0.0-38.38`, upstream 7.0.14. The
generator checks exact source hashes and writes a separate overlay; it does not
build, install or reboot. All preparation, compilation and execution belong in
the maintained VM and remain separately recorded. This package starts from the
maintained runtime selected by `8129490927416bc82c8b033a02de5b65b1ed74db`; it does
not import the unpromoted mutex optimization branch.

## Object protocol and lifetime

The existing lock member becomes a typed Native/KD union of identical size and
alignment. An immutable provider pointer is appended to `files_struct` and
`pipe_inode_info`; NULL selects Native. Each KD object owns one provider module
reference from initialization before publication through its final destruction.
No live object is retagged, and KD objects never acquire a Linux lock as backing.
Typed member conversion exposes remaining Native lock uses to compilation.

Setup selects an exact current task and a bounded number of subsequent file
table/pipe creations. The launcher uses normal `unshare(CLONE_FILES)` and pipe
creation, then clears the selector before workers start. Sharing or passing an
existing object preserves its backend. Setup controls are outside the measured
syscalls. Failed creation rolls back its exact provider reference; no implicit
Native substitution is permitted for an explicitly selected KD creation.

The single loadable KD provider owns all KD queue, CPU, frame and source state.
API binding is an explicit load-time option, `api_bind=1`; its read-only module
parameter defaults to off. Ordinary nano/basic providers therefore register only
their workload entries. With binding off, API setup/query controls refuse the
request. The actual-syscall benchmark and semantic test enable binding in both
Native and KD arms and retain the parameter readback before starting clients.
The built-in bridge contains binding and dispatch only. A second local-only KD
runtime would create incompatible queue state and is not used. Destruction keeps
the provider through native close/buffer callbacks, verifies the KD object is
idle and drops its reference immediately before object storage is freed.
Provider unload requires selectors and all bound objects to be gone, in addition
to the existing source/frame/queue drain obligations.

## Calls and compiler contract

Only the three selected acquisition sites use explicit caller-clobber shells.
They capture original SP/IP/BP and pass the immutable provider separately to a
no-frame assembly tail bridge. Every other acquisition is a conventional-ABI
local route, including pipe read/write/resize and file-table maintenance. The
pipe fcntl shell admits only `F_GETPIPE_SZ`; the complete native switch remains.
Unsupported delegation context falls back to local KD on the same word.

Selected unlock bridges are exact outer-root aliases, not global KD aliases for
arbitrary objects. Minimal completion still compares the physical root, saved
CALL continuation and wrapper metadata. A FULL exit retains the original bridge
CALL target. Nested calls on another object use the original-task native suffix;
they must not reinterpret a Native object as KD through translation learning.
Ordinary native API calls cannot acquire this clobber contract through ftrace.

The coverage includes `fs/file.c`, `fs/locks.c`, `fs/proc/fd.c`,
`io_uring/openclose.c`, `include/linux/fdtable.h`, `fs/pipe.c`,
`include/linux/pipe_fs_i.h` and direct watch-queue assertions. Exported pipe lock
helpers route splice/tee/vmsplice users. RCU and lockless pipe poll remain native.
Exact source searches, typed-field compilation and emitted-code inspection are
required; a regex census alone is not evidence of complete participation.

## Validation order

First validate the binding, failure unwinding, same-word local/delegated routes,
clobber forwarding and endpoint classification with focused source-derived
fixtures and module mechanism checks. Run the requested single-round nano
comparison separately, with diagnostics off for scored rows.

Then build and boot the narrow overlay with Native creation policy first. Verify
the selected source spans retain their bodies and all participants use the bound
word. Exercise actual fcntl/ioctl paths with concurrent close/dup/proc observers,
pipe read/write/resize/wakeups and normal destruction. Only after these gates may
same-kernel Native/KD syscall comparisons be reported. A TCLock comparison needs
an equivalent whole-object binding; old copied-body measurements are not pooled.

Broader object groups and MM integration remain later stages. Current source
work is unbuilt and unvalidated until its separate VM receipts exist.
