# mmap1 learning with the 64-application allowance

The candidate completed 50 passed, drained learning applications, then stopped
because the mmap image became Native-only at generation 48. The compiler's
next text-cache plan exceeded 256 KiB. No worker-attributed proof or quiet KD
point was produced; process mode and the remaining worker counts are unrun.
All learning rates remain unscored. The preserved matched Native results are
unchanged; there is no measured KD throughput gain or Nano acceptance.

## Candidate and checks

- Design/evidence commit: `bdd37ba0`.
- Runner: `cfdb52a83e98eed140062bc83c51207579242392`, branch
  `codex/mmap-reached-jit`; `master` remains unchanged.
- Only the benchmark allowance, preparation progress and boundary fixture
  changed. The default allowance remains three; this run selected 64 with the
  same 1800-second global learning deadline, 128-image pool, CFG bounds,
  image-readiness checks, worker proof and one-round scoring.
- Fresh frozen root: `/root/kdlock-inputs/frontier-cfdb52a8`.
- Source-state SHA-256:
  `26a7338a855efcf58c621086f1bb1063d7b0d378547c3633818645dc80f37e2c`.
- Manifest SHA-256:
  `6a31417b12c26128014a8afd0b9abc0f37b21ae09bb00714f9a6095582a15183`.
- Provider SHA-256:
  `427da305c37cd96625b77fee4d46ff6e0df956df251a8f647cba502cff9bccd7`.
- Daemon SHA-256:
  `253243ff1d49cd5422db63d67f37666e22d1247c39b12d5c9e29bf004a375eb9`.
- Observer SHA-256:
  `52b292ba1bf14fc49fb70f35c970ab5fb3ec1c2da4a39d4e77fdf5f8e6a72543`.

The two directly affected VM drivers passed: 11 demand/limit cases and nine
controller cases. Provider, daemon and observer builds passed. Unchanged
runtime/component checks were reused only after matching their source hashes.
The previously reproduced text-region failures remain recorded in
[the focused frontier report](../../tests/source-frontier-99958c7d/README.md).

Kernel `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`0066b863-dcdb-48b2-b53f-b9347a943f72`, used `kd_mmap=on`. The syscall tuple
selector was enabled, with the same two roots, topology, policy, binaries and
eight-count grid described in
[the preceding campaign](../mmap1-frontier-99958c7d/README.md). Histories started
empty. Preparation progress was read only from the existing source-host log;
no guest inspection process was added while the factory was active.

## Observed stop

| Root | Final status | Successful generation | Distinct CALL additions | Distinct IJ edges |
| --- | --- | ---: | ---: | ---: |
| `0xffffffff817b6f68` | Native-only | 48 | 44 | 4 |
| `0xffffffff8181c73b` | NORMAL | 25 | 22 | 2 |

There were 74 compiler jobs: 73 succeeded, and the mmap generation-49 attempt
returned Native-only. Its final appended target was `0xffffffff826c5620`
(`mas_store_prealloc`). The append counts include that unsuccessful addition;
they are not all successful publications. The pool used 73 descriptors, with
55 free and zero private. All 50 application lifetimes passed and drained.
Compiler wall time totaled 794.203 seconds; application lifetime wall time
totaled 401.882 seconds. These are preparation totals, not scored runtime.

The final decode had 241,664 cached bytes, 28,327 decoded instruction bytes,
7,181 instructions and eight incomplete source blocks. Extending the eight
missing targets with 8 KiB page-aligned windows planned 270,336 bytes, exceeding
the 262,144-byte cache bound by 8,192. The compiler refused before reading the
oversized plan. This is a cached-window limit, not image-capacity exhaustion or
the 64-application allowance. `ready_writer_entries()` then refused scoring
because one selected image was Native-only.

The additional mmap helpers include `is_mergeable_anon_vma`, `vma_expand`,
`commit_merge`, `vma_prepare`, `anon_vma_interval_tree_remove`, `rb_next`,
`vma_adjust_trans_huge` and `mas_store_prealloc`. These are plausible protected
VMA merge work. All final table lines are distinct; there is no repeated
completed addition in those tables. Per-edge task/lock-phase provenance is
absent, so exhaustive region attribution remains unproved. The diagnostic
instruction's live handback and returned MM read-tail/writer proof remain
unvalidated in this campaign.

The existing compact policy couples smaller lookahead to a 1 MiB aggregate
budget and the retired eager profile. Enabling that policy directly would
change the current bounds. The authorized follow-on retries only oversized new
page-window plans with shorter optional lookahead, retaining every old byte,
root and full instruction prefix under the same 256 KiB and CFG limits. If
mandatory data still cannot fit, it retains the last complete immutable image
and uses the existing retained continuation for actually reached uncompiled
targets, rather than treating cache saturation as semantic invalidity.

## Retirement and recovery

Exact finalization passed after bounded ordinary CPU progress reduced the last
binding from one to zero. Retirement returned `state=2, modules=0, frames=0,
writers=0`; ordinary unload and idle passed. The original failed result,
SHA-256 `c3e34f05bb06b784bd5579f8dd5f99e101a763114797c622aaf80a0cab029daa`,
is unchanged.

The normal `7.0.0-38-kdlock1` kernel, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored on boot
`a1c09e81-ae60-42f7-99c0-484f743f1bea`. Idle/no workload, daemon or provider and
the empty one-shot boot entry were verified. No merge was performed.

The retired VM records remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/frontier-cfdb52a8/kd/`.
The source-host collection retains the exact result/finalization, compiler and
phase logs, all unscored application records and final CALL/IJ tables.
