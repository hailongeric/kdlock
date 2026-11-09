# Proxied rwsem downgrade and retained writer, 2026-11-09

The implementation and focused checks pass. The bounded live learning check
failed its quiescent-boundary validation; it is not a runtime pass for the
proxy read suffix or a performance result. Exact retirement, normal unload and
normal-kernel recovery passed. No retry or longer campaign followed.

## Candidate and behavior

- Implementation: `adf4d2680d0b07e38cf5a0a2f9d609673b425636`.
- Fixture alignment: `3ceb7f002672e8e9a4b2a14de6660944338088e5`.
- Branch: `codex/release-unit-boundaries`, isolated checkout
  `/tmp/kdlock-reached-path-translation`, based on `0a58c04819b12c1b5d0d45d34cb4b4f04aa6a731`.
- `master` remained `343439f5d433affa2bfe416d12d27cccb9a44f82`;
  unrelated main-checkout work was preserved.

A downgrade actually consumed by the JIT makes ownership logically read-only
while retaining the exact physical writer gate and selected admission phase
`-1`. The same root image continues through its decoded read suffix. The exact
matching read release consumes that physical writer once. A handback after this
transition retains the writer on the executor and uses the original logical
task's typed `UP_READ` service and physical release acknowledgment.

A handback before downgrade keeps the existing native-tail behavior: native
downgrade publishes a real reader credit, releases the writer gate/phase, and
transfers that read credit through `read_to_native`. Ordinary local/read-credit
releases keep their existing final-decrement contract. Proxy final release is
limited to the original logical task in ordinary task context; IRQ-off,
preemption-disabled, preemptible-RCU and cross-task non-owner variants are not
supported by this candidate.

Only typed proxy downgrade is exempted from the compiler's physical-release
unit boundary. Other releases retain their boundary. The existing depth/CFG
bounds, real CALL/RET words, source/frame leases, exact generations and
unrelated MM operations remain in place. No kernel MM body or surrounding
wrapper tracing/accounting/callback/cleanup operation was changed. Trusted
kernel/module source remains the selected production policy; these results do
not establish checked semantic admission or whole-kernel equivalence.

All implementation and regression code was committed before the first test.
After the completed first run exposed two fixture failures, all fixture fixes
were committed before a fresh frozen rerun. Running inputs were not edited.

## Focused guest checks

The first `adf4d268` run failed `mutex-test_rwsem_read_admission` because it
extracted removed scalar-cohort writer helpers, and `mutex-test_writer_query`
because its extracted provider initializer lacked the entry-scope validator.
The original failure logs and receipt remain in `initial-checks`. No provider
build was scheduled after these failures. Source hashes and final idle passed.

The fixture-only follow-up keeps the current reader polling/OSQ/count/barrier
checks, aligns final read-release expectations, and supplies the current scope
validator inputs. Current queued-reader precedence and exact writer phase/drain
coverage remains in `test_admission.py`; retired positive writer-cohort helpers
were not recreated. No production code changed between the two runs.

The fresh `3ceb7f00` run passed the two basic programs, ten directly affected
Python drivers, daemon build and new enabled-MM observation-provider build:

| Check or build | Result |
| --- | --- |
| `daemon-build` | pass |
| `test_control_call-build` | pass |
| `test_control_call` | pass |
| `test_daemon_policy-build` | pass |
| `test_daemon_policy` | pass |
| `codegen-test_release_units` | pass |
| `codegen-test_direct_call_depth` | pass |
| `admission-test_text_regions` | pass |
| `execution-test_release_units` | pass |
| `execution-test_native_service_join` | pass |
| `mutex-test_admission` | pass |
| `mutex-test_rwsem_read_release` | pass |
| `mutex-test_rwsem_read_admission` | pass |
| `mutex-test_rwsem_api` | pass |
| `mutex-test_writer_query` | pass |
| `provider-build-only` | pass |

This is the basic and affected selection, not a full suite. Codegen release
units ran 24 tests, direct-call depth ran 4, and text-region admission ran 86.
Canonical admission ran 18 deterministic cases; reader-count admission/release
ran 21. Native-service and release-unit fixtures cover proxy continuation,
exact final release, real native downgrade, nested/non-LIFO boundaries,
stale/duplicate identity refusal and task-context restrictions. Deterministic
physical/task substitutes do not establish concurrent kernel progress.

Every driver ran only in the VM using the pinned translation interpreter and
CPU 63. Codegen caps were 240 seconds, other driver caps 180 seconds; basic
build/run caps were 60/30 seconds. The provider build cap was 480 seconds.
Both before/after source maps, original source receipts, platform and final
idle checks passed. No deadline or skip was counted as a pass.

Provider profile: enabled-MM `7.0.0-38-kdscope5`, `W=1`, selftest 0, NUMA 1,
spin/mutex batch 1024, mutex NUMA boundary 1024, and 128 images. The observation
overlay applied with zero fuzz; its offsets are retained. Source/output binding,
configuration, exports/imports and kernel input hashes passed before/after.

- Provider SHA256: `663cec836c9661cb744cd62cd64983d3f213e56cd3e6e7e4eac05902d6671c92`.
- Provider Build ID: `3dd2f72972d23eb186aa4c8d15a069088b914174`.
- Provider note SHA256: `5079462f965691f10d3b47f235000f70be6f5b9dbdb44e00b385d95ca2faa27a`.
- Preparation manifest SHA256: `24340a78864ffd453809b9b306459ab5fab6b581e9ad9a84254a1c8ed02b03b8`.

Build logs preserve the compiler-difference warning and objtool warnings about
handwritten returns, stack state and frame setup. This build is not evidence of
complete return-mitigation coverage.

## One bounded real-syscall observation

A fresh real QEMU listing confirmed `kdlock-builddisk-clean-20261031` on all
disks. Host snapshot, pinning and frequency checks, guest idle and >2 GiB
root/build headroom gates passed. The existing enabled kernel was selected once,
without rebuilding it or changing the normal GRUB default. Standard schema-2
installed/running verification passed, including the guest baseline manifest,
Build ID `357a7115d21941960b90262ac1165bf70d1b398e`, `kd_mmap=on`, and lazy
preemption. Live boot: `aa09faf8-4ee7-4114-9624-5d468a1aba40`.

The unchanged upstream `mmap1_processes` program used its actual system calls.
Pinned upstream revision was `75f66e45697e6f5f49c33dd950c4e6b289198f8f`.
Previously prepared binaries and dependencies were reverified by current
`inputs_from`; their input receipt SHA256 was
`beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0`.
The newly built provider/daemon and frozen current source were joined by exact
hashes. The required unchanged identity-probe artifact was hash/input verified
for configuration only and was never loaded.

One `observe.py` invocation selected processes `[1,8]`, one application per
point, six warmup plus two nominal measurement samples, 30-second application
caps, learning/prewarm 180 seconds, close 40 seconds, runner 360 seconds,
finalizer 90 seconds and outer wait 480 seconds. Translation stayed active;
service tracing stayed disabled. Existing selected-service counters were the
only added runtime observations. No targeted handback PC/reason/lock-state
capture, traced run, continuation or replacement run was requested.

| Workers | Application / learning verdict | Drain | Unscored nominal pairs/s |
| --- | --- | --- | --- |
| 1 | pass; wholly local interval, generation-1 images in final registry | pass | 220215.5 |
| 8 | failed after application return: no quiescent learning boundary within deadline | pass | 34370.5 |

The one-worker point was entirely local: 1,757,925 selected local acquisitions
for each root and zero JIT entries. Its first two images were published at
generation 1. Publication is distinct from JIT-body completion.

The eight-worker counter interval recorded:

| Root | Selected/submitted/JIT-entered | Handback finished | Returned JIT bodies |
| --- | ---: | ---: | ---: |
| `vm_mmap_pgoff+0x118` | 274,767 | 274,767 | 0 |
| `__vm_munmap+0xbb` | 274,766 | 274,766 | 0 |

The application returned and its workers drained, but its final execution-session
verification raised `demand learning did not reach a quiescent boundary`.
`pilot_data_passed=false`, controller return 1 and `short-result.passed=false`
remain unchanged in the retained evidence. These counters do not locate the
handback or establish that proxy downgrade was consumed. Neither post-downgrade
suffix completion nor a physical multi-request chain was measured. The raw
rates above are failed/unscored learning observations with changing image
history; no Native comparison, strict peak qualification or performance gain
is claimed.

The unchanged finalizer separately passed exact retirement: bindings 17→0,
source state 2, modules/frames/writers 0, normal `rmmod`, drained and final idle.
Its `passed=false` and `campaign_complete=false` remain preserved because the
campaign was stopped; `retirement_passed=true` is the separate cleanup verdict.

Normal recovery then passed standard identity verification for
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`f0a22d78-8d31-46a8-b6d2-918b25145696`, with final idle and headroom checks.
No force unload, source cleanup or snapshot rollback was used.

## Retained evidence

[validation.json](validation.json) preserves check/build identities, both live
application verdicts, selected counters, retirement and normal recovery.
[raw-index.json](raw-index.json) binds the retained files by SHA256 and size.
The complete source-host evidence is retained at:

`/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/rwsem-proxy-read-3ceb7f00-v1`

It includes both focused-check bundles, source manifests/states, original host
receipt joins, private-preparation and both boot receipts, reviewed controllers,
complete short-run outputs, and the 171-entry live evidence archive. Workspace
symlinks are retained as link metadata without following them. The initial
collector refusal of a workspace link is also retained; it caused no live state
change.

Live archive SHA256: `aa58fe4e05a3697dcc07525c8582c9d7029aedff7befb2b949b789517161d997` (102,144,000 bytes).
Guest frozen inputs and output receipts were retained; no cleanup was performed.
