# Indirect CALL learning and cumulative batch review

Base: `d4349577c33647455fe89b9d2b7461d37f78d4a4` on
`codex/mmap-reached-jit`, inspected in the preserved isolated worktree.
Source, documentation and regressions are committed at
`76b0147cfbb58246b4a3a0f371434cd758032588`.
The user selected dynamic RET learning with focused regressions. No production
indirect-CALL continuation inference is added.

All nineteen selected Python drivers, the strict daemon/basic checks and the
provider build passed on the final frozen source. This includes 255 unittest
cases and the production-function fixture groups below. No selected check
failed, skipped or remained unrun. These are source, supplied-primitive and
userspace generated-code checks, plus compilation; no live provider or workload
evidence follows.

## Source findings and corrections

The [original UserspaceBypass collector](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/indirect_jump.py)
seeds return continuations for direct CALLs and walks static block successors.
It does not infer return continuations from learned indirect CALL targets. The
current direct-only CALL inference is inherited behavior, separate from the
already corrected learned indirect-JMP tail walk.

`disassem/special_inst.py` evaluates an indirect CALL target before pushing its
real post-CALL source PC. RET pops once before dispatch. With only forward CALL
history, an already decoded callee can run and then miss at its RET. The
retained boundary exports the actual popped target, post-pop SP and RET
next-PC; the runtime reports the corresponding IJ tuple and hands back at the
target without replaying completed effects. If admitted, that tuple can enter
a later cumulative build. This depends on report capacity, supported source,
translation, publication and a later invocation. A rejected tuple needs another
reached report. One invocation still stops discovery at its first permanent
handback.

Two independent source defects require narrow repairs:

1. The entry/frame lock-kind mismatch in `kernel_module/exe.c` used an ungated
   terminal status store. A publisher could pass its terminal check, then
   overwrite that store with NORMAL after acknowledging a batch. The branch
   now uses the existing `kd_image_disable()` gate. A terminal decision that
   wins prevents publication and acknowledgment; a publication that wins may
   acknowledge its view, and the later disable remains terminal.
2. A session receipt alone did not prove that the local history contained
   another writer's acknowledged inputs. Writer A could freeze `{a}`, writer B
   publish `{a,b}`, and A cancel its stale attempt before accepting pending `{c}`
   at the new generation. A's local `{a,c}` rebuild would omit acknowledged
   `b`. The daemon now retains each root's exact identity and next expected
   generation from its own successful publications. It refuses an unexplained
   generation before history preparation, compiler launch or BIND, cancels that
   view and leaves the current image eligible. This adds no automatic foreign
   history recovery and no global single-writer policy. A fresh process cannot
   adopt an already published root.

The generation advances only after a known successful final device write.
Compiler, history, BIND, partial-read and cancellation failures do not advance
it. Optional evidence or read-only close errors after successful publication
cannot undo the publication. Failed cancellation retains the view and retries
cancellation before obtaining a new snapshot.

The existing ledger remains bounded at 32 outstanding distinct records,
including a frozen batch. It keeps admitted records without eviction, counts
full-ledger report rejections, immediately reuses acknowledged slots and retains
published images until session teardown. Exact batch/base-generation ACK,
source leases, old-frame image bindings and retained handback are unchanged.

## Focused regression scope

The generated-code CALL fixture starts with forward history only. It checks
one pushed CALL word, one RET pop, preserved flags and source effects, and the
exact retained miss tuple. A separate build adds only that observed RET tuple
and checks post-CALL effects on a separate invocation. It does not resume or
replay the handed-back request. Seven decoded-graph methods cover multiple
callees/callers, nested words, shared returns, terminal/undecoded targets,
duplicates/cycles and atomic work-budget refusal without new source reads.

The entry fixture extracts the actual production mismatch branch, publication
gate, immutable publisher and batch acknowledgment helpers. Scheduled pthread
actors exercise both gate orderings, retaining the old image, frame and stack
contents. An old-setter negative control must fail an assertion; a compile
failure, crash or timeout cannot count as detection. IRQ and physical execution
primitives remain substitutes. The benchmark-overlay fixture reuses this
driver and is also selected.

The daemon policy fixture uses supplied transport/control operations, including
two writable descriptors, local successful publication, stale BIND, a foreign
generation advance and a fresh-process case. It checks refusal before compiler,
BIND, history mutation or device write, plus expected-generation behavior on
failure paths. These are mechanism fixtures, not captured kernel ACK receipts.
Final-device-write failure and generation overflow were source-reviewed rather
than newly injected in the daemon fixture. The competing publisher's snapshot
and ACK outcomes are substituted, not observed from a running provider.

## Validation status

Static source review, whitespace checks and complete-patch reverse checking
passed. All builds and tests ran in an isolated ext4 copy on the designated
VM's existing normal `7.0.0-38-kdlock1` boot
`6148a091-cca7-4258-8d0b-d75227134564`. Python drivers used the pinned
translation interpreter.
The daemon and three basic C programs build with `-Wall -Wextra -Werror` and
pass without build warnings. No current pass is borrowed from an older source
snapshot. The full suite was not requested or run.

| Python driver | Final result |
| --- | --- |
| `execution/test_exe_registry.py` | 36,543 checks at default pool 64; 70,972 at fixture-only pool 128; 16 mutations detected |
| `execution/test_mutex_images.py` | Mutex, spin, direct and origin programs passed |
| `execution/test_native_service_join.py` | Write, downgrade and read cleanup cases passed with supplied physical/task primitives |
| `infrastructure/test_source_lifetime.py` | 49,922 checks; 37 mutations detected |
| `admission/test_text_regions.py` | 86 passed |
| `codegen/test_returning_calls.py` | 22 passed |
| `codegen/test_source_frontier.py` | 11 passed |
| `infrastructure/test_compiler_manifest.py` | 12 passed |
| `bench/test_mmap1_provenance.py` | 20 passed |
| `bench/test_mmap1_settled.py` | 13 passed |
| `codegen/test_retained_misses.py` | 4 passed |
| `codegen/test_direct_call_depth.py` | 4 passed |
| `admission/test_context_guards.py` | 43 passed |
| `admission/test_address_guards.py` | 7 passed |
| `admission/test_audited_c_memory.py` | 13 passed |
| `execution/test_jit_entry_scope.py` | 9,501 checks; 58 mutations detected, including the old ungated mismatch setter |
| `execution/test_bench_completion.py` | 10,392 checks; 7 completion mutations detected; actual observation overlay applied with zero fuzz |
| `codegen/test_native_call_boundaries.py` | 13 passed, including forward-only CALL history followed by a later RET-history build |
| `codegen/test_indirect_call_learning.py` | 7 passed |

The 128-image registry case changes only the userspace fixture. It does not
change the provider's default 64-image capacity. The benchmark overlay applied
with recorded line offsets; its accounting checks are not a benchmark run.
Decoder warnings and Python deprecation warnings remain in the passing CALL
logs.

The provider compiled and linked against the existing separated normal kernel
output with `W=1`, default 1024/1024 mutex bounds and no kernel reconfiguration.
It produced eleven warnings: one compiler-name mismatch (both identify Ubuntu
GCC `15.2.0-16ubuntu1`) and ten objtool warnings. The latter comprise three
`MITIGATION_RETHUNK` naked returns, one modified stack frame, one undefined
stack state and five calls without frame-pointer setup. Exact warning lines,
commands and module artifact hash remain in [selected-summary.json](selected-summary.json)
and the raw build log. These warnings are not reported as resolved.

## Preserved receipts and limits

The local receipt directory is `/tmp/kdlock-batch-checks-6_0ij1lo`; the guest
copy is `/mnt/kdlock-builds2/kdlock-batch-checks-zgrfka_g`. All 27 check commands,
logs, statuses, source patches, frozen inputs, original manifests and final
environment checks are retained. Independent offline review verified the raw
archive identity, archived result equality and all 27 log hashes.
[source-verification.json](source-verification.json) verifies all 1,095 frozen
source files against the committed blobs and current working bytes, including
the new private `publication.inc`. The frozen and working guest sources also
matched throughout the run.

Initial/final checks found the same normal boot and no project module, task or
source process. Existing kernel build inputs, all 134 original source receipt
roots and the original manifest inventory remained unchanged. Historical
contents under `bench/results`, `results` and `kernel_baseline/experiments`
were excluded from content rehashing; their declared hashes and exclusions
remain retained. Those historical contents are not claimed as freshly
hash-verified. Final free space was 3,755,757,568 bytes on guest `/` and
15,113,363,456 bytes on the build filesystem. No cleanup was performed.

Raw artifacts are under
`bench/results/10.176.26.71/raw/tests/call-batch-d4349577-20261108/`.
[artifact-verification.json](artifact-verification.json) records exact sizes
and hashes. Compact receipt indexes bind the full original state and manifest
bytes kept in the raw archive; they do not replace those records.

An initial staging request and a controller request returned only **aborted
before dispatch**, without an approval-review reason. Neither executed checks.
The user approved retrying the same staging/check route; staging and the exact
controller route then completed successfully. No alternate route or review
control change was used. The earlier `/tmp/kdlock-call-batch-review` bundle is
preserved as the pre-run review snapshot, not the final validation receipt.

No provider load, live publication, mmap1/application, campaign, learning run or
performance measurement occurred. No guest boot, kernel configuration or review
control changed. Full kernel batch membership and ACK attribution remain
source-derived; there is no new captured kernel ACK or loaded-image digest.
