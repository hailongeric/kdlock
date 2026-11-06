# mmap1 original-image learning at 99958c7d

The campaign completed 32 passed, drained learning applications and 57
successful compiler jobs, but reached its application allowance before a stable
timing epoch. It produced no worker-attributed proof or scored KD point. Every
learning rate remains unscored; no Native/KD throughput gain is claimed.

The runtime/runner source was `99958c7d4d79bc9ddcdac290b51ed0bd40328487` on
`codex/mmap-reached-jit`. The provider and daemon identities and focused checks
are in [the frontier report](../../tests/source-frontier-99958c7d/README.md).
Kernel `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, ran with `kd_mmap=on` on boot
`d7794069-552c-4b81-bcb1-542eb031ac78`. The default-off syscall tuple selector
was explicitly enabled. Both selected roots used the original JIT and fresh
empty histories. No caller body was modified.

The requested grid was `1,2,4,8,16,32,36,60`, threads then processes, with one
scored round per point. It stopped during one-worker thread learning; all
remaining points and the process model are unrun. The preserved matched
[Native arm](../mmap1-scaling-f9fdaa2a/README.md#native-results) remains the
comparison baseline. This eight-count subset is not the full 21-count grid.

| Root | Final status | Generation | Distinct CALL additions | Distinct IJ edges |
| --- | --- | ---: | ---: | ---: |
| `0xffffffff817b6f68` | NORMAL | 32 | 29 | 2 |
| `0xffffffff8181c73b` | NORMAL | 25 | 22 | 2 |

Every completed append-table entry is distinct. The additions plus each initial
publication account exactly for the 32 and 25 generations. All 57 compiler jobs
returned success and the final pool contained 57 published images, zero private
images and 71 free descriptors. Munmap remained at generation 25 for the final
five learning applications; mmap continued to advance. Compiler wall time was
564.260 seconds; application lifetime wall time was 257.213 seconds. These sums
are not scored runtime or critical-section time. Host observations bracketed
the whole launch and retirement from `04:38:29.166379` to `04:57:24.801277` UTC;
that 1135.635-second interval includes preparation and finalization.

The last mmap additions are `vma_merge_new_range`,
`can_vma_merge_left.constprop.0` and `can_vma_merge_right`. Munmap's final
addition is `anon_vma_clone` through `__split_vma`. These are plausible protected
MM work, rather than evidence of repeated learning. Matched ELF call sites put
`do_mmap` at `0xffffffff817b6fb8` before the write release at
`0xffffffff817b6ff4`; the learned VMA helpers are in that call tree. Munmap
reaches `do_vmi_munmap` at `0xffffffff8181c789`; its learned split/clone helpers
precede the later downgrade/release. The tables also include assertion/query
provider paths and module-reference helpers. They do not include the root's
post-release `userfaultfd_unmap_complete` or `__mm_populate` helpers.

Append tables do not record a task or lock phase for each edge. Their distinct
contents and plausible source paths support continuing incremental learning;
they do not prove absence of region leakage, attribute every edge to a worker,
or establish that the kernel's diagnostic frontier executed. Munmap's NORMAL
image now carries the frontier requirement and successfully compiles beyond
the earlier generation-19 decoding refusal. Runtime diagnostic-branch handback
remains unproved. Quiet and proof gates were not weakened. `service_progress`
was empty at retirement; with counters disabled this is not evidence of no
execution.

Exact retirement reduced the last binding from one to zero through bounded
ordinary CPU progress, then returned `state=2, modules=0, frames=0, writers=0`.
Ordinary unload and idle passed. The original failed result, SHA-256
`35eeb5756c844455f39c965afecb39e9bdbdb432f3e3554d41461b43de715049`,
remains unchanged. The normal kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored on boot
`19f35722-ee98-48e6-be70-3c1d6149faf6`; no workload, daemon or provider remained,
and the one-shot boot entry was empty.

The retired VM records remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/frontier-99958c7d/kd/`.
The source-host collection retains the exact result, finalization, daemon log,
phase records, learning applications and final append tables. A follow-on may
raise only the benchmark application allowance to 64, keeping the same global
1800-second learning deadline, pool/headroom guards, CFG bounds, miss semantics,
worker proof and one-round scoring. Use fresh identities and empty histories.
