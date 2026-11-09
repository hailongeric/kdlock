# Bounded generation-three mmap1 follow-up

Runner `816e9ce3430cebdd2c186f6a8d2baca16d75e66f` changes only the permitted
observation count sequence and documentation. Provider and translator bytes
match validated `eabe454b4ee51ea6962a73525372b4b09679c737`; the matching
provider, build and focused checks were reused. No return/callback protocol,
JIT backend, GS handling, source/CFG limit or ownership rule changed. Master
was not modified or merged.

Before running, both retained generation-three images from the previous
session were checked against their recorded SHA256. They contain the learned
edge `0xffffffffc0e32bec` → `0xffffffff814f4a38` and the actual target body.
The source return reads its word, advances R13 by eight and puts the destination
in R14 before IJ dispatch. A hit restores dispatch flags and jumps directly to
the target with no second pop. Exit 15 exports the same completed transfer for
the first-unexecuted destination. The key is the source RET's next-PC, not an
unexecuted RET address. See `disassem/special_inst.py`,
`disassem/indirect_jump.py`, `include/wrapper.S` and
`kernel_module/execution/wrapper_entry.inc`. This pre-run review establishes
static coverage only. Old module addresses and histories were not imported.

One fresh processes session ran `[1,2,4,8]`, once per point. The first three
are bounded learning applications; the last is the representative observation.
Unchanged will-it-scale is `75f66e45697e6f5f49c33dd950c4e6b289198f8f`,
`-t N -s 2 -m`, six warmup plus two measured samples. Runtime is
`7.0.0-38-kdscope5`, Build ID `5f2fce72a33480f6e79a79b374b21a0db377ecd1`,
`kd_mmap=on`, lazy preemption, 64 vCPUs and 24 GiB. Requesters use CPUs
`0..N-1` on node 0; executor pool 0–61 spans both nodes and collector is 63.
Host policy remains fixed 2 GHz. Compilation and selected counters remain
active. Rates are unscored learning observations; counter totals include
warmup. Different learning schedules are not pooled or treated as controlled
performance gains. Full suites, a new provider build and Nano were unnecessary
for the runner-only change and were not repeated.

| Processes | Pairs/s | JIT entries mmap/munmap | Fully delegated returns mmap/munmap |
| ---: | ---: | ---: | ---: |
| 1 | 220830.5 | 0/0 | 0/0 |
| 2 | 322072.0 | 2/2 | 0/0 |
| 4 | 372330.5 | 4/4 | 0/0 |
| 8 | 369782.5 | 8/8 | 0/0 |

All four applications passed and drained. Both entries were generation 3
before the eight-process application and generation 4 afterward. The final
point recorded eight completed handbacks per entry and zero ordinary delegated
returns. Local/no-image acquisitions were 2957049 for mmap and 2957045 for
munmap. Thus the learned return image executed, but a complete delegated MM
region or read tail remains unproved. The generation-three source hashes in
this fresh session match the earlier reviewed images; the histories were
relearned, not copied.

The final histories retain the two earlier IJ edges and add these CALL targets:

| Root | Reached callee boundary | Matched core ELF symbol |
| --- | --- | --- |
| mmap | `0xffffffff8181c0e0` | `unmapped_area_topdown` |
| munmap | `0xffffffff826b2f60` | `mas_mab_cp` |

The selected generation-three images contain only CALL-miss stubs at these
callee entries (exit 1), not their bodies. Generated caller code pushes the
real return word before reaching the stub. Existing runtime validation retains
that word and resumes the original task at the first-unexecuted callee;
the CALL push is not replayed. The mmap image shows the caller at
`0xffffffff817f6fd6` with return word `0xffffffff817f6fdb`. The munmap image
contains several CALL sites to its recorded target; the callee history does
not identify which caller was executed. Unique target histories do not
attribute each of the eight handbacks individually. This is an observed code
coverage boundary, not evidence that either helper cannot be delegated.
Generation 4 was published after the application and remains unrun.

The eight-process rate is 78.16% below the preserved Native control
1692926 pairs/s and 4.96% below the prior learning observation 389100 pairs/s.
Native was not rerun; its runner is `14cc632d8e84010448ee84a6411f8bf8f5220a01`
on the same kernel build with `kd_mmap=off`. The prior runner was
`f0bf9f505442ba97067055a88a1d8c34fe2782f3` with `[1,2,8]` and the same
provider. These are descriptive differences across learning schedules, not
a measured implementation gain or a causal attribution of the decrease.

Exact retirement passed with `state=2, modules=0, frames=0, writers=0` and
final idle. Normal `7.0.0-38-kdlock1` was restored and verified at boot
`2e6b45cf-2364-4fac-992b-5b417e876398`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`; the one-shot boot entry is empty.
The overall performance/delegation verdict remains unaccepted.

The exact generations, local/handback/completion counts, new recorded edges,
compiler outcomes and retirement receipts are in `analysis.json`. A JIT entry
or normal image is not a completed region. Actual CLI/STI hits and physical
batch lengths remain unmeasured. Existing flags, SIMD and IRQ-context limits
remain; this observation does not establish general architectural equivalence.

All original run files remain on the VM. Local retained records are under
`../../raw/bench/mmap1-generation3-816e9ce3/`, bound by size and SHA256 in
`retained-files.json`. Original campaign outcomes and separate finalizers retain
the distinction between workload/drain success and performance acceptance.
