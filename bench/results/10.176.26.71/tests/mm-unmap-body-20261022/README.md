# Whole-VMA munmap body stage

Status: prepared; compilation and live validation are pending. The reviewed
scope and resource/ownership rationale are in [the munmap guide](../../../../../kernel_integration/mmap_lock/UNMAP.md).
The completed advice and first-write stages through `9ebcfba` remain separate.
Performance, p95 and the seven mutex regressions remain deferred.

Initial checks found the original MM guest idle on recovery boot
`11968a2a-23e4-4474-95b8-a636a9858fbd`, release `6.1.159-kdclobber2`, with the
expected 73 modules, no MM probe workers, approximately 15.3 GiB free on root,
the original host placement and the real
`before-mutex-kdonly-20261017T140354Z` snapshot. The only pre-existing checkout
changes were the unrelated disk-cleanup report and nano campaign files; they
remain untouched. No other run was interrupted or messaged.

Read-only review copied the actual `kdmm3` kernel sources to the source host.
The first collection returned status 2 because this kernel has no
`arch/x86/include/asm/mman.h`; its 20 other source files were retained and
inventoried. The actual x86 `arch_unmap()` definition was found in
`asm/mmu_context.h`, and notifier registration was checked in
`mm/mmu_notifier.c`. This collection issue is not a test failure or a pass.

The planned candidate is `6.1.159-kdmm4`, built separately at
`/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1/linux` with a new
captured baseline. Recovery and `kdmm1/2/3` installations remain protected.
The stage uses `bench/results/10.176.26.71/raw/tests/mm-unmap-body-20261022/`
on the source host and `/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022/`
in the guest. No general mmap/munmap or populated-page teardown delegation is
claimed.

Build source `670796f` passed the two basic programs, five advice and five fault
receipt checks, and completed the kernel image. The final single-module target
failed with two competing `serio_raw.o` compilations: modpost found missing
`MODULE_LICENSE()` and an unresolved builtin reschedule symbol. Nothing was
installed or booted. The first build log and object/command files are retained;
the planned retry uses the module directory with one job, preserving the image
and checking the same 73-module closure. Admission and runtime checks are unchanged.
