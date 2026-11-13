# Rwsem read eligibility after native progress

This source candidate rechecks an initially ineligible ordinary rwsem read
after the existing native progress pass. It changes only the entry decision
in `kernel/mutex_api.c`; owner/grant retirement, the reader gate and writer
implementation retain their current code. Compilation, runtime behavior and
performance require new bench receipts.

## Evidence and exact transition

The preserved kernel12 receipts use core `7504893e`, harness `54437fd2`, boot
`678395e4-f4f1-4567-9551-841a7b836dd7` and Build ID
`13cdf607461f84e7dd731df38eb7f8cf22d735f0`. The source session verified archive
`/tmp/kdlock-rwsem-read-continue-7504893e-20261112-01/guest-receipts.tar.gz`,
SHA256 `2e94593d4abde8b4c64e01267be2a56d10a188aedc20816a041608a3f724b743`.
Its `functional-rwsem-kdlock/functional-on.json` reports 256 operations,
205 physical read pairs, 51 writes, 154 fast-read pairs, 102 reserved/freed
requests and zero recorder errors. The corrected `audit.json` and original
`audit-attempt1.json` remain preserved. The audit reports median whole-workload
KD-off 615475.6666 ops/s and same-boot Native 1912925.4786 ops/s. These are
exploratory sequential-block measurements; timed fast-path counts are unavailable.

The source exposes this ordering:

1. `kd_episode_unlock_native()` closes the logical grant, pumps actual-owner
   duties, then calls `kd_episode_collect()` before finishing its control user.
2. During that pump, `reap_ready_locked()` refuses an obligation whose
   `release.source_user` still exists. Physical release alone is insufficient.
3. The subsequent collection unlinks the now-closed, physically released grant.
   `kd_state_unlink_grant()` calls `drop_grant()` and
   `kd_mutex_grant_unlinked()`, which drops that exact source user and wakes
   its owner. This does not itself unlink the owner batch from its progress list.
4. The following native read first checks `native_fast_eligible()`. A retained
   `root->owners.batches` membership rejects the shortcut. Its normal
   `kd_task_progress_native()` then runs exact owner progress, collection and
   another owner pass, which can finally reap that batch.
5. The previous wrapper continued straight to root-frame preparation after
   this cleanup, without reconsidering reader eligibility.

This identifies a concrete missed entry opportunity. The 51 ordinary reads
matching 51 writes is consistent with it, but the nano recorder does not log
every eligibility predicate; those counts alone do not establish per-operation
causation or the time spent in this path.

## Change and lifetime reasoning

Cache only the initial eligibility boolean. After the unchanged progress call
returns successfully, recheck only RWSEM_DOWN_READ that was initially
ineligible. Require the complete original eligibility predicate and native
validation again, then use the same guarded reader admission. Do not retry a
physical admission that already failed on an initially eligible invocation.

No old node, frame, grant or owner pointer is retained across progress. A live
batch or logical/native grant still prevents entry, including deferred release,
nesting and downgrade duties. A pending pool record alone remains legitimate
when it holds the current native endpoint; the change neither reuses it nor
requires the whole pool to empty. The reader still refuses a writer, pending
writer or observed queue tail under the family guard. Failed admission changes
no source operation and continues through the original persistent path.

The existing final-access-before-reuse, cancellation, physical ACK, grant drop
and retirement code is unchanged. No source effects are replayed or moved to a
different task. Writer admission, fairness and downgrade rules are unchanged.

## What ordinary writers prepare

The existing writer path pays native progress/collection, reserves a persistent
request, initializes its frame and retains control/image/grant/auxiliary users
before acquisition. It looks up an image and prepares the node/driver and
execution bindings, validates the source/auxiliary stack descriptor, switches
to the auxiliary stack, and captures the current GS plus declared SP/IP/BP/DI
inputs before entering `kd_jit_acquire()` and the ordinary rwsem writer gate.
These prepare delegation and exact continuation even when a writer ultimately
executes locally. This is a source inventory, not a measured cost breakdown.
This candidate removes an avoidable reader preparation after that writer;
it does not introduce a different writer ownership record.

## Focused bench handoff

Preserve kernel12 and all older source/build/raw receipts and frozen inputs.
This is a built-in source change and needs a separate kernel release/build/boot
and matching modules; object and task-root layouts and evidence ABI3 do not
change. Keep the established recovery, idle, disk, exact ELF/config/Build ID,
GS/ITS, source/module identity and ordinary drain requirements.

The fast-owner runner adds one case, `read_recheck`, extracting the actual
`prepare_current()` and operation predicates with controlled progress/gate
endpoints. It covers completed owner cleanup without frame/capture preparation,
retained owner or logical-grant refusal, no second attempt after an initial
physical miss, post-progress physical refusal, and unchanged writer entry.
The progress stand-in deliberately reports pending storage even after duty
cleanup. This case is not a kernel retirement or scheduler proof.

Run the eight affected fast-owner cases, five existing reader gate/release
cases and twelve recorder/ABI cases: 25 focused units. Keep the existing mutex,
rwsem reader/mode and managed-killable live fixtures. Reuse the unchanged harness
and identity checks once passed; no new full suite or workload is requested.

Use the reviewed `native-current` scope from `54437fd2` on the new candidate
boot with four matching functional receipts and twelve two-second timings,
retaining the current workload and instrumentation settings. Use the candidate
kernel release and fresh GS/ITS proof explicitly; the original harness guide's
kernel11 example is historical. Report actual fast-read and reservation counts
from recorded functional phases without strengthening the general accounting
contract to require all reads fast. Compare same-boot Native and the separate
kernel12/prior-KD receipts, keeping whole-workload and selected peak results
and source/build/boot boundaries explicit. No performance improvement is
claimed for this recheck until those measurements exist.
