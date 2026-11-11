# Kernel6 private rwsem and mutex regression preparation

This is source-only preparation. The native twelve-case API check and real
four-thread, 64-iteration mmap/munmap syscall check run first. These private
fixtures provide separate generated-execution mechanism evidence. They do not
substitute for either real syscall completion or native API compatibility.

Use only three focused checks. Run the existing five cases in
`tests/test_kernel_gs_rip.py`, one complete private rwsem fixture, and one complete
private mutex fixture. The unchanged compiler's four source-boundary cases have
their own completed receipt. No full suite or additional spin/rwlock campaign
is included. The GS cases read actual kernel6 instruction bytes and lower them
through the original decoder/backend. They do not execute generated code.

The frozen input is committed source
`80c272e5f134d9a499c03782f71064d04fae25c3`. The existing native API controller
uses that same fixture revision. Kernel package source remains
`3512f5dd639701f3f9953cfc6add1e4bbdd85e88`, core
`532b68a65bdf96504e2cede6c23a5bc1476d94e9`, with all 77 actual package files
matched byte-for-byte. The fresh snapshot is under
`/tmp/kdlock-kernel6-private-source-80c272e5-01` with 117 files, including both
private `.inc` files, compiler/runtime dependencies and the GS test. Its tar
is 1,269,760 bytes with SHA
`24c2a256397df1481443a0cb6a0e89df9c7799da602188ce494769c89f7d1342`.
The manifest SHA is
`9b68233d5cd7cb06aa7bbc69ce2d0d891fc87af6ae2f004c173a0f39b23aa690`.
The package JSON is the unchanged actual input with SHA
`e5d86bb042ed919f72275ed095d3e8113bc755abb07b6583aa6f415e68a899cf`.

The helper `/tmp/kdlock-main-kernel6-private-fixture.py` derives from the retained
kernel5 fixture controller. Its `build` mode builds only the two original leaves
through normal `M`/`MO`, `KERNELRELEASE=7.0.0-38-kdrebuild6`, `V=1` and explicit
jobs/observer/space inputs. It records actual module hashes, name, vermagic and
runner syntax outcomes. It compares every snapshot file and all six actual
kernel-output pins before and after. The Linux7 callable-API `no_llseek` issue
does not occur in these private fixtures, which already use `default_llseek`.

The common kernel source/output pair is
`/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/{source,build}`.
Its linked Build ID is `5ed6cd8cffed6960ce901261dfab3bb019a0442d`.
The snapshot's `kernel-pins.json` binds vmlinux/config/System.map/Module.symvers
and the two release headers to the actual successful kernel6 identity. The
`gs-config.json` binds actual site `0xffffffff8150114b`, bytes
`65488b05c54ef102` and full current-task alias `0xffffffff84416018`. Use those
files and their actual SHA values as explicit helper arguments. A later actual
postboot result and GS proof remain mandatory before either live family.

The `gs` mode runs only the existing five actual-target/derived GS cases with
the designated VM translation Python. It requires return 0, exactly five cases
and no skips. Missing input, dependency or test failure stays failed. It also
records unchanged source/kernel hashes and boot identity. This is an offline
linked-byte regression inside the VM, separate from the live JIT observations.

The live order is rwsem then mutex. Both reuse four workers, eight iterations,
16 dependency spans, 131,072 source bytes, a 268,435,456-byte wire-log bound,
65,536 events and a 600-second runner deadline under a 660-second outer
observer. Supply the actual kernel6 `its_return_thunk` address and its exact
two-byte span from the new linked identity. The runner verifies exported
`c3cc` against the actual ELF before compilation. No named thunk model, flag
override or compiler/backend change is introduced.

Rwsem additionally uses a 20,000 ms holder bound, 16,000,000 runtime block
visits, 16 reader-learning passes and 1,000,000 source coordination iterations.
Those existing explicit inputs yield 102 cold image slots and 104 cycle slots.
No request-pool policy changes. Reached ordinary observations must proceed
through the existing compilation/publication/ACK path before the final fixed
image. Native reader concurrency, exclusion, real native downgrade and repeated
read credits remain checked. Fixed-image read/write nesting, shared-B return,
retained-writer downgrade terminal handback and exact deliberate miss suffixes
retain the current strict oracles. New misses during fixed-image validation fail.

Mutex retains its existing native/fork checks, three cold body modes and four
compiler cycles, then fixed-image plain and both deterministic recursive scenes.
The exact canonical state, distinct acquisitions, current endpoint, physical
owner/callback and final source/result/return/notifier closure remain required.
An empty warm claim is still mandatory for mutex. Rwsem's deliberate checkpoint
baseline can be nonempty but must remain exactly unchanged. Do not hardcode old
dynamic publication, ACK, event or settlement counts for this new source image.

The first private family requires a hash-pinned successful
`NATIVE_API_AND_MM_COMPLETE` predecessor. Its actual API/client/load/unload
commands must all have returned zero on the same boot/core/config/image and
postboot proof. Both native modules and controls must currently be absent, with
no remaining worker or workload. Its exact recorded taint may be 4096 or 12288,
the declared out-of-tree/module-signature bits. No other taint is accepted.
The raw private modules then retain the existing expected 12288 result. Mutex
requires the exact successful rwsem predecessor, same private module-build
receipt and postboot proof, and actual ordinary drain/unload. A taint value,
process return or counter alone never authorizes teardown.

Each live family uses a fresh verified recovery observation, idle window and
explicit free-space floor. Keep actual module/ELF/config/source/postboot hashes,
invocation, raw stdout/stderr/kernel logs, complete binary observations, source
exports/disassembly, each candidate's assembly/C/flat metadata and GNU object,
every wire request/reply, exact publication/ACK receipts and final fsynced
archive/SETTLE/END records. Require ordinary destroy/unload and final module,
device and worker absence. Timeout or failure preserves actors and controls
without retry, replay or forced cleanup.

Passing would establish only these bounded private mechanisms on the new kernel
identity. The unprotected C epilogue remains native. General scheduling/progress,
broader context/mitigation coverage, auxiliary-stack unwinding, and performance
remain outside these checks. Actual syscall/MM evidence stays a separate row.
