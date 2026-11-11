# Kernel 8 managed killable K03 claim failure and ordinary recovery

K03 remains **failed**. All five named mechanism scenes and both learning scenes
completed, and all 19 children have actual waitpid observations. The final
fixed-image assertion then rejected a second pending fact key from the same
native helper frontier. The original runtime verdict `failed_retained` and outer
verdict `INCOMPLETE_CHILD_RETAINED` are retained byte for byte. Ordinary recovery
later archived and settled both keys and retired the provider successfully; that
cleanup does not turn K03 into a pass.

This directory records the original K03 execution, its ordinary shutdown and the
source-only checker correction. The earlier region and child-exit corrections
remain separate in [region failure](../kernel8-killable-region-failure-20261111/README.md)
and [exit recovery](../kernel8-killable-exit-recovery-20261111/README.md). Existing
private rwsem and mutex passes remain in their own committed evidence.

## Identity and retained results

| Item | Exact identity |
| --- | --- |
| Runtime source | `6a4ba5a1734dfa5dc0b52e7fd5a6fda3d85b8196` |
| Compiled fixture source | `140aecc4f83a6b6ae6f20245234e8a63504f9210` |
| Linked kernel core | `0d42063ead37dc8fc1631fa56c8348890ede9c5f` |
| Fixture module SHA-256 | `74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8` |
| Kernel release / boot | `7.0.0-38-kdrebuild8` / `e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0` |
| Kernel build ID | `a33dd4d11d0f0c6649107507e685b6e86e716c1a` |
| Original runtime result SHA-256 | `56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a` |
| Original outer result SHA-256 | `fc1375e0653d88fec37b72242da86408151293034028fa7170e099c5bc873c62` |
| Ordinary cleanup result SHA-256 | `40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0` |
| Restored producer proof SHA-256 | `10ea0bbd3545562930d7a593bcdb4c3c76335e62c7ef0b40d5bba636df804bbd` |
| Shutdown archive | 3,318,053 bytes, SHA-256 `0cdb77a5c44ff7ad4dcb81081f9eccd37d041702638a43c62e133a31563e7cd7` |

The seven completed rows are `ready-before-fatal-cancel`, `reader-drain-cancel`,
`queued-exit-before-holder-release`, `learning-0`, `learning-1`,
`origin-signal-wakes-foreign-c`, and `candidate-cancel-drains-current-w`.
The raw observation header is ABI 1, 20 words, capacity 131072, count 241,
overflow 0. Scene receipts retain completed role fields until reset. The saved
pre-signal recovery status shows all roles reset, zero native scopes, empty
queue/gates and an idle pool before the retained controller was terminated.

## Why the final assertion failed

Cycle 3 CLAIM SHA-256 is
`d4b44fa65d351daf5a214674b21e4eefc58ab7fb55001d050577591da6568214`.
Cycle 4 CLAIM SHA-256 is
`c173323281bdcefffd48457f95586b82b601445dfd61bb55c0b33768332d67a0`.
Cycle 4 preserves the first row exactly and adds the second distinct key:

| Pending record | Incarnation |
| --- | --- |
| `0xff110003bf8001d4` | 1 |
| `0xff110003bf8002c4` | 1 |

Both rows have producer `0xff110003f538fc00`, image `0xff110003f538fd38`,
epoch `0xff11000346654b40`, the same 203-byte version and ten identical remaining
scalar words. Their exit is COVERAGE_MISS (3), detail UNRESOLVED_TARGET (10),
source IP and cursor `0xffffffffc000b4e6`, dynamic target
`0xffffffffc000b300`, phase TARGET_READY (1), classification UNCLASSIFIED (0),
and entry result 0. The target lies outside all five exported source regions.
The reached source CALL is the actual five bytes `2e2e2effd0`; the following
native instruction is `0xffffffffc000b4eb`.

The raw root chains are reserve/frame/grant/ENTER/EXIT/FORWARD indices
102/103/112/113/114/115 and 191/192/204/205/206/207. They have distinct task
lifetimes, with a slot free between episodes, despite reused storage addresses.
Each chain has its exact root, source state, acquisition, image, physical
executor and native frontier. They are not combined into one acquisition.
Cycles 3 and 4 retain the same image and publish nothing. A new pending FactKey
is still a new fact: literal `no_new_facts` is false. Its occurrence does not by
itself establish new ordinary learning or a new image publication.

The reviewed correction at `5c14b483ca16b3bba8f3dd40a00f16a6efefc12c`
keeps both exact pending keys, requires exact root/CALL/JIT/FORWARD provenance,
and separates pending native-frontier reservations from ordinary-learning
checks. K03 did not execute that corrected checker. Any AST-only check or K04
execution is recorded separately.

## Ordinary reconstruction and shutdown

The recovery helper retained the original 146 runtime files (1,537,842 bytes)
and reconstructed both producer images from the saved SOURCE/CLAIM/BUILD history
through the normal compiler. Its receipt records equality of all five STAGE
blobs and saved ELF `.text`, without new GNU assembly or source execution.
It restored the actual publication/ACK history: cycle 1 ACKed zero keys, cycle 2
ACKed one, then cycles 3 and 4 retained the two distinct pending keys. Recovery
introduced no publication and no coverage ACK.

Only after reconstruction and the all-clear status did the helper use the exact
PID/start-time identity to send SIGTERM to retained controller 12651 and observe
exit plus descriptor release. QUERY recovered its exact cached END sequence 17.
The remaining operations completed with status zero:

| Operation ID | Sequence | Meaning |
| --- | --- | --- |
| 0 | 0 | QUERY cached END17 |
| 9 | 18 | SHUTDOWN |
| 10 | 19 | ARCHIVE_CLAIM, exact two keys |
| 11 | 20 | SETTLE, exact two keys and archive digest |
| 6 | 21 | END |

The archive contains both keys and the complete raw original history plus
restored producer proof. The SETTLE request carries that exact archive SHA-256.
RETIRE returned 0 and ordinary rmmod returned 0. The final status has no live
binding, source, runtime, trace or self-hold; roles and native scopes are clear,
the pool is idle and the gates are empty. The boot identity is unchanged,
taint remains 4096, and only `nls_iso8859_1` remains loaded. The original failed
result hashes were not replaced.

## Preserved files and offline audit

`failure-collection/` contains all 156 selected guest files (1,691,973 bytes), its
complete transport tar, indexes and collection controls. `recovery-collection/`
contains all 40 selected guest files (3,808,106 bytes), its complete transport
and controls. `source-host/` preserves the original launch, first-read, recovery,
copy and post-restart read-only controls, including failed transport receipts.
These files are historical inputs and must not be replayed as current commands.

`source-export/` preserves both complete 143-regular-member source transports,
manifests and state, the new exporter, and the exact 78-file kernel package
manifest. The new export has 1,612,508 source bytes; tar 1,730,560 bytes,
SHA-256 `35e9d05d6a4b88a3d3bffe95ad1f6674388486ff6e06d4be210aece753512989`;
manifest SHA-256 `6a14d26236343e37ae43a30c6e441783f979299b426c0a7b9fbbca9154f09645`;
state SHA-256 `95e3a54def7e87c595164b80ea329751f571a95ae64bf3dae821e1eacc4263cb`.
The exact member set is unchanged from 6a4ba5a1. Only the killable runner and its
README differ. `kernel/integration/RWSEM.md` was already a member and is
unchanged; all 78 kernel-core hashes still match 0d42063e.

`copy-index.json` maps every retained input to its original path, file identity,
raw hash and stored hash. Files of at least 65,536 bytes are losslessly gzipped,
except GNU object/ELF files retained directly. Both complete collection transports
and both complete source transports are retained; no duplicate tar was omitted.
`audit.json` records exact member/hash checks, event dictionary comparisons,
CLAIM scalars, reached CALL bytes, STAGE/ELF equality, archived history, cached
END17, archive digest and both SETTLE keys. `archive-copy.py` records how the
closed inputs were copied and audited. It uses only the standard library.
`SHA256SUMS` covers every retained file except itself.

This evidence establishes neither a complete K03 pass nor corrected-checker
runtime success. It adds no real MM JIT execution, full C epilogue return,
general nested cancellation, native-context expansion, broad kernel replacement
or performance result. The existing safe native-context frontier remains the
limit of this execution.
