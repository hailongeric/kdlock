# Native continuation validation

The user-directed cleanup removed retired benchmark records and parts of mixed
source archives. Archival provenance is **REDACTED / INCOMPLETE**. Original
complete-archive hashes and full-source replay claims below describe the earlier
collection, not the current retained subset; retained measurements are unchanged.

Continuation implementation `9a0fdd4`, with fixture-only corrections through
`a4eb4eb`, passed basic and directly affected checks in the recovery VM.
All nine live continuation/ownership probes passed at their recorded source
revisions. This is separate from the completed
[`d21a1e3` public-mutex performance matrix](../../bench/mutex-public-20261020/README.md).
The subsequent [controlled replay](../../bench/mutex-public-regressions-20261020/README.md)
completed 120 valid, drained sessions using those original performance inputs.
Performance acceptance remains open, including seven unresolved causal
resolutions, two class gaps, p95 latency and dynamic host worker variability.
No whole-kernel replacement, mmap/fault integration, RT/ww_mutex or lockdep
acceptance follows from this work.

The source host is the sole writer. Builds and tests use frozen, committed
source copies only in `root@10.176.26.71:2222`, under
`/root/kdlock-evidence/10.176.26.71/tests/native-continuation-20261020`.
The guest kernel has not been modified or rebooted.

## Attempts and corrections

| Attempt | Source | Outcome |
| --- | --- | --- |
| checks-1 | `9a0fdd4` | Dependencies, W=1 provider and Werror daemon passed. Unit aggregate: 28 passed, three drivers failed. Remaining benchmark checks did not run. |
| checks-2 | `390d04c` | Dependencies, provider, daemon, both basic programs and all 29 selected unit drivers passed. First benchmark driver failed compiling a stale observation fixture. |
| checks-3 | `d7d65c1` | Spin/cacheline and direct-comparison drivers passed. Rwlock/rwsem benchmark driver failed on missing fixture metadata. |
| checks-4 | `a4eb4eb` | All 26 rwlock/rwsem benchmark tests passed; final idle and source hashes verified. |
| checks-5 | `b345db3` | Dependencies, provider/daemon, both basic programs, eight selected unit drivers and three benchmark drivers passed. Includes 12 focused replay tests. The emission-only prefetch test missed an assembler failure found by the next live run. |

All failed attempts and original results remain under their numbered
directories. Each failed process exited; a separate `post-failure-health.json`
then established VM idle and unchanged current/frozen source hashes. The
original scripts leave `final_idle` and `source_unchanged` false on an early
failure because those final checks did not run; the later receipt supplies
the independent verification without changing that original result.

Corrections are confined to tests:

- `390d04c`: provide both clobber symbols in the expanded-text fixture; map
  paired ABI2 fixture calls to KD local control symbols; scope the unused-C-
  parameter warning exception to the unchanged assembly helper that reads its
  argument through `%rdi`. Exact control, restoration and refusal assertions
  remain. All 24 paired-JIT cases and both 320-case spin restore builds then
  executed successfully in checks-2.
- `d7d65c1`: model the observation sysfs parameter's actual argument and
  read-only completion-probe permission. Check disabled and wrong-lock behavior,
  distinct entry/completion counters and accumulation across CPU slots.
- `a4eb4eb`: include the ordinary image's `requirements=0` in the rwsem
  publication fixture. Production publication checks are unchanged.

The third and fourth attempts select only remaining affected benchmark
drivers. Passed provider, daemon and unit inputs are byte-identical to checks-2;
their validation is retained under that exact revision, not relabeled as a
new run. Skips, missing dependencies and compile failures are not passes.
The retained benchmark-driver outcomes remain scoped to their original inputs.
The provider build exited successfully with existing locale-fallback warnings
and the `_Q_LOCKED_COMBINER_VAL` redefinition warning retained verbatim in its
log; this is not a warning-free build claim.

## Live attempts

`live-1` used `a4eb4eb`. Mutex OUTER, public DIRECT and spin passed all four
phases and drained. Their cold-delegated matching entry/completion counts were
1,590,509, 1,589,501 and 1,595,512 respectively. Each hot phase recorded one
checked native exit and no completed JIT body; the post-ban phases recorded
zero new entries, completions or exits. Every phase completed 1,600,000 writes
with exact prefix/suffix effects. Exact task, arithmetic flags and spinning
CPU/control-state checks remained active.

Rwlock stopped during preparation: strict admission refused a widened result
pointer at the cold-path join (`CMP BYTE PTR [RSI], 0`). No positive rwlock
execution was established. Cleanup retired all source frames, modules and
writers; independent idle and hash verification followed. The two archives
retain all four tasks, including that failure:

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| probes.tar.gz | 16588171 | `ad1c2e77e30191e6c6f94a3a1dbaa14e321516747f1b92b09f92d80de087f22d` |
| metadata.tar.gz | 43529 | `2c9411ef48c884cc646787104c29a6634d1de66b9f23a012eb8541169fb1e9ad` |

Raw copies are under
`bench/results/10.176.26.71/raw/tests/native-continuation-20261020/live-1/`.
The VM archiver verified unchanged inventory and final idle. The separate
health check verified 776 source/binary hashes and found no matched faults in
the four kernel logs.

`eea0260` changes the shared probe payload only: the hot path increments suffix
and then checks that competing-reader completions are unchanged; the cold path
increments suffix separately. This preserves the observation window through the
suffix while removing a result-pointer dereference from the cold merge. Pending
reader, active-reader/writer, rwsem reservation and exact unlock checks remain.
Provider and admission code are unchanged. `live-2` also stopped at rwlock
preparation: the first refusal moved to the pre-marker store of
`reader_pending` after the polling loop. It drained and retired completely,
with 194 source/binary hashes verified and no matched kernel faults. Its
archives remain separate under the analogous raw `live-2/` directory:
`probes.tar.gz` is 4,153,930 bytes, SHA-256
`cfdf13c04d85d9018ff437ae81eaeb470f6570045b014cc032fc0cb77b9ca50f`;
`metadata.tar.gz` is 42,773 bytes, SHA-256
`b73780671a1f5ac8272c93cac7f43e0a105f6fc2764639ccf39c6646294f28cf`.

`fafad5c` keeps the pending-reader poll and completion snapshot before the
marker, carries their scalar values through the unchanged native continuation,
and stores them in the result afterward. `live-3` (collection commit `52ceb5a`)
still failed strict admission, now at the result-pointer store immediately
after RDTSC. It ran no business phases and drained completely. Its preserved
archives and exact refusal are under [live-3](live-3/archives.json).

`cf1e858` moves observations to a private local record on the retained caller
frame, copying the record to the caller only after the exact unlock returns.
The actual rwlock disassembly uses BP-relative fields through the marker,
with the caller-pointer copy after both unlock routes. `live-4` passed strict
ABI3/requirement-33 admission but failed the unchanged positive execution check:
both cold phases had zero JIT entries and completions. All 2,800,000 writes and
40,000,000 reads completed without business errors. This is **NO_JIT**, not a
correctness pass. The remaining planned tasks did not run.

Independent health verification found complete retirement, idle, 194 unchanged
source/binary hashes and no matched kernel faults. The [live-4 archives](live-4/archives.json)
retain the generated image, disassembly, worker receipts and failure. The next
diagnostic attempt enables only the existing final heat statistics; thresholds,
instruction admission, positive returned-body checks and reader checks remain
unchanged. Baseline attempts retain their original instrumentation identities.

`live-5` (`6f97b3c`, final heat diagnostics enabled) repeated the drained
`NO_JIT` result. The affected caller-lifetime runner's three tests passed first.
No delegated batch or native exit was observed. Final CPU heat gates were cold;
writer residual windows contained roughly three to four entries per MCS
publication. These are unfinished-window observations, not lifetime counts or
proof of every historical gate decision. They support insufficient qualified
contention, while no generated-entry refusal appeared in the kernel log.

The next payload revision adds 32 bounded reader-exclusion observations with
`cpu_relax()` to each shared-family writer body, on both cold and hot branches.
This extends the checked exclusion window and allows genuine queue contention
to develop. It changes no provider/admission threshold, skips no check, and
retains the original fixed worker counts, affinities and operation counts.
It is a distinct correctness-probe revision, not a performance measurement.

The serialized plan covers checked native exits for mutex OUTER, public DIRECT,
spin, rwlock and rwsem; address-
guard and string-service regressions; ordinary mutex and rwsem ownership
probes. Positive JIT probes must demonstrate returned cold bodies, the exact
hot native continuation, sticky refusal and final drain. Publication alone
does not satisfy them. Reader contention must remain visible in shared-lock
families. Caller timeouts do not prove drain and must retain unsafe state.

The seven original mutex regressions, incomplete comparisons and unmeasured
p95 gap remain open; correctness progress is not performance acceptance.

## Completed affected live probes

`live-6`, source `96f81ac`, completed all nine serialized tasks successfully:
all five instruction-exit families, address guards, string services, ordinary
mutex ownership/API checks, and rwsem sleeping/admission/cancellation checks.
The two shared-family bodies use the additional bounded exclusion window;
the other three marker bodies retain the frame-local correction from `cf1e858`.
No production provider or instruction-admission rule changed during diagnosis.

Rwlock's cold-delegated phase returned 1,549 JIT bodies; rwsem returned
1,030,743. Each then recorded exactly one hot native exit, no hot returned body,
and zero entries/completions/exits after the sticky ban. Cold warmup is allowed
to establish contention without returned bodies; rwlock's warmup returned zero.
Every shared-family phase completed 1,400,000 writes and 20,000,000 reads with
the full task/flags/exclusion checks. All ownership probes completed and retired.
Independent verification found the VM idle, all source/module/writer/frame
retirement records zero, all 1,694 frozen source/binary hashes unchanged, and no
matched faults in the nine kernel logs. Complete archives are retained under
raw `native-continuation-20261020/live-6/` and the same VM evidence run identifier.

The basic/affected unit results above remain bound to their original exact
sources. Performance acceptance is still open. The separately retained offline-review
script and per-attempt receipts check archive consistency, not live correctness
or generic kernel replacement support.

The [live-6 archive manifest](live-6/archives.json) has SHA-256
`c0e2809ffa0c7fbd007b26766032c3351a5f41e6c7b454ef98d62f3acb59f4ba`.
The read-only helper reviewed 4,655 archive members, all source/binary bindings,
448 worker receipts and nine exact retirement records. Its separate corrected
compiled-image review checked all five complete ELF `.text` listings and the
1,472-byte loaded string-service image. The initial optional relocation audit
used an incorrect offset convention; the corrected review uses CALL opcode
offset + 1 for the displacement write and + 5 for the continuation. This was
an offline review error, not a runtime failure. All helpers report no files
touched; the main agent remains the only writer.
