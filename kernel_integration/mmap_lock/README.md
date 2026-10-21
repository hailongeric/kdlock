# Actual mmap-lock kernel integration

This is an explicitly approved guest-kernel experiment on the existing
`10.176.26.71:2222` VM. The source baseline is `443baa6` and the recovery kernel
is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Historical captures under
`kernel_baseline/experiments/` remain inputs, not editable implementation trees.

The first integration uses KD physical exclusion for the actual
`mm_struct::mmap_lock`, with concurrent local readers and origin-local writers.
It does not admit complete MM critical sections into the JIT. Killable waits,
downgrade, nested old/new mm locking, fault retry, remote-mm access and deferred
read release must retain their existing semantics. No private workload lock
substitutes for the real mmap lock. Native and KD measurements, instrumentation
profiles and kernel revisions remain separate.

The main agent is the only writer. Source and static review run on `380G10`;
builds and tests run serially in the existing VM. No timing is authorized by a
partial correctness result. Keep untouched mmap/munmap and page-fault workloads
separate, and exclude TCLock from unsupported complete MM bodies.

Before installation, preserve and hash the existing boot image, initramfs,
configuration, symbol map and boot configuration. Keep its modules and source
tree intact. Install a distinct experimental release, retain the recovery entry
as the default, and use a one-shot experimental boot. Verify the real snapshot
`before-mutex-kdonly-20261017T140354Z` before live work. A timeout is not drain.

Stage evidence and remaining gaps are recorded in the
[integration report](../../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md).
The earlier [Native audit](../../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/INTEGRATION.md)
describes the starting limitations; its historical blocked status is retained.
