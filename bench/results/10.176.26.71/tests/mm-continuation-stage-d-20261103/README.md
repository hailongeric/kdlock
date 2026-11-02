# General MM continuation: Stage (d) evidence

This isolated work continues from Stage (c) on
`codex/unified-lock-queue-mm`. The maintained `master` is unchanged. The goal
is unchanged mmap1 system calls with delegated writer and downgraded read
intervals. The evidence below proves returning primitives, not actual MM
delegation or throughput. Later untested source changes are not covered by
these receipts.

The returning and instruction checks below ran in VM `10.176.26.71`, kernel
`7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`b4c42511-d2fd-4ac7-b6b5-48650aae48b7`. Source editing and receipt analysis
ran on `380G10`. The recovery snapshot `kdlock-builddisk-clean-20261031`,
idle state, CPU placement and fixed frequency were verified before live work.
The ordinary kernel has its MM backend disabled. No mmap1 score is implied.

## Returning primitive checks

| Attempt | Exact source | Outcome |
| --- | --- | --- |
| First | `bb5f0770f657551e45567f6ec9e7abf83216f833` | Returning-call code generation, three selected capability checks, production source-lifetime checks with negative controls, and generated MM dependency checks pass. Helper observation import fails; provider assembly lacks the include path. No live module starts. Both failures are retained. |
| Second | `e33dce192fae7bf998c5babffba161b39df8459f` | Corrected helper parser checks and provider build pass. Both live returning-helper phases pass, drain, retire and unload normally. Build logs retain existing objtool warnings. |

The scalar phase has origin PID `49929` and executor PID `49907`; the sleeping
child phase has origin PID `49930` and executor PID `49882`. In each phase,
the actual Native helper runs on the origin's real kernel task stack, observes
all six distinct word arguments, returns AX `0x993f730e40218045`, and the same
executor/image resumes once at the exact source CALL successor. Source CALL
words and image/request generations are joined in the trace.

The sleeping phase records three context switches and six jiffies inside the
origin primitive, one actual local child acquisition/release, and a fatal
signal after the parent's acquisition committed. The parent still succeeds
and executes its post-helper body once. The later user process signal exit is
separate from the successful lock API result. This is functional evidence;
the six-jiffy interval is not a benchmark measurement.

The immutable image requires value `896` (retained queue, returning CALL and
budget continuation); capabilities are version 14. Both phases finish with
zero errors, zero active users and an idle lock. Full extracted observations
and provenance hashes are in [focused-receipts.json](focused-receipts.json).
Original attempt directories remain at
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/mm-stage-d-first-20261103`
and `mm-stage-d-second-20261103`; local controller receipts are named in that
JSON. These original inputs/results are retained, including failures.

## Subsequent source and kernel work

Commit `58fda6a4` adds exact retained Native spin/RCU records, source-checked
returning primitive declarations, indirect CALL successor handling and four
helper phases. It has not yet run in the VM at the time of this entry. The
new GS instruction service is a further candidate and must obtain separate
build, decoder, context and returned-body evidence.

A distinct `7.0.0-38-kdscope5` tree is being built from frozen commit
`9529b070086c6d5ca7d6465de6cd71e279a1228c`. Its fresh composition, affected
MM/syscall objects and full kernel/modules build pass with `W=1`. The v1
Build ID is `1e29cde775b6cfd7f754b27888f85a8a457be5e1`; it has not been installed
or booted. See [kernel-v1-summary.json](kernel-v1-summary.json). Native MM
bodies are hash-checked unchanged. This is neither boot nor actual MM evidence.
Its asynchronous controller records exact child identities and drain; no
source synchronization occurs while those inputs are in use.

The subsequent instruction attempts remain separate in
[instruction-attempts.json](instruction-attempts.json):

| Attempt | Source | Outcome |
| --- | --- | --- |
| `mm-gs-first` | `a4b64cabde4d96cd5c33417ecbbbda61c6d75300` | Production instruction decoder/metadata cases with three negative controls, helper observation parser, generated MM dependencies and MM benchmark units pass. Indirect CALL scope, missing codegen fixture symbols, a standalone fixture typedef order, and a module-hidden preemption macro fail. No live module starts. |
| `mm-gs-second` | `9fd17324fb9b864c53a5c39e005512f2d705a819` | Provider builds; corrected GS wrapper/flags cases and production source-lifetime checks with negative controls pass. Returning CALL tests pass except the new tail-callee case, which reveals missing eager callee decoding. No live module starts. |

Commit `7b01e6ec` also contains the initial guarded-read frontend joins from
concurrent source work; the remaining read implementation was not yet in that
checkpoint. It was caught before synchronization/execution and remains unrun.
Commit `8bfd1cc2` completes that source slice, including version16 negotiation
and strict live fixture inputs. It is unvalidated at this entry. No result from
an older source is relabeled as a pass for either checkpoint.

The complete v1 kernel tree is preserved on the first build disk. The
7,217,990,632-byte archive has SHA256
`5704299cdc57eef73dc1f80095debdbaf1249d5aa032f45099e1d2fa5a72cc11`;
the offline content check on `380G10` passes for all 209,839 entries.

The general provider v2 completion amendment builds successfully from
`9fd17324fb9b864c53a5c39e005512f2d705a819`. Exactly the provider header and
builtin completion implementation differ from v1; Native MM bodies and
configuration remain unchanged. The new Build ID is
`d3b5cf1b208028495b5fa9be2a3750b0831a2ec3`. See
[kernel-v2-summary.json](kernel-v2-summary.json). Installation is a separate
stage; neither this build nor archive verification proves actual MM execution.

Remaining acceptance requires an installed/identified MM kernel, ready
immutable core-entry images, a fresh provider-bound mm, actual syscall runs of
both `mmap1_threads` and `mmap1_processes`, joined other-task writer/read-tail
and fresh-writer evidence, and separately measured throughput against Native.
No performance gain, Nano acceptance or arbitrary Native API equivalence is
claimed by this report.

## Version16 runtime attempt

Frozen `0fff405c63d51c69858aba18b5ce1c0686a7c238` is tested separately as
`mm-v16-first-20261103`. Provider compilation passes. Returning CALL cases,
mutation instruction cases, production decoder cases and their three negative
controls, source lifetime, observation parsing and selected version16
capability negotiation pass. Four guarded-read code-generation cases fail
because the ordinary GS nonoverlap lowering emits an unencodable expression
with three register contributions. No live module starts. This failure is
retained; it is not a skip or a pass.

Commit `708f2db491b020483635df6d99ea4d3507d5b09f` computes the source offset
before adding the saved GS base, applies address32 truncation at the source
offset, and reserves mapped temporary registers before source mapping. Its
new component cases and live continuation checks remain unrun at this entry.

## Canonical read successor correction

Frozen `c51cee5c97484224258cfa857b175b96069ad2ad` builds successfully. Eight
returning-CALL cases, four mutation-codegen cases, Native scheduling and
nonreturning descriptor/registry checks with negative controls, full-register
restoration in three return configurations, and the explicit execution-session
checks pass. Five of six guarded-read tests pass; the dynamic serviced load
returns `0x45` to its following store instead of `0x80000000`. Live helper and
killable checks are withheld. See [c51-attempt.json](c51-attempt.json).

The ordinary read left its cached virtual-register mapping at the shared
successor; the serviced read imported canonical packet registers. Commit
`8538e634680b5c15536378a03fd0ecb255cf2e0f` flushes ordinary outputs before the
join and checks canonical SP/BP mapping without overwriting a source-written
BP. The original destination/flags assertions remain, extended to simple GS
addressing and a BP destination. This source correction still needs its own
VM result.

## Installed MM kernel, Native mode

The v2 kernel is installed separately. All 6,901 modules stage successfully;
the stripped tree occupies 676,818,267 bytes. The ordinary kernel and permanent
boot default remain unchanged. On `380G10`, the exact 103,174,321-byte initrd
passes the content correspondence check for 1,188 included modules. The first
host extraction fails because its default temporary directory is read-only;
the successful second attempt selects a fresh writable temporary directory.
Both attempts remain retained.

The one-time Native/off boot succeeds with boot ID
`4a5dd23d-a9bf-44b0-85b2-2a6689514b1f`. Schema-2 capture and running verification
pass for `kdscope5-native`, Build ID
`d3b5cf1b208028495b5fa9be2a3750b0831a2ec3`, `kd_mmap=off`, and `full (lazy)`
preemption. This is boot/identity evidence; no delegated MM execution is
claimed. The exact built ELF is copied and hash-verified on `380G10`; its
`__kd_rwsem_sites_start`/`__kd_rwsem_sites_end` interval contains 55 records,
including one entry in `vm_mmap_pgoff` and one in `__vm_munmap`. The host audit
retains equal-bound function aliases rather than assuming unique symbol names.

The latest isolated source adds a tests-only actual-application controller,
complete diagnostic collection and exact session/transaction joins. These
changes do not alter Native MM bodies or the upstream application. Candidate
execution, both application models and performance acceptance remain pending.

## First focused checks on the MM kernel

Frozen `3017c8a5fea6dbc7f16e567e8abb05238bd0f36f` passes all seven guarded-read
codegen/execution cases, including the original failing destination and the
new BP case. The explicit session and delegated-controller site/trace checks
also pass. Its provider compiles against the exact scope5 kernel. The
continuous collector fixture fails before execution because the selected unit
runner does not add the benchmark fixture directory to Python's import path.
No live helper or killable phase starts. The correction makes this fixture load
its sibling explicitly, as the existing benchmark fixtures already do; it
does not change the production collector or lock code.

This attempt uses the Native/off boot above, separately from the prior c51
checks on the ordinary kernel. Its first host preflight fails when a QEMU
auxiliary thread changes during observation; a second complete stable capture
passes before the VM checks start. Both captures and the failed unit receipt
remain retained.

## Focused live continuation and cancellation checks

Frozen `efd10ac8c5471b107145c367ba4401ad9dadfca3` passes the corrected continuous
collector fixture and scope5 provider build. All six helper phases and all
eleven killable/nesting phases pass with normal drain, source retirement and
unload. Each final phase snapshot has zero errors/active requests, empty queues
and an idle lock. See [efd-receipts.json](efd-receipts.json). This is a separate
source/boot result; no failed predecessor receipt is relabeled.

The helper phases cover six-word Native returns, a sleeping child, Native spin
trylock and nine RCU records, final Native release after outer release, ordinary
GS/preemption instructions and final instruction completion. Exact source
instruction, request/image generations, O/E identities, flags, SP and returned
values are joined. The cancellation phases include three queued cancellations,
selected reader-drain cancellation, nested cancellation, mixed and early-release
depth nine, 128 child reuses, and a nondelegable child control.

In `executor-downgrade-and-fresh-writer`, origin `7729` enters, downgrades,
releases its read share and returns on executor `7635`. The same executor then
enters and completes origin `7730`'s new write request on the same lock. The
fixture holds an additional reader and checks that this successor does not
enter until that reader drains. This satisfies the controlled continuation
criterion; it is not mmap1 execution or a throughput result.

The later file-callback and Native inner-writer addition at design commit
`41409fcfc1bc0f2334002834d1e7765484e7f9f8` remains a separate implementation
candidate. Fresh ELF file-backed mappings require those callback contracts;
file VMA insertion retains a Native `mapping->i_mmap_rwsem` write acquisition.
The Native MM bodies stay unchanged. Actual mmap1 thread/process delegation
and performance remain pending until those intervals pass their own checks.

## Native inner-writer checks on KD mode

The same v2 kernel boots and passes schema-2 capture/verification in KD/on mode,
boot `1c78f37f-4501-4a3b-b4be-49fb3167212a`. The generic module factory remains
inactive during the standalone fixtures; this mode alone does not imply MM
delegation.

Source `370e8e7f964e80e6fe4bedc1df0387b9a753b897` passes all six affected unit
drivers and provider compilation. Its first six live helper phases pass. The
new blocked-writer phase fails because its snapshot can observe O blocked
after the preceding log read, before the fixture has collected the root-enter
record. The retained late log has the exact O `4762` / E `4691` entry and two
Native grants with non-LIFO releases. Its 30-second holder deadline then ends
the interval and records one fixture error. The phase remains failed; E
scheduling and final Native release were not accepted in that attempt. Later
inspection verifies zero active requests, empty Native waits and zero frames.
Normal daemon closure, source retirement, exact descriptor unregister and
normal unload follow, retaining the failure counter and original receipt.

Commit `902ee2a0dcd33405f8c568e006735ce43ab18f2d` adds bounded collection of the
exact root-enter record without changing lock code or weakening the Native
blocked/scheduling checks. Its new observation fixture passes; the provider
builds, all eight live helper phases and all eleven killable/nesting phases
pass with normal retirement and unload. See [902-receipts.json](902-receipts.json).

In the blocked Native-writer check, O `7709` schedules in actual Native
down_write (switch count 1 to 2), while E `7672` on CPU `44` increases its
switch count from 8 to 13 and a control task runs on that same CPU. Native
ownership names both exact objects and releases the older acquisition first.
The final-release phase keeps E executing after outer KD release until the
last actual Native up_write ACK. These observations establish those general
protocol transitions; they are not mmap1 or performance measurements.

The unchanged mmap1 binary preparation is revalidated by its complete file
manifest and original revision `75f66e45697e6f5f49c33dd950c4e6b289198f8f`.
The actual-application controller still needs an explicit verified private-root
admission path: the old common MM runner permits only the canonical VM
checkout. No application diagnostic has started at this checkpoint.
