# Generic rwsem source checkpoint and unrun validation

Implementation core `532b68a65bdf96504e2cede6c23a5bc1476d94e9` adds generic
source-rebuilt Linux rwsem binding, one shared KD gate for selected APIs,
physical-local records without another S_W, persistent canceled-writer queue
users, exact reader routing and real native downgrade. Source snapshot
`02ffa1ec4f4813e4051ebe109fcd0777ba6304fa` adds actual generic owner-query
exports and exact versioned source API boundaries. The integration contract is
[RWSEM.md](../../../kernel/integration/RWSEM.md).

Independent source review closed for the backend, Linux binding/installer,
canonical-state and task-lifetime integration, and the two fixtures. Findings
corrected before freeze were owner-control publication ordering, an accidental
archive-loop insertion, unavailable per-gate JIT event attribution, and cleanup
of an unexpected successful try on the original calling task. None of these
reviews is a build, test, API acceptance or performance result.

At fixture source checkpoint `fdfb5127`, the [native compatibility fixture](../../kernel/rwsem_api/README.md) had eleven
bounded scenes. Source commit `0d0b52c0` adds the twelfth scene for cancellation
after taking an MCS turn while draining existing readers; it is also unrun. The [real syscall fixture](../../kernel/mmap_api/README.md)
invokes mmap/munmap through actual userspace syscalls and uses its control ioctl
only for binding/query/lifetime glue. Initial real-MM binding explicitly uses
`source_calls=false`; no dummy source provider or source packet is created.
Syscall byte effects, native physical grants, native downgrade and exact drain
are separate observations. It makes no MM body delegation or JIT-consumed
retained-write downgrade claim. Four VM-only source-boundary regressions are
written in `tests/test_source_boundaries.py`; they are unrun.

The [reviewed preparation controller](plan/prepare-focus.py) and
[plan](plan/prepare-focus-plan.md) are **unexecuted**. They construct independent
fresh kernel6 source/output, preserve normal and kernel5 inputs, apply the exact
seven-file installer, and compile 33 KD plus eight affected native objects.
The committed plan and package manifest fix source inputs; they do not by
themselves supply a fresh recovery receipt or authorize reuse after a mismatch. Build/install and reboot authorization already exists. At this source freeze
no source was staged to the VM and no kernel6 candidate, compile, full link,
module, install, reboot or behavioral check had been dispatched. Subsequent
preparation/compilation is a separate stage with its own receipts.

Fresh read-only guest inspection observed normal `7.0.0-38-kdlock1`, boot
`51b49fa4-4d99-457e-a73e-632b690eb95e`, taint0, no active build/fixture or blocked
D-state thread, builds2 available76,095,098,880B. QEMU-host `df` observed
242,879,787,008B available. These are source-turn observations from tool output,
not a saved complete preflight or a future activity/space guarantee. Historic
RCU/journal warnings from the earlier snapshot deletion remain in guest dmesg;
no new full-filesystem-health conclusion was made.

The subsequent recovery inspection as `eric` failed with
`PermissionError: [Errno 13] Permission denied: '/proc/257489/exe'`, before
reaching the QEMU monitor or inspecting snapshots. The empty output then caused
a secondary JSON decode error in the local summary step. The
[denial record](host-read-denial.json) is an authored factual record of those
tool errors, not original stderr. The read-only
[exact host script](plan/host-read.py) is retained. The standing stop-after-denial
instruction was followed: no sudo retry, alternative access route or dependent
VM build occurred. The user then explicitly approved the same script through
`sudo -n python3 -`; the exact approved retry returned0, with empty stderr.
[Its retained output](host-read-approved.json), UTC2026-11-11T11:37:43.065101Z,
records the running VM, no block jobs, three attached images, host available
242,879,578,112B and `kdlock-builddisk-clean-20261031` in the all-disks snapshot
section. That clears the permission hold and supplies a fresh recovery proof
for the separately reviewed preparation dispatch. It is no compile or runtime
result. Passing kernel5 receipts cannot be reused for this source revision.
