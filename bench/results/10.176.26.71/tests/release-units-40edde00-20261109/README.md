# Release-unit correction: focused checks pass

Source commit `40edde00525b71207246bbde4935767cbcb21fb7` ends retained
ABI2 mutex/service source units at every recognized release, including inner or
unrelated releases, typed Native releases and downgrade. Runtime decides whether
the real operation completes the scope or requires exact native continuation.
The compiler does not pair an unlock with an acquisition.

## Concrete change

- Known release CALL/JMP boundaries stop decoder fall-through and source emission.
  Bounded release-free return summaries prevent an ordinary or learned indirect
  callee's release-only path from making its caller's suffix reachable. A genuine
  returning alternative retains that suffix. Source history does not independently
  authorize a disconnected post-release region.
- Runtime completes the release CALL once. Final release retains existing
  completion behavior. With remaining owners, the saved post-release IP/SP and
  canonical packet enter the existing Native handoff. No CALL push or RET pop is
  replayed, and source/image references and exact release/ACK duties remain.
- Downgrade retains its real read credit, which transfers to Native custody and
  remains through the matching read unlock. It neither reacquires nor silently
  discards the protected read tail. Executor retirement may precede completion of
  that native read tail; this is not returned-JIT evidence.
- Newly nonfinal units require the existing service-queue image requirement.
  The existing flat terminal-clobber fast case keeps its requirements and runtime
  identity checks. Legacy spin/rwlock boundary/refusal behavior is unchanged.

This first correction uses **native-tail fallback**. It does not implement
separate nested JIT images, JIT-to-JIT continuation units or later translated
resumption after that native tail. Full-root munmap returned counters can remain
zero by design. No new matching-scope metadata, upload protocol, second JIT,
ownership inference or actor rewrite was added.

## Focused VM evidence

All six directly affected drivers passed with no skips:

| Driver | Relevant evidence |
| --- | --- |
| `codegen/test_release_units.py` | 17 methods: outer/inner/unrelated release, CALL/JMP, nested/indirect callees, return alternatives, downgrade/read boundary, bounded work and flat-fast compatibility |
| `execution/test_release_units.py` | Actual production completion/release/RPC/loop/handoff functions; five KD boundaries, three Native releases, ordinary CALL, refusal ordering and four mutations |
| `execution/test_jit_entry_scope.py` | Existing production entry, CALL advancement, progressed exit and packet checks |
| `mutex/test_rwsem_read_release.py` | Real reader decrement and final object-access boundary, with negative control |
| `execution/test_native_service_join.py` | Four component modes, including already-consumed release CALL, through actual Native acceptance, typed release, final ACK and retirement |
| `mutex/test_admission.py` | 15 production queue/admission cases, downgrade/read-credit custody and four mutations |

The changed observation-prepared **128-image kdscope5 provider built successfully**
against the existing verified kernel outputs. Its SHA256 is
`594c4dbd8180a0b1e4ac1b80ded1b281445e8263d25bb1dbc29a29cbfe50865c`,
ELF Build ID `978e03eca714cffd6bb7a17bbce0a726eab1f5cd`.
The build retains 11 warning lines: one compiler identity notice and ten objtool
findings (three naked returns, one modified stack, one undefined stack state and
five missing frame-pointer setups). These are not resolved mitigation coverage.

Checks ran only in the VM, normal boot
`1eeab914-c1d7-4c69-bc7c-1db2921c3135`. All 1,099 frozen source files,
prepared provider inputs, kernel build inputs and original receipt sets remained
unchanged; final module/process/task idle checks passed. The component fixtures
supply task/scheduler/physical-operation primitives and do not establish live
kernel concurrency. No daemon or kernel rebuild, reboot, module load, workload
or performance run occurred.

[receipt.json](receipt.json) retains exact commands, statuses, log hashes,
warning lines and artifact identity. Full receipts remain at:

- Local `/tmp/kdlock-batch-checks-ads4eary/checks.tar.gz`, SHA256
  `db55e8b1ae39781dfea0f8d8c7a0f6ab10a412dfa0727edba52a64d279dbc341`.
- Guest `/mnt/kdlock-builds2/kdlock-batch-checks-u1dw9xwz`.

The preceding live experiment's [deadline failure and recovery](../mmap1-continuation-2d8eb6e3-20261109/README.md)
remain separate evidence. Its last pending CALL was `unlink_file_vma_batch_add`;
the new boundary implementation has not been loaded or measured.

## Separate actor-selection finding

Publication is eligibility for possible combiner execution, not irrevocable
delegation. The ordinary KD mutex already elects local versus proxy execution
under its wait lock; a locally selected origin can serve as combiner and then
execute its own body. Retained service roots currently end arbitration after
admission and force transfer to a claimed service worker. Their missing local
execution/combiner transition and acquire-boundary redesign belong to the separate
architecture workstream. This patch neither implements nor validates that rewrite.
