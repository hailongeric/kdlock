# Checked instruction exits, 2026-10-18

**PASS for the final focused checks.** This change preserves the accepted KD
mutex lock protocol and rwsem waiting implementation. It adds a checked way to
stop delegated machine code before a reviewed processor instruction, resume the
original waiter there, and disable future delegation of that critical-section
entry. JIT means just-in-time compiled code; the
[terminology guide](../../../../../docs/TERMINOLOGY.md) explains the execution,
ownership and measurement terms used here.

The [instruction policy](../../../../../docs/design/admission.md#checked-instruction-exits)
lists twelve exact instruction encodings. Full source admission still applies;
unknown instructions, unsupported processor state and unproven register inputs
remain refused. This is not an arbitrary-fault recovery mechanism. The
[register contract](../../../../../docs/JIT_REGISTER_ABI.md#checked-instruction-exit)
describes capability version 6, original instruction/state restoration, immutable
images and the unchanged owner/unlock-acknowledgement protocol.
The [source comparison](lock-protocol-source.json) checks the selected mutex
owner/queue/caller files against `d2a2304` and the rwsem waiting files against
`c21345b`. Shared translation, publication and continuation files intentionally
change; the whole runtime is not claimed byte-identical to those commits.

## Final selected-source checks

All builds and execution ran in the recovery VM on `10.176.26.71`, with 64 virtual
CPUs. Source edits and the independent archive review ran on `380G10`. The kernel
remained `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot identity
`b65f0205-c8f9-4385-8b13-039cbce243a6`. The existing recovery snapshot
`before-mutex-kdonly-20261017T140354Z` was confirmed through the VM monitor.
No kernel rebuild, installation, reboot or forced unload occurred.

| Check | Final outcome |
| --- | --- |
| Basic and affected unit programs, attempt `units-03` | Both basic C programs and 17 selected Python drivers passed; no skips. This is not a full suite. |
| Generated instruction markers | Reviewed opcodes, exact original address, cold/taken branches, arithmetic flags, retained static refusals and ordinary-image compatibility passed. |
| Production register restoration | All general-purpose registers, stack position, packet/canary integrity and all 64 arithmetic-flag combinations passed both with and without the configured return-thunk path. A return thunk is the kernel-selected return sequence used for processor mitigations. |
| Image and execution lifecycle | Publication/disable ordering, retained older images, invalid markers, source references, native-return tags and existing execution-resource checks passed. |
| Provider, workload and daemon builds | Completed; provider uses `W=1`, undefined-behavior instrumentation disabled, and the existing benchmark observation overlay. Daemon uses `-Wall -Wextra -Werror`. Warnings remain recorded below. |
| Live marker probe, attempt `live-03` | All four phases passed with exact updates, original-task identity, flags, exclusion and full retirement. |
| Ordinary rwsem controls, attempt `rwsem-02` | c08 and RCUHT passed at 16 workers and 80% writes, with positive matching delegated entry/completion counts and full retirement. |

The live marker probe uses workers on CPUs 0–15, 100,000 operations per worker
per phase. It changes the branch condition only after every earlier caller has
finished. Its safe special instruction is `RDTSC`, which reads the processor
timestamp counter. The source comparison sets six arithmetic flags before an
unconditional branch; the native remainder checks all six after the timestamp
read. It also checks the actual task identity and updates before/after the exit.

| Phase | Operations | JIT entries | Completed JIT bodies | Instruction exits |
| --- | ---: | ---: | ---: | ---: |
| Cold warmup | 1,600,000 | 1,130,210 | 1,130,210 | 0 |
| Cold delegated check | 1,600,000 | 1,479,585 | 1,479,585 | 0 |
| Taken special branch | 1,600,000 | 1 | 0 | 1 |
| After disable and drain | 1,600,000 | 0 | 0 | 0 |

All 6,400,000 operations finished exactly once. The single exit event identifies
the original RDTSC address, the bound code-image version and an actual worker
process. Its remainder finished on that waiter, so it is correctly **not** counted
as a completed JIT body. After the disable, the registry remained `NATIVE_ONLY`,
meaning delegation was forbidden for the rest of the source session. The final
phase independently verifies zero new generated-code entries.

The rwsem controls each used 200,000 operations per worker on CPUs 0–15, with
collector CPU 63. Each measured phase completed 640,000 reads and 2,560,000 writes.
c08 returned **860,947** delegated writer bodies; RCUHT returned **224,329**.
Their separate warmups, protected-data checks, worker progress and ownership
retirement also passed. These are correctness controls, not throughput scores.
The accepted `c21345b` timed comparison is unchanged and remains
[separate evidence](../../bench/rwsem-optimization-20261018/README.md).

## Retained failures and intermediate evidence

- `units-01`: the pinned decoder misidentified exact RDTSCP bytes as `INVLPG ECX`.
  Admission refused them. A narrowly checked decoder correction was added.
  The new C restoration fixture was also missing from the first synchronized
  snapshot; that test did not run and is not counted as passed.
- `live-01`: code publication succeeded and local updates were correct, but both
  cold phases had zero JIT entries. Python worker names did not match the
  provider's eligibility name. The runner now sets and checks `ke_worker` on
  both sides. The original attempt remains a drained `NO_JIT` failure.
- `units-02`, `live-02` and `rwsem-01` passed their selected checks before the
  final return-thunk correction. Their counts are retained separately in the
  [preliminary review](preliminary-review.md); they are not pooled with final
  selected-source evidence.

The intermediate marker restore used a direct return despite the kernel's
`CONFIG_RETHUNK` setting. Review of the captured kernel return sequences found
that the configured helper preserves arithmetic flags. The final helper uses
that configured sequence; the final live and unit checks were repeated.

## Evidence and limits

[Final independent review](final-review.md) checks archive hashes, frozen source,
prepared provider inputs, binary/image hashes, exact phase results and final
retirement. [Its JSON record](final-review.json) contains detailed checks and
source comparisons. The [preliminary review](preliminary-review.json) preserves
earlier failures and intermediate successes. Unit-generated temporary programs
have no separate executable-hash manifest; their source, commands and logs are
retained, and the basic executable files are present in the raw archives.

Raw archives remain under
`bench/results/10.176.26.71/raw/tests/native-instruction-exit-20261018/`, with final
attempts under `final/`. Guest originals remain at `/mnt/kdlock-builds/` under the
recorded run names. `archives.json` and `final-archives.json` identify their exact
hashes. The archive helpers, unit drivers, snapshot confirmation and final health
record are retained alongside this report.

Builds still report existing macro-redefinition, locale and custom-stack/return
analysis warnings. The probe's deliberately prepared entry also produces
unreachable-entry and instruction-address warnings from the kernel's `objtool`
assembly checker. Warnings were not suppressed. The new helper's bare-return
warning is absent from final builds; custom-stack analysis remains limited.
No matched runtime kernel fault occurred in these sessions.

Only RDTSC and one arithmetic-flag pattern were exercised by the live marker
probe. Other reviewed instruction families have admission/runtime fixture
coverage, not live execution coverage. The userspace restore fixture separately
covers all 64 flag combinations. Arbitrary runtime-pointer checks, whole-kernel
replacement, realtime/wound-wait mutex integration, general processor-state
restoration and spin/rwlock instruction markers remain outside this change.
The final checks establish correctness for these inputs; they do not establish
performance parity or a new standard-grid benchmark result.
