# Kernel proxy functional milestones, October 30

The bounded marker, spin-context and Native CALL probes passed their completed
VM attempts. Reaching an instruction marker or the tested Native CALL finishes
that invocation on its original task while later cold requests continue to
return from JIT. These results establish functional mechanisms, not arbitrary
Linux lock replacement, general native-to-JIT re-entry, real syscall integration
acceptance or a performance improvement.

The [independent verification](verification.json) checks seven live sessions
(39 phases), four basic functional sessions, exact counter/effect arithmetic,
source retirement and receipt hashes. Failed attempts remain in the same receipt
collection and in the table below. Each source generation is reported separately;
this is not a claim that a full suite ran against the final probe commit.

## Identity and evidence scope

All reported live sessions used `7.0.0-38-kdlock1`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`, running Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, the authenticated schema-2 source/output
bundle and snapshot `linux70-kdlock1-clean-20261027`. The recorded preemption
policy was `lazy`. Workers were pinned to CPUs `0–15`; these probes do not cover
oversubscription or cross-NUMA execution. Translation uses the maintained
trusted-source policy. The checked analyzer remains separate regression evidence.

The receipt-only archive is in the **main checkout**, not this worktree:

```
/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/receipts.tar.gz
```

[Archive identity](receipt-archive.json) records SHA256
`1e78b352ca3a745bf15ff73e09769244b451e4d61ba976d3403ade0099aa949e`.
It contains 1,921 closed small receipts/logs, 3,288,418 uncompressed bytes,
fetched read-only from `/root/kdlock-evidence/10.176.26.71/tests`. Remote stable-file
reads and local bytes were checked against the [SHA manifest](fetch-verification.json).
No source/build tree, ELF or running preparation directory was archived here.
The larger source/binary archives are a separate evidence step.

The verifier compared 13 source manifests with their declared Git commits:
1,440 distinct **tracked** blobs matched. The manifests also contain six
historical untracked leaves (`include/kd_rwsem_direct.h`,
`kernel_module/kd_rwlock.c`, and `kernel_module/mutex/{custody,pin_diag,pin_origin,pin_window}.inc`)
and, in two basic snapshots, `.build/provider` copies. They remain recorded and
are explicitly excluded from Git authentication. This report does not infer
compiler dependency identity for those leaves. Recorded binary hashes and
live image-hash checks are retained, but this receipt audit does not independently
rehash the absent ELF/image bytes.

Reproduce the offline audit without executing any captured code:

```
python3 bench/results/10.176.26.71/tests/kernel-proxy-functional-20261030/verify_receipts.py \
  --archive /home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/receipts.tar.gz \
  --repo /path/to/kdlock
```

The verifier extracts only regular receipt files into a temporary directory,
checks every SHA, reads Git blobs, and checks JSON/log evidence. It does not build,
load a module, import captured Python, run a unit test or access the VM.

## Instruction markers and faithful lowering

Source `264725969cbafd909bd20a051cc51b2575b30cfd` passed actual decoded-byte and
execution checks for PAUSE, fences and LOCK overlap ordering after the failures
listed below. Its marker probe then passed all four lock families. Each session
ran warmup followed by **cold → taken → cold → taken**. The two cold columns
below are returned JIT bodies; the taken columns are exact JIT-entry/marker
counts with **zero returned JIT completions**. They are counts, not throughput.

| Family / entry ABI | Cold returned | Taken native | Cold after returned | Taken again native |
| --- | ---: | ---: | ---: | ---: |
| mutex / 2 | 30,862 | 6,192 | 29,030 | 6,011 |
| spin / 1 | 27,886 | 29,253 | 29,444 | 26,890 |
| rwlock / 3 | 3,118 | 3,459 | 5,259 | 1,706 |
| rwsem / 2 | 17,365 | 10,054 | 13,217 | 10,995 |

Mutex/spin performed 32,000 writer operations per non-warmup phase. Rwlock/rwsem
performed 30,000 writes plus 10,000,000 local reads per phase. Warmup was 100,000
acquisitions per writer. Every worker completed its requested operations with
zero errors; prefix, suffix and taken effects were exact. The runner verified
unchanged NORMAL registry, generation 1, code address and image-file hashes after
each phase. Sampled logs bind the marker entry/RIP/generation to an original
writer PID and `action=native_suffix_keep_eligible`; rate-limited event samples
are not used as the total counter denominator.

Every session ended at source state 2 with modules/frames/writers all zero.
The recorded runner's stale final text line in `tests/kernel/jit_escape/run.py` says “permanent
native-only state”; the phase and publication assertions demonstrate the opposite
for these supported reached markers. That text is not used as evidence.

## Spin context

Source `25aa81bba99b12c9c0e33a8e4db83c144cccdc29` passed the ordinary public
spin-context probe. Each non-warmup phase performed 32,768 operations. Returned
JIT counts were IF-on **19,627**, IF-off **19,623**, mixed-IF stress **8,372**, and
final IF-on **18,633**. BH-disabled, preexisting RCU, preemption-disabled and
migration-disabled phases each returned **zero JIT bodies** and completed locally.
All operation/state checks passed, with exact preemption, IRQ and migration
restoration and final source retirement.

This ordinary ABI1 image has generation **0** and requirements **0**; it is not
mislabelled as an immutable marker image. The live mixed-IF phase explicitly
records `mismatch_refusal_proved=false`: it provides stress evidence, not a
forced mismatched origin/executor pair. The directly affected production-helper
unit fixture supplies the deterministic admission/refusal checks. This probe
also does not certify arbitrary inline context-changing instructions or all
Native callees inside a delegated interval.

## Native CALL continuation

Source `3a0f3c25f237a1a980b3b80ee0bf48f54f10e510` passed separate direct and fixed
register-indirect CALL probes. Both use an ordinary public ABI2 KD mutex root;
the taken branch invokes the real Native `_raw_spin_trylock` on an untouched
Native object, then completes its native suffix. The source CALL-site audit
checks the emitted direct/indirect instruction and return continuation.
Capability version 12 advertises optional bit 12; old providers do not silently
receive the new indirect-CALL exit contract.

Each session used 200,000 warmup iterations per worker and 100,000 per worker in
each following phase: **1,600,000 operations per phase**. The counts are:

| CALL mode | Cold returned | Taken native | Cold after returned | Taken again native | Final native started/completed/unlock ACK |
| --- | ---: | ---: | ---: | ---: | ---: |
| direct | 1,592,679 | 422,713 | 1,591,658 | 424,042 | 846,755 / 846,755 / 846,755 |
| indirect | 1,592,236 | 402,330 | 1,589,572 | 404,875 | 807,205 / 807,205 / 807,205 |

Cold phases have equal positive entry/completion counts and no native CALLs.
Taken phases have equal JIT-entry, validated-CALL, native-start, completion and
unlock counts, with zero returned JIT completions and zero instruction-marker
exits. Twenty sampled events per mode bind the exact entry, Native target,
CALL return PC, stack, outer lock and original task; event samples are not totals.
The payload checks original `current`, CPU AUX, stable non-PICKUP physical owner,
exact effects, and preempt/IRQ/migration restoration. The Native spin lock is
released before the outer mutex. All callers joined, both immutable images
remained NORMAL with unchanged generation/address/hash, and all source references
retired: state 2, modules 0, frames 0, writers 0.

These runs prove a **borrowed outer physical owner**, not an owner role swap.
They do not demonstrate arbitrary native-to-JIT return on the same invocation,
unknown indirect RET/JMP recovery, every terminal API, every CALL operand form,
or CALL continuation for all four lock families. The fixed indirect target is a
permanent terminal API and remains unlearned; broader unknown-call learning is
covered by focused unit contracts, not this live target. The probe's private
observation overlay counts already-validated CALL exits and exposes read-only
native totals; its prepared-source and binary manifests are retained. It is an
unscored mechanism probe, not a real-world syscall benchmark.

## Basic functional checks and retained attempts

At `0ef4e92bea5db63b9201c3dd24310cbd6929d928`, all four basic functional sessions
completed 1,600,000 operations with correct data, zero worker errors, returned
JIT and full retirement. Returned counts were spin `c01` DIRECT **1,596,587**,
mutex `c01` public **1,589,665**, rwlock `c01` write 20%/post 4 **25,618**, and
rwsem `c16` write 100%/post 4 **1,589,756**. Rwlock operations include local reads.
`performance_accepted=false` and `timing_started=false`; elapsed fields in these
functional receipts are not a nano score.

The following totals count unit **drivers**, including the two basic C drivers,
not a sum of all nested cases. Passes from different versions are not pooled.
Every failed directory and owner receipt remains in the archive.

| Attempt directory under `tests/` | Source | Outcome / reason |
| --- | --- | --- |
| `kernel-proxy-marker-unit-20261030` | `b8fda6af5d4169e69e10b09133fabf0b1af2d645` | 9 pass / 1 fail: LOCK postprocessor `after_addr` unbound. |
| `kernel-proxy-ordering-unit-20261030` | `627b47e8292ff08eb346dd913778fe3c3a0dd7f2` | 9 / 1: generated overlapping LOCK continuation produced wrong effects in checked and trusted modes. |
| `kernel-proxy-ordering-r3-unit-20261030` | `264725969cbafd909bd20a051cc51b2575b30cfd` | 3 / 0; decoded `c_next` fix; W=1 provider build. Four-family marker live followed at this source. |
| `kernel-proxy-context-unit-20261030` | `4fc02b01acab36e2cdc31b832e59fe1268dd66d8` | 5 / 2: split helper declaration missing from two extraction fixtures. |
| `kernel-proxy-context-r2-unit-20261030` | `ada764f076454d01f134d93e6b728b1acb842754` | 3 / 1: synthetic nested queue nodes lacked continuation records; fixture SIGSEGV. |
| `kernel-proxy-context-r3-unit-20261030` | `99efd26e8cc6627f00509fd68635f04b283a6a56` | 3 / 0; W=1 provider and mmap identity payload compilation. |
| `kernel-proxy-context-live-20261030` | `f40a17c8e69ce9ac5017a6d8c3583d4da39014ba` | 3 / 0 units; live preparation incorrectly required marker image capabilities. Normal cleanup reached state 2/all references zero. |
| `kernel-proxy-context-live-r2-20261030` | `25aa81bba99b12c9c0e33a8e4db83c144cccdc29` | 3 / 0; nine live context phases passed. |
| `kernel-proxy-calls-unit-20261030` | `d20afbefb7491b592f0b51547fa1b6dfea3a0dc4` | 13 / 1: bridge driver could not import `test_kernel_api_binding`; other CALL/source/alias contracts passed. |
| `kernel-proxy-calls-r2-unit-20261030` | `1495f5509752d2424bbc99c6dcea92649db97ba4` | 3 / 0 after import registration; W=1 provider build. |
| `kernel-proxy-profile-unit-20261030` | `0ef4e92bea5db63b9201c3dd24310cbd6929d928` | 6 / 0, plus 7 standalone MM-platform tests and Werror client compilation. These are not live MM execution. |
| `kernel-proxy-native-call-live-20261030` | `e9ad910c45661170710aaf3051034a70a2700860` | 5 / 0; direct live stopped before load: missing annotation separator emitted `.popsectioncall`. |
| `kernel-proxy-native-call-live-r2-20261030` | `3a0f3c25f237a1a980b3b80ee0bf48f54f10e510` | 3 / 0 (including 7 API-object runner cases); both syscall clients compiled with Werror; both Native CALL live sessions passed after annotation newline fix. |

The CALL unit slice includes exact source/stack/actual-CALL validation, optional
capability refusal, learned-entry closure, ordinary callee behavior, exact root
alias routing and binding/bridge lifetimes. Missing dependencies/imports and
compilation failures above are failures, not skips or passes. The passing syscall
client builds/runner units do **not** mean the selected bound setfd/pipe kernel
objects have passed actual-syscall execution on a newly integrated kernel.

## Remaining gates

The original `acfa33a5` semantic audit remains historical evidence with the
new milestones appended in `docs/design/kernel_cs_semantics.md`. Whole-object
integration, changed-kernel execution, real syscall semantics, unchanged mmap1,
full mitigation coverage, unsupported configurations, and the requested matched
performance/no-regression gates remain distinct requirements. No earlier
regressed optimization is promoted by these functional results.

The [killable mmap writer polling review](mmap-killable-poll-plan.md) is a
**source-only proposal**. No polling optimization was implemented or measured by
this campaign. It requires condition-before-signal cancellation, exact reader
drain and downgrade behavior, original-task execution, and a fresh matched
Native/KD comparison before any performance claim.

## Later full-archive verification milestone

The earlier receipt-only audit above remains unchanged. A subsequent read-only
capture now retains the full closed source/build/ELF evidence for 16 attempt
directories, including `kernel-proxy-profiles-r2-unit-20261030`. The archive and
its capture metadata are in the main checkout's ignored raw directory:

```
bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/full-evidence.tar.gz
bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/full-result.json
bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/full-input-inventory.json
bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030/full-controller.py
```

The archive is **79,815,057 bytes**, SHA256
`11d1aa58597f7aa08bdb7643190a5e21d83c53b3f4679a53a211ef32c7067f0c`.
The inventory SHA256 is
`783a08938732e255b964557a5fddd88809ff20eced85f9f8aa263f9d7032cad5`.
The [independent full-archive verification](full-archive-verification.json)
checked the exact **9,497 inventoried paths**: 8,551 regular files, 922 directories
and 24 symlinks, plus the 16 root-directory tar headers. Types, permissions,
UID/GID, regular-file sizes, archive-representable mtimes and symlink targets
match. Device/inode/ctime/link-count and sub-floating-point mtime precision
remain capture-inventory facts; tar does not independently reproduce them.
The controller records unchanged pre/post inventory and boot identity. All
**1,921 earlier receipt files are byte-identical** in the full archive.

Rehashing the actual archived bytes produced:

| Evidence | Matching hash references | Distinct retained files |
| --- | ---: | ---: |
| Original source manifests | 3,444 | 3,444 |
| Final prepared-source manifests | 870 | 870 |
| Binary manifests, including provider/payload ELFs | 50 | 50 |
| Recorded image publications (`jit.bin`, `jit.S`, `bin.txt`) | 54 | 36 |
| Maintained provider-preparation manifests, direct matches | 1,870 | 1,870 |

There are no missing or unexplained mismatched references. Six additional
provider-preparation references describe the **earlier layer** of the two files
modified by the Native CALL probe's recorded observation patch, across its three
attempt directories. The verifier reverses those exact textual hunks as data,
checks their context/counts and reproduces all six original hashes. Successful
live attempts also have matching final prepared-source manifests. The detailed
base/final/patch hashes are retained; the probe is not relabelled an unmodified
provider. Some references in the table overlap between manifest families, so
the columns are not additive counts of independent artifacts.

This closes the earlier absence of archived ELF/image bytes for these manifest
checks. It does not make historical untracked source leaves compiler inputs,
prove every runtime instruction or mitigation path, or turn a NORMAL image from
failed preparation into returned-JIT evidence. Functional acceptance still comes
from the phase/counter/effect/retirement checks recorded above.

The newly included `kernel-proxy-profiles-r2-unit-20261030` belongs to
`8446f4ecb08816380a4c233197a8ce5e4d333aac`: **4 unit drivers passed** (basic two plus
provider admission and kernel-profile drivers), with **9 basic-runner cases** and
**12 nano-runner cases** in separate commands. Its W=1 default-off provider build
passed. The expected negative daemon launch messages are not failed test cases.
These are provider/runner checks and compilation; they add no new syscall/MM live
execution, kernel boot or performance result.

Reproduce this independent offline check:

```
python3 bench/results/10.176.26.71/tests/kernel-proxy-functional-20261030/verify_full_archive.py \
  --raw /home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/kernel-proxy-functional-20261030
```

The verifier streams archive members as data, never follows archived symlinks,
and never imports or executes captured scripts, tests, modules or binaries.
