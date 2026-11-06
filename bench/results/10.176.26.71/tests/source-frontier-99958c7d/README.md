# Original-instruction frontier: focused checks

The generated-state and retained-owner checks passed, and the provider, daemon
and mmap1 observer built in the VM. These component checks do not establish
execution of the kernel's diagnostic branch, actual MM handback, mmap1
throughput, or Nano acceptance. The existing text-region driver still has seven
failures and one error, reproduced against its baseline.

## Source and build identity

- Branch: `codex/mmap-reached-jit`; no merge to `master`.
- Design: `722e4972`; initial implementation:
  `d57f7523f4d6438e4c31a840524f48bc7413fb56`.
- Validated candidate:
  `99958c7d4d79bc9ddcdac290b51ed0bd40328487`.
- Frozen source: `/root/kdlock-inputs/frontier-99958c7d`.
- Source-state SHA-256:
  `3c068315e767e81591f3d62346460867bcc8c8937bf626fba264502ef4de3122`.
- Manifest SHA-256:
  `99a5fa51bbf4c0b25afefd2e5fc5f61d417653b14d2e0bb64b7c09d9b52c0884`.
- Build tree: `/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build`, kernel Build ID
  `5f2fce72a33480f6e79a79b374b21a0db377ecd1`.
- Provider SHA-256:
  `bca4c9557f05e9c21974386418b342e392ac990021ff6a2df845cf51ae968558`.
- Daemon SHA-256:
  `253243ff1d49cd5422db63d67f37666e22d1247c39b12d5c9e29bf004a375eb9`.
- Observer SHA-256:
  `cba9230e4dcf1aa5987448924dabf74302374c949f2f6e117a3f254bf6259530`.

All compilation and execution ran on VM `10.176.26.71`. These checks ran on the
ordinary kernel, boot `74106c59-6990-4d67-a479-8aadf4fcdbf0`, without loading a
module or starting a benchmark. The provider used `W=1`, NUMA enabled, spin
batch 1024 and 128 image descriptors; daemon compilation used
`-O2 -Wall -Wextra -Werror`.

## Implemented behavior

The decoder recognizes only the complete five-byte `67 48 0f b9 3a` form at an
instruction offset requested by the existing decoder. That branch ends at a
`SOURCE_FRONTIER`; other branches keep the original JIT. No byte-pattern scan,
additional call closure, returning instruction service or instruction
interpreter was added.

Capability version 18 negotiates `KD_JIT_CAP_SOURCE_FRONTIER`; the immutable
image requires `KD_IMAGE_REQUIRE_SOURCE_FRONTIER`, ABI2 and the retained service
queue. Generated execution exports the first unexecuted original IP, current
SP/GPRs and existing arithmetic-flags representation. It does not execute the
instruction, push or consume a source CALL word, replay earlier effects, or
report a learned edge.

`kd_jit_source_frontier()` checks the current retained frame, exact packet,
executor/origin identity, source lease, immutable image, idle typed-call state,
stack bounds and exact leased source bytes. Success selects the existing
retained ownership handback and its Native ACCEPT/final ACK. Ownership and
source/frame lifetimes remain retained until their ordinary terminal events.
No MM body, queue admission, killable arbitration, downgrade protocol or
per-lock image boundary was changed. Broader flags/SIMD and IRQ/NMI support is
not claimed.

## Focused validation

| Check | Result | Scope |
| --- | --- | --- |
| `codegen/test_source_frontier.py` | 5 passed | Actual generated code in the VM, with controlled source memory |
| `execution/test_native_service_join.py` | write, downgrade and read passed | Production frontier consumer and retained join; supplied physical/task primitives |
| `infrastructure/test_source_lifetime.py` | 55,916 production checks and mutation matrix passed | Includes refusal when the new capability is absent |
| `admission/test_kernel_symbols.py` | 26 passed | Resolver optimization remains covered |
| `bench/test_mmap1_campaign.py` | 9 passed | Existing learning/proof/quiet separation |
| `execution/test_jit_entry_scope.py` | Production and mutation matrix passed | Existing dispatcher behavior; legacy retained positive execution remains explicitly refused |
| `admission/test_text_regions.py` | 82 run, 7 failures, 1 error | New capability-query case passed; baseline has the same failures/error in 81 cases |
| Provider, daemon, observer | Built | No module load in preflight |

Generated execution verifies a preceding atomic increment changes 5 to 8
exactly once, exports the original frontier IP/SP/argument registers and leaves
the post-frontier write unexecuted. Another branch completes in JIT. Exact-byte,
embedded-immediate and unsupported-provider cases are included. The retained
join covers write, downgraded-read and read release, exact nested owner records,
Native ACCEPT/final ACK, and once-only terminal source/stack retirement; 18
invalid frontier states are refused without packet mutation or learning.

The generated and join passes were reused from `7438cd5b` only after verifying
their relevant source bytes match `99958c7d`. The capability mutation change at
`99958c7d` is test-only. `all_test_drivers_passed` remains false in the final
preflight receipt; the positive focused checks do not hide the text-region
driver's failures.

## Retained unsuccessful attempts

| Attempt | Observed result | Correction or limit |
| --- | --- | --- |
| `d57f7523` | Three errors in the five-case generated driver | Added shared terminal-prefix metadata; padded the negative fixture's source window so it tests provider refusal |
| `2d24c686` | Generated driver passed; legacy entry driver had 4 failures in 9,446 checks | Moved retained positive coverage to the Native service-join fixture; kept the legacy refusal intact |
| `7438cd5b`, first run | Entry matrix exceeded its 180-second aggregate command budget | No remaining owned tasks or modules; partial files retained. Later aggregate budget 600 seconds; individual compile/run bounds unchanged |
| `7438cd5b`, second run | Three retained joins passed; text driver failed | Baseline reproduction found the same seven failures and one error |
| `7438cd5b`, third run | Source production checks passed; capability mutation matcher did not match | Updated the test matcher and added the new missing-feature case at `99958c7d` |
| `99958c7d` | Focused checks/build passed; known failed text driver retained | No runtime or benchmark acceptance follows from preflight alone |

The text failures concern earlier eager/retry-count expectations and compact
extension expectations; the error is the same mocked Native-discovery-state
error in both versions. Decoder bounds and call closure were not changed to
satisfy those expectations. Earlier resolver context-policy failures remain in
the separate resolver report and are not counted as newly introduced here.

VM receipts and complete driver logs remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/`, in the exact
`frontier-preflight-*` and `frontier-text-baseline-7438cd5b` directories.
Source-host launch receipts retain each attempt and the exact commands.
