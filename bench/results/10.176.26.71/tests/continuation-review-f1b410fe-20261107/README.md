# Offline continuation review at f1b410fe

The candidate remains on `codex/mmap-reached-jit`, based on
`f1b410fefffd48b06aab5b4d91cedc43bc771cca`. No merge or new live validation
occurred. This 2026-11-07 review inspected source and preserved receipts on the
original source host; it did not connect to the guest, run tests, load a provider,
boot a kernel or retry the stopped launch.

## Established state

- `971eddfb` adds exact, capability-21 pre-STD/CLD boundaries; `d726952d` corrects
  one fixture setup; `c1b624c9` records their checks. `f1b410fe` adds the expanded
  publication gate and configurable cleanup bound. Production code is unchanged
  by this review.
- [checks-result.json](checks-result.json) records 10 settled-runner and seven
  campaign fixtures passing at `f1b410fe`. These are prior fixture results; the
  synthetic `rate: 42` in a fixture log is not mmap1 throughput. Reused provider
  bytes came from `d726952d`, SHA256
  `602c5bd93770e8f4118ae163f66b12382d8b39cd888f297f4efd9be7fed48262`.
- [recovery-final.json](recovery-final.json) explicitly records provider load,
  campaign launch, live publication verification, learning application, fixed
  measurement and short learning-continuation implementation as not executed.
  It records no uncertain actions and no launch retry.
- [normal-boot-capture.json](normal-boot-capture.json) records successful recovery
  to `7.0.0-38-kdlock1`, boot `6148a091-cca7-4258-8d0b-d75227134564`, Build ID
  `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, and final idle state. This is saved
  recovery evidence, not a fresh guest-state observation on 2026-11-07.

The three receipts are byte-for-byte copies of the original source-host files.
Their SHA256 values are, in the same order as the linked filenames above:

| Receipt | SHA256 |
| --- | --- |
| checks-result.json | `10e789fed98660222ffbcc92b5f0483367264fdbce8cd2cf47f19e7e5785d7a7` |
| recovery-final.json | `06a31c8a65c73b77a3d80234cc43e8a4ec40c05e690863454a492dee4d6bee75` |
| normal-boot-capture.json | `5be6f1afe44009b2bd344cba665ace5c14f6c32dfe1c4c0749d34a23027a608b` |

## Source findings and evidence limits

`disassem/source_frontier.py:54-94` supplements only an actual decoded offset,
marks the instruction terminal, spills the current register mapping, exports
flags and the first unexecuted IP, then takes FULL exit 16. The runtime validator
in `kernel_module/execution/wrapper_entry.inc:334-409` checks the current retained
frame, source lease, immutable image, scalar packet, stack extent and exact byte;
it keeps the exported SP/GPRs and source CALL/RET effects. It adds no replay,
whole-function exception or alternate JIT. Direction decoding additionally
requires capability 21 and the frontier feature on the active device session.

The unchanged `kd_exe_capture_image()` at `kernel_module/exe.c:968-1013` accepts
NORMAL, CALL_MISS and IJ_MISS states when the immutable retained-miss image and
source/ABI/header requirements remain valid. Recompilation therefore does not
by itself withdraw an eligible image. This says nothing about stable benchmark
acceptance while learning continues. Original GS handling is unchanged.

The unchanged restore code at `kernel_module/spin/restore.inc:48-92` imports only
arithmetic flags (`0x8d5`), retaining the waiter's IF/DF/AC. The specific matched
`STD -> REP MOVSQ -> CLD` suffix is compatible with the documented DF-clear scalar
entry contract. The existing native suffix double proves prepared values and no
prefix replay in that fixture; it does not prove kernel restoration, general
flags/SIMD equivalence or execution of this suffix by mmap1.

The new publication gate selects the receipt's exact entry/generation assembly
and checks its SHA256. Its function-body predicate rejects a bare missing-callee
label, and its terminal predicate requires the exact STD source IP. These are
static publication prerequisites, not evidence that the terminal executed.
The `leased_direction_compiler` predicate is entry-wide across daemon history;
it does not independently correlate the lease message to the selected generation
or artifact hash. Preserve that provenance limit when interpreting a future gate
result; the receipt and frozen-input checks remain separate requirements.
Artifact hashes and resulting registry code/generation are recorded separately,
without an acknowledged digest/upload-to-generation mapping. Existing serial
upload ordering supports their association; no runtime correctness bug was
demonstrated under the frozen single-factory assumptions. The 17 runner fixtures
do not exercise `publication_gate()` end to end with mismatched history, compiler
log and artifact identities. These are evidence limits, not new failed tests.

A sequencing gap remains: the earlier long preparation did not learn
`mas_wr_bnode`; the next application's warmup first reached it. The candidate
still gates immediately after its one long preparation. A bounded fresh learning
continuation was discussed but remains unimplemented and unrun. If the required
expansion is not learned, the correct result is an unmet gate; the fixed point
must not silently become a discovery application.

Munmap g9's missing outer return `0xffffffff814f4918` is still a possible reached
miss, not observed execution. Complete delegated read-tail/later-writer behavior,
publication of the corrected expanded root and stable throughput remain unproved.
The [direction-boundary report](../direction-boundary-d726952d-20261106/README.md)
and [earlier failed point](../../bench/mmap1-settled-276f2647-20261107/README.md)
retain the detailed historical evidence.

## Platform blocker and legitimate resolution path

The coordinator's saved final turn records the exact platform error:
"This content was flagged for possible cybersecurity risk." The implementation
turn stopped after KD boot and before provider loading. This audit has no
command-specific review receipt, review ID or evidence that the restriction was
cleared. A new session, rephrased launch, different environment or changed review
controls cannot supply that clearance. No blocked action was retried here.

The official [feedback guidance](https://learn.chatgpt.com/docs/reference/troubleshooting#feedback-and-logs)
describes opening `/` in the existing chat, submitting feedback with the session
included, and retaining the resulting session ID. That is a supported reporting
route, not a documented automatic clearance mechanism. Feedback has not been
sent. Request investigation of this specific stopped kernel-lock validation,
including the exact error, candidate, pre-launch state and recovery receipt.
Coordinator: `01a1a73e-738c-70be-8baa-ee8260ae6012`; implementation thread:
`01a18132-2a71-7ea1-8bdd-625abb6e70fa`; coordinator completion:
`2026-11-06T20:20:50Z`. Share only reviewed, relevant records.

Live work remains blocked pending an explicit permitted resolution. Any later
measurement still needs a freshly learned and published expanded image, a new
fixed receipt after settlement, per-root entry/return/handback counters, unchanged
image/report/compiler/publication boundaries, exact drained conservation and
verified retirement/recovery. No new throughput result exists.
