# Final munmap g7: Maple lock scope and ordinary MM releases

This is static analysis of the SHA-verified final image retained from the d421e7d5 normal campaign (evidence53889930), not the prior40edde g6 diagnostic. No live work or test ran.

## Source identity

The following local source files under `/tmp/kdlock-semantic-source-20261030/source/` hash-join the final run kernel-baseline manifest:

- `lib/maple_tree.c`:959a43980d7ef06c1c7970e5c0bb0a735dbe9c4d5a5f450376d8f76e97f21e9f
- `mm/vma.c`:8dea0340f92be7b964b2d424459155f04447fb0b69075d02f4b64b58291f7f05
- `mm/mmap.c`:26097665c7cfaf7b28c0be7a8b1362b80b51d497033af24278b8a0444d2f1c5b
- `include/linux/mm_types.h`:6a96679d9cc00ab4c967a9f6693727896903d1a0f0bd0273121385262b95c9aa
- `kernel/fork.c`:0bccb1f0e882cfcd68d048271ece6bcce00e0f3e115c3d2770072efabe5bc5a0

`/tmp/kdlock-unmap-review/lib/maple_tree.c` differs and was not used as matching source. The older `/tmp/kdlock-mm-file-api-capture-20261103/build/System.map` also differs from the final kernel's recorded System.map and was not used for final symbol attribution. The exact-ELF symbol map is retained at `/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/mmap1-normal-d421e7d5-v1/munmap-g7-static/kernel-symbols.txt`.

## Specific excluded Maple internal-lock branch

Matching source `lib/maple_tree.c:5843-5854` implements `mas_nomem()`: only after `mas->node == MA_ERROR(-ENOMEM)`, it tests `gfpflags_allow_blocking(gfp) && !mt_external_lock(mas->tree)` before internally unlocking and reallocating/relocking. The final g7 image contains this exact condition at `asm/jit.S:136172-136249`: node encoded0xffffffffffffffd2, GFP bit0x400, then NOT of tree flags followed by AND DH,0x3 and JNZ to826c6b63. This last branch is equivalent to `(tree->ma_flags & 0x300) != 0x300`.

The internal-unlock source CALL is0xffffffff826c6b6a (`mas_nomem+0x6a`), target0xffffffff82702de0 (`_raw_spin_unlock`), with post-CALL continuation0xffffffff826c6b6f. Generated block lines136313-136324 explicitly push this real continuation and jump to the target; the target is an emitted terminal CALL stub at149269-149275.

For the normal MM tree, `include/linux/mm_types.h:1421-1422` includes `MT_FLAGS_LOCK_EXTERN` in `MM_MT_FLAGS`; `kernel/fork.c:1087-1088` initializes `mm->mm_mt` with those flags and its external mmap lock. `mm/vma.c:1570` initializes the detach tree with the main tree's lock mask. Final generated `do_vmi_align_munmap` at jit.S77984-77989 /78063-78067 explicitly masks the inherited flags with0x300 and compares against0x300, corroborating the compiled flag bits. Thus the internal-unlock branch is excluded for these normal MM/detach trees under their source-defined invariant. This is an object/state-specific exclusion, not a dynamic observation of the flags or a claim that the whole mas_nomem function is unreachable: its allocation path without internal unlocking can still run.

Two other generated calls to the same `_raw_spin_unlock` target come from0xffffffff81816c33 and0xffffffff81816c67 (`vmalloc_dump_obj+0x93/+0xc7` in the exact kernel), with continuations81816c38 and81816c6c. They are not excluded by the Maple flag argument; they belong to a separate diagnostic path.

## Ordinary munmap success/error release shape

- Matching `mm/mmap.c:1075-1078` sends the userspace syscall through `__vm_munmap(addr,len,true)`.
- Matching `mm/vma.c:3266-3271` acquires writer state, calls do_vmi_munmap, then performs the outer write unlock only on an error or unlock=false. For a successful userspace syscall the latter condition is false.
- Matching `mm/vma.c:1319-1321` downgrades when unlock=true. The final image CALL to `kd_mmap_write_downgrade`814f4fa0 is at source81818dd4, with post-CALL continuation81818dd9; see jit.S77934-77951. Target stub148788-148794.
- Matching `mm/vma.c:1346-1347` read-unlocks after the teardown. Final image CALL to `kd_mmap_read_unlock`814f5280 is at source81818daa, continuation81818daf; see jit.S77896-77909. Target stub148795-148801.
- The final image has no emitted next block at either81818dd9 or81818daf. How these terminal CALL controls hand back/resume is governed by the exact runtime protocol; their presence alone does not prove execution or a taken boundary.

Earlier exits can precede these releases. The all-handback / zero-return counters do not select the downgrade, read unlock, Maple branch, STD frontier or any other exact point.
