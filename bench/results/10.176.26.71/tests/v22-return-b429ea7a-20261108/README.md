# V22 publication evidence and learned-tail return propagation

Source commits on `codex/mmap-reached-jit`:

- `c5512295512032cbe94f0e603e068a18fef132c8`: validate v22 batch publication
  evidence alongside the valid v21 contract.
- `ae1c33e4afc728f6b2c31b68588e5db8dd4093b0`: propagate caller returns through
  already decoded learned tails, independently of batch collection.

The final frozen source passed all fifteen selected Python drivers, including
235 unittest cases, the production-function C fixture groups and three basic C
programs. No selected check failed, skipped or remained unrun. This is source,
mock and supplied-primitive evidence; no provider load, live publication, mmap1
application, campaign or performance measurement occurred.

## V21/V22 compatibility

The previous equality-only v21 checks are replaced by one pure capability
validator shared by the existing scheduled capability observation and offline
association. It recognizes only versions 21 and 22, their known feature bits,
the immutable/exclusive/frontier prerequisites, and the decoder's existing
dependency and conditional memory-bound contracts. V22 also requires the batch
feature. Valid v21 packets without the optional module arena remain valid;
unknown versions/features, partial success packets and malformed fields refuse
association. The existing current capability query is compared with the four
captured compiler capability fields. No device read or poll is added.

V22 requires identical, correctly typed and bounded batch summaries in the
hash-bound compiler context, upload context and completed upload receipt:
token, revision, slot, count and overflow-event count. Upload context identities
must also match the accepted-payload receipt. Batch uploads cannot claim the
legacy command-cache path. Empty batches require cold generation-zero UNINIT
preparation. V21 retains absent/null batch metadata and its existing cache
association behavior.

All prior payload/manifest/header, contiguous accepted length, descriptor and
compiler lineage, timestamp and `base_generation + 1` checks remain. Stable
image, read-tail and execution predicates are unchanged. The source still has
one logical current JIT per root, cumulative frozen-history builds, exact batch
ACK/base-generation publication, pending-image eligibility and exact handback.

The v22 chain explicitly remains a **source-derived summary and payload
association**. The producer does not capture the full kernel batch rows or a
kernel ACK receipt. Matching summaries do not independently prove exact record
membership, every ACKed tuple, complete cumulative-history union or a loaded
kernel-image digest. The added evidence fields explicitly mark those stronger
claims unproved. Overflow events are retained without silently imposing a new
lifetime-zero qualification rule or claiming complete learning. Stronger batch
membership evidence would require a separate producer-artifact extension.

The [daemon guide](../../../../../daemon/README.md#finite-abi2-learning-batches)
describes the current control and evidence boundaries.

## Independent munmap g9 return relationship

[g9-source-review.json](g9-source-review.json) binds the saved assembly and
CALL/IJ histories to their exact SHA256 values. The saved assembly remains
`9aace9c217ee56de59a4e8a9434cc457266f34880717c2905525a975d2ec7d19`.
The pre-correction return-analysis source hash matches the earlier retained
report; no old module pointer was transplanted into a new session.

The retained static path is:

1. CALL at `0xffffffff814f4913` creates caller word `0xffffffff814f4918`.
2. The thunk at `0xffffffffc0000f26` ends in `JMP RDX`; learned key
   `0xffffffffc0000f28` selects already decoded `0xffffffffc0e32980`.
3. The callback's inner CALL has its own continuation
   `0xffffffffc0e3298e`, then the callback reaches shared RET
   `0xffffffff82704e20`.
4. The saved dispatch at `0xffffffff82704e21` lacks the outer caller word.
   If reached, the existing retained miss would occur after the RET pop.

The smallest causal relationship is CALL to a thunk, then a learned indirect
JMP to a decoded RET. The old analysis followed only decoded `block.bto`
successors, so the learned JMP never propagated that caller continuation.
The regression additionally includes an inner CALL and shared RET to verify
that the two CALL words remain distinct.

The correction follows only exact-source learned **indirect JMP** targets that
are already decoded and remain after terminal filtering. It does not follow
indirect CALL or RET dispatch targets, decode additional bodies, read more text,
increase CALL depth or enlarge CFG/work bounds. Each new traversed edge uses
the existing return-analysis budget; refusal still leaves history unchanged.
The original CALL/RET lowering, ownership, lifetime and admission rules remain.

The small decoded graph cases cover duplicate/cyclic, absent, undecoded and
terminal targets, CALL/RET exclusion, inner continuations and atomic budget
refusal. The existing generated-code fixture now supplies only JMP history,
derives the RET continuation and checks the callback result, CALL-word stack
position and flags. It no longer seeds the RET edge whose derivation it tests.
These fixtures executed in the VM; the read-only reviewer's JSON correctly
records that the reviewer itself performed no execution.

This corrects the source-analysis relationship and its miniature regression.
It does not establish that saved g9 reached this path, that the missing target
was reported at runtime, that a corrected full g9 image was generated/executed,
or that complete balanced-stack/flags/SIMD behavior is proved. Batching does not
fix this relationship, and one invocation still stops discovering at its first
permanent handback.

## Final selected checks

All compilation/execution used the pinned Python in a new isolated ext4 copy
on the designated VM's existing normal `7.0.0-38-kdlock1` boot
`6148a091-cca7-4258-8d0b-d75227134564`. Strict daemon/basic builds use
`-Wall -Wextra -Werror`; all pass without build warnings.

| Python driver | Final result |
| --- | --- |
| `execution/test_exe_registry.py` | 36,543 checks at the default 64-image pool; 70,972 at the fixture-only 128-image setting; 16 mutations detected |
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

The previous 130 compiler tests were rerun in this final snapshot. Their four
drivers now total 131 because of the new return-graph method. The remaining
unittest drivers bring the total to 235; production C check counts are reported
separately. Both v21/v22 mock association and real-recorder fixture paths pass.
The 128-image variant is a userspace fixture, not a changed provider default.

The initial complete fifteen-driver run also passed. Two positive capability
subcases were added to one test file after that initial freeze, so the entire
selected set was rerun from the final snapshot rather than treating the added
cases as executed. Both receipts remain separate. There were no unsuccessful
executions in this phase; prior failures and the interrupted preflight remain
unchanged in the [batch implementation record](../learning-batches-b9a31a06-20261108/README.md).

## Preserved receipts and remaining limits

The initial isolated copy is
`/mnt/kdlock-builds2/kdlock-batch-checks-t2y9blsb`; the final copy is
`/mnt/kdlock-builds2/kdlock-batch-checks-g0kt2nlt`. Their source states, manifests,
patches, exact commands, logs, statuses and final idle checks are preserved.
[source-verification.json](source-verification.json) verifies all 1,093 final
source files against the committed implementation and lists the sole test-file
change between runs. Compact source-receipt indexes bind complete original
source-state records in the raw archives by SHA256.

Initial/final checks confirmed the same normal boot, no project module/task,
unchanged tested source bytes and original manifest/state identities. Original
source-file hashes were checked; historical contents under `bench/results`,
`results` and `kernel_baseline/experiments` were explicitly excluded from content
rehashing, with their declared hashes retained. Those historical contents are
not described as freshly hash-verified. No frozen/canonical source, existing
evidence, recovery state or unrelated work was edited or cleaned.

Raw archives are under
`bench/results/10.176.26.71/raw/tests/v22-return-b429ea7a-20261108/`;
[artifact-verification.json](artifact-verification.json) records sizes/hashes.
The full suite and provider build were not selected in this phase. All 138
provider/header source files match the prior passing provider-build snapshot;
its compiler-identity diagnostic and ten objtool return/stack warnings remain
documented in the earlier record, not resolved here.

The separately stopped live action remains excluded. No guest boot/configuration
change, provider load, live image publication, mmap1/application/benchmark/
campaign or learning/measurement launch occurred, and no review controls were
changed. No current kernel-execution or throughput claim follows from these
source changes, builds, supplied primitives or userspace generated-code tests.
