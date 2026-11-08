# Cumulative root learning batches

Implementation `fed19bd66d82898a3a15af41c0b1a7a465d09e6a` on
`codex/mmap-reached-jit` replaces the single pending-tuple bottleneck with a
32-record ledger per translation entry. The daemon unions a finite snapshot
with that root's cumulative same-session CALL/IJ history and invokes the
ordinary compiler once for the resulting full-root input. Miss records are
targets or edges, not separate JIT programs. Publication selects one current
immutable generation for the logical root.

The selected overflow policy keeps admitted records without eviction, counts
rejected report events when full, and continues existing handback/image
eligibility. Repeated rejected keys can increment the counter repeatedly; it
does not count exact distinct lost edges. A rejected target needs another
invocation to report it after space becomes available. Successful publication
immediately reuses only its acknowledged miss slots. Published executable
images retain their existing session-wide lifetime, including after their
captured frames finish; no image collection was added.

## Implemented protocol

The version-22 capability adds a separate snapshot/BIND/CANCEL control ABI.
Existing 64-byte registry/upload packets, image protocols 2/3 and wrapper words
are unchanged. Each writable open description owns one frozen view. Successful
copying makes that view bindable, but neither reading, compilation nor CANCEL
acknowledges records. Final successful publication checks the exact root/base
generation and consumes only the bound snapshot's revision-qualified records.
Later arrivals remain pending with their actual reporting generation. Reports
newly arriving from superseded images remain excluded.

Direct CALL keys are `(CALL,target)`; IJ/RET keys are `(IJ,from,target)`, using
the existing dispatch next-PC convention. Duplicate outstanding keys share a
record. The same key can become a new obligation after acknowledgment if a
later current image still misses it. Cumulative compiler history is separate
from these outstanding obligations.

Authoritative histories and frozen attempts use the complete root identity and
a fresh boot/daemon/device session. Missing established history, another
session or history-less preparation at a nonzero generation refuses the build.
Batch startup preserves existing workspaces. Compatibility exports are never
used as batch compiler inputs. The batch path bypasses the old command cache;
upload retries retain the exact frozen compiler artifacts. Rebinding that view
can discard only its matching private partial upload, without acknowledging
records or changing the current image.

The [daemon guide](../../../../../daemon/README.md#finite-abi2-learning-batches)
owns controls and failure handling; the
[lifetime guide](../../../../../docs/design/lifetimes.md#executable-images-and-guarded-spin-transition)
owns physical image and frame retention.

## Selected VM checks

All compilation and execution occurred in new isolated ext4 copies on the
designated VM, on normal release `7.0.0-38-kdlock1`, boot
`6148a091-cca7-4258-8d0b-d75227134564`. The pinned translation Python was used
with bytecode output disabled. The complete loadable recovery snapshot
`kdlock-builddisk-clean-20261031` was observed through the existing monitor
before checks. No snapshot, boot or configuration change occurred.

The final affected recheck passed, with no skipped or unrun selected checks:

| Check | Result |
| --- | --- |
| Strict daemon build | Passed with `-Wall -Wextra -Werror` |
| Basic control-call, daemon-policy and daemon-provenance C programs | All three passed |
| Production registry/control driver | 36,543 checks with the default 64-image pool; 70,972 with the fixture-only 128-image variant; 16 mutations detected |
| Immutable image driver | Mutex, spin, direct and origin image programs passed |
| Native service join | Write, downgrade and read cleanup cases passed with supplied physical/task primitives |
| Complete source-lifetime driver | 55,922 checks; 37 mutations detected |
| Provider build only | Passed; provider was not loaded |

The provider rebuild retains one compiler-identity diagnostic and ten objtool
return/stack warnings, listed in
[recheck-selected-summary.json](recheck-selected-summary.json). These remain
limitations, not resolved mitigation coverage. A new 1,664-byte snapshot stack
frame warning in the first build was removed by moving cold request storage to
the writable descriptor and copying only the input header. No warning threshold,
kernel configuration or runtime probe was weakened.

Four compiler drivers had already passed on the first source snapshot:

| Driver | Result |
| --- | --- |
| `admission/test_text_regions.py` | 86 passed |
| `codegen/test_returning_calls.py` | 21 passed |
| `codegen/test_source_frontier.py` | 11 passed |
| `infrastructure/test_compiler_manifest.py` | 12 passed |

These 130 tests were not repeated after unrelated daemon/control/fixture
corrections. [source-verification.json](source-verification.json) lists all six
changed source files between the snapshots and verifies that the current
implementation matches every one of the final snapshot's 1,093 source files.
Keep the two source receipts separate; these are component checks, not pooled
runtime or performance measurements. The 128-image setting is only a userspace
fixture variant; the provider build retains the 64-image default.

## Preserved unsuccessful attempts

The original overbroad preflight rehashed historical result contents in old
source copies. Its identified controller was interrupted with SIGINT followed
by SIGTERM, and subsequent inspection confirmed the PID was absent. Retained
state shows zero checks and no build/work copy. Its source copy and receipts
remain; this attempt supplies no test pass. See
[interrupted-interruption.json](interrupted-interruption.json).

The first source-scoped run remains an overall failure:

| First-run result | Correction and final evidence |
| --- | --- |
| Daemon and two daemon fixtures did not compile | Correct the signedness of the root-kind comparison; strict builds and both programs passed on recheck |
| Native service join did not compile | Add the include path needed for the new public control header; all three cases passed on recheck |
| Source-lifetime positive program passed, but mutation selection stopped early | Update the exact stack-feature mutation marker after the capability declaration changed; the complete driver passed on recheck |
| Provider built with the new large-stack-frame warning | Move snapshot input storage off the kernel stack; final build no longer reports that warning |

The new capability fixture's getter-name typo was corrected by source review
before the first source-scoped execution. Its 86-test driver passed there.
No fixture failure was counted as a pass. Deliberate error/refusal cases inside
passing daemon fixtures remain visible in their logs.

## Receipts and limits

The first source-scoped copy is
`/mnt/kdlock-builds2/kdlock-batch-checks-djpstlb8`; the passing affected recheck
is `/mnt/kdlock-builds2/kdlock-batch-checks-vkvigvie`. Their source-state,
source-hash, command, log, return-code and final-idle receipts are preserved
separately. Initial and final checks confirmed the same release/boot, no project
module/task and unchanged source bytes. The captured kernel build inputs also
match before/after the external-module build.

The tracked `*-source-receipt.json` files are compact indexes. They bind each
complete original source-state receipt by SHA256 and its exact archive member;
the full excluded-path lists remain in those preserved originals.

The source-scoped controllers hash original source files and compare original
manifest/state bytes. Historical contents under `bench/results`, `results` and
`kernel_baseline/experiments` are excluded from content hashing and reported as
such; their declared hashes remain in the retained original manifests. Do not
describe those excluded contents as freshly hash-verified. No existing source
tree, history or recovery data was modified or cleaned.

Ignored raw files are under
`bench/results/10.176.26.71/raw/tests/learning-batches-b9a31a06-20261108/`.
[artifact-verification.json](artifact-verification.json) records archive sizes
and SHA256 values. Both source snapshots, passing/failing logs, interrupted
controller metadata and its retained guest result are preserved.

No full suite, provider load, live publication, mmap1 application, benchmark or
campaign ran. The earlier live-launch restriction remains unresolved. Existing
v21-specific settled/provenance campaign gates are unchanged; the v22 batch path
is not claimed compatible with those launch/evidence paths. These supplied-
primitive fixtures and builds do not establish actual MM syscall behavior,
returned JIT bodies, physical delegation-chain length or throughput.

Capture eligibility in `NORMAL`, `CALL_MISS` and `IJ_MISS`, exact captured-image
ownership and first-unexecuted-position handback remain unchanged. No active
code is patched. One invocation still stops discovery at its first permanent
handback; batching combines separate invocations and cannot discover deeper
misses behind it. The independent munmap g9 outer-RET relationship remains
unresolved. No read delegation, MM/lock API change, image reclamation, push or
merge was performed.
