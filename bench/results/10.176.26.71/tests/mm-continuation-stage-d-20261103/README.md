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
fixture holds the delegated tail's retained read credit and checks that this
successor does not enter until that credit is released. This satisfies the controlled continuation
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

## Private source admission and subsequent application attempts

Frozen `6763c3d3c09e9e26ca2a75456d84847303c384e7` passes all nine private-source
admission cases, provider compilation, all eight helper phases and all eleven
killable/nesting phases. These checks use the same schema-2 KD/on kernel and
boot above; both live suites report `passed=true` and `drained=true`. Existing
build warnings remain in the retained log. See [676-receipts.json](676-receipts.json).
The factory remains inactive during the controlled fixtures, so these passes
do not establish delegated MM execution or application performance.

In the controlled downgrade phase, origin `13224` enters, downgrades, releases
its read share and returns on executor `13134`, request generation `7`. The
same executor subsequently serves origin `13225`'s fresh write request,
generation `11`, on the same lock `0xffffffffc0b9d9c0`. The fixture observes
the new writer waiting with admission `-1`, one retained tail read credit and
no successor body prefix before releasing that credit. Final state has zero
errors, active requests, readers and queued requests, and an idle lock.

This corrects the earlier interpretation of an "additional reader": the
observed reader is the delegated tail's own retained read credit. The fixture
does not add an independent reader after that tail returns. It proves the
controlled two-request continuation and this fresh drain condition; it does
not prove implicit reacquisition by the first origin, uninterrupted scheduling,
actual mmap1 execution, or throughput. Original observations remain unchanged.

Three later application attempts at the same frozen source remain failed and
unscored:

| Attempt | Last established boundary | Retained result |
| --- | --- | --- |
| First | Source admission, before controller/module start | Five generated `.pyc` files violate the frozen tree's exact file set. Each is archived by path, size and hash; tracked input bytes are unchanged, and the first failure remains retained. Revalidation observes 6,768 source files and 409,841,591 bytes. |
| Second | `bench.admit`, before module load | `AssertionError('CPU outside caller affinity')`; the module is absent. The failed receipt retains `passed=false`, `accepted=false`, `scored=false` and `drained=false`. |
| Third | Provider/probe build and load, then image preparation | The daemon rejects `CALL RAX` at `0xffffffff81803423` and `0xffffffff817f6fab`. Leased live bytes are `2e 2e 2e ff d0`, an alternatives-generated five-byte register CALL. Preparation stops before factory activation; `rwsem_provider_active=N` and bindings remain `0`. No application model completes. |

The third attempt's original `drained=false` and failed status remain intact.
Its first separate normal-retirement attempt stops while a translator is still
active and leaves it untouched. The next separate attempt sends the daemon its
normal SIGTERM; translator `16243` retains its device lease and completes
without a signal. Source writers then fall from one to zero, with zero modules
and frames; RETIRE reaches state `2`, and the observer/provider unload normally.
That later receipt reports `passed=true`, `drained=true` and
`normal_unload=true` for cleanup only. It does not turn the original application
attempt into a pass or prove delegated MM execution.

Design commits `bcaf6e7cf0820f5673f387e936f691f10422a0f4` and
`d6ded31452695ef3af6373fe7cd8cb00a357fe1a` specify exact alternatives CALL
continuation and the stronger application observation criterion. Source commit
`bc9045bb53845525dcb2e7e3da2c107c93873399` updates the Python/C exact-length
parsers; `8c8d5324b6b53ee9875e9854eda85a267a7f5320` requires positive application
read-tail and subsequent same-executor/object writer observations. Their new VM
checks remain pending at this entry. No earlier receipt is relabeled for these
changes. Actual mmap1 delegation length, critical-section ratio, complete
per-invocation accounting and performance acceptance remain unestablished.


## Exact indirect-CALL correction and next text-cache limit

Candidate `3b018e27df7823ee3c31a315e320fb463d524685` passes all nine private-source
cases and the production C entry fixture (9,177 checks, zero failures), including
all 50 negative controls. Provider compilation, eight helper phases and eleven
killable/nesting phases pass with normal drain, retirement and unload. The
intermediate `8c8d5324b6b53ee9875e9854eda85a267a7f5320`,
`78b492fa0d74ad25f2e4a3dc2d8e08389ab3ba10` and
`291d181d33de5d1c7f4cb6c82e59c63edd9f71ee` attempts retain their fixture-only
compilation/pattern failures; no live phase started in those attempts. Their
production provider builds passed. No failed receipt is reused as a pass.

The actual-application preparation now accepts the patched CALL encoding and
reaches the 256 KiB text-cache bound. The first stopped sites are
`setup_arg_pages` (`0xffffffff818e05bd`) and `vm_brk_flags`
(`0xffffffff817f77e5`), required ELF startup sites among the 55 entries. This
corrects the earlier informal label of the latter as a mmap entry. The audited
application entries are `vm_mmap_pgoff` at `0xffffffff817b6da8` and
`__vm_munmap` at `0xffffffff8181c57b`. Neither unchanged application model has
run in this attempt. The factory remains inactive with zero object bindings.

The cap measures fetched windows, including page-aligned lookahead, rather than
just decoded instructions. The next docs-first design uses compact lookahead
for general retained call closure and preserves cache/pass/image limits and all
mandatory source bytes. Its fit and actual execution remain pending.

The failed application receipt retains `drained=false`. Separate normal daemon
closure lets translator `24655` finish with its source lease, then confirms zero
frames/writers, RETIRE state `2`, and normal observer/provider unload. See
[3b0-receipts.json](3b0-receipts.json). This cleanup is not an application pass.
No actual mmap1 delegation, throughput improvement or performance acceptance is
claimed.

## Compact text closure and the generated-source boundary

Frozen `b6a3db19ab8326d320b21d3e2690a09181f7f952` passes five focused unit
drivers, provider compilation, eight helper phases and eleven killable/nesting
phases on the same scope5 v2 KD/on boot. Both live suites report normal drain;
every final phase has zero errors, active requests, readers and queued requests,
and an idle lock. The text-region driver includes 58 cases.

The subsequent actual-application preparation remains failed. Compact lookahead
reaches 71,552 cached / 35,161 selected decoded bytes for `setup_arg_pages` and
105,968 / 50,936 bytes for `vm_brk_flags`, below the unchanged 256 KiB cache cap.
It then refuses source ranges `0xffffffffc0002330` (1,088 bytes) and
`0xffffffffc0002370` (1,024 bytes) with `ESTALE`. Captured Linux 7 producer
source shows separately allocated ITS instruction pages whose core pointer
inventory is freed during initialization. These addresses are consistent with
that producer; a live owner query is still required to establish ownership.
Executable-address status, matching bytes and discarded init tables cannot
replace that ownership record.

The factory remains inactive with zero object bindings. Neither mmap1 model
starts. The original application result retains `passed=false`, `drained=false`,
`accepted=false` and `scored=false`. Separate normal daemon closure and source
retirement reach state `2` with zero modules, frames and writers; observer and
provider unload normally. This cleanup does not change the failed result.

## Generated-source and returning-tail attempts

The exact source, receipt hashes, unit outcomes and phase summaries are in
[generated-source-attempts.json](generated-source-attempts.json). Original full
logs remain in the referenced source-host and VM evidence directories.

| Attempt | Exact source | Observed outcome |
| --- | --- | --- |
| `mm-eb5-first` | `eb535d5722a165356a7ded2a03d3420fb26e9b03` | Provider module compilation passes. Four of eight unit drivers pass; four fail. No live fixture starts. This does not build or validate the composed-kernel producer. |
| `mm-824-first` | `824f7c15ee55e42e562b3d697e061bb018eee87f` | All six selected unit drivers and provider compilation pass. Helper startup fails at the common runner's version check, before its body; the killable suite does not start. Normal retirement completes. |
| `mm-433-first` | `4336d4373f5d4c00c9a4f5619f9d72b4eef2791e` | Fresh provider compilation, nine helper phases and eleven killable/nesting phases pass and drain. The receipt has `units=[]`; no unit pass is relabeled from `824`. |

The four `eb5` failures are retained individually: the extracted source-range
loop fails compilation because `end` may be uninitialized; the mmap argument
fixture expects a former one-line function signature; returning-call fixtures
omit synthetic decoded roots/lookahead (12 subtest errors and a failed
`4160 != 42` assertion); and a CS-memory negative control erases its variable's
only use and fails compilation under `-Werror`. The production entry component's
9,324 checks and five preceding detected mutations do not make that incomplete
driver pass.

At `824`, the generated-source component passes 2,707 checks and all three
negative controls; the entry component passes 9,324 checks and 57 mutations.
The other selected drivers pass 15 scope-identity, one mmap argument, 16
returning-call and 12 Native-call-boundary cases. Its startup receipt records
capability version `17`, but the common runner accepts only versions through
`16`. The original `PREPARATION_FAILED` result remains, with normal RETIRE
`2/0/0/0` and no project modules in the subsequent observation.

The source-host comparison of all 6,777 private manifest entries and exact Git
delta shows only `tests/kernel/jit_continuation/run.py` and its README change
between `824` and `433`: the runner admits declared version `17` while retaining
the feature-bit checks. Production and unit sources are unchanged. This scope
proof explains the focused rerun; it is not another unit execution.

The new `433` indirect-tail phase calls an unregistered register-JMP callee,
then runs the declared scalar primitive on origin `38684` and resumes executor
`38629` in image generation `1`. The trace joins request, enter, done and resume
at the same real caller successor; the saved caller word is reused. The helper
and post-helper body each execute once, returning `0x993f730e40218045`. All
twenty final phase snapshots have zero errors and active requests, empty queues
and an idle lock. These controlled observations do not establish complete
actual MM callee closure or application completion.

## Separate producer-kernel preparation

Kernel recipe `1ab7124abb6140752c1f0bb6e862144d426a3875` is distinct from
runtime `4336d437`. It carries the generation-specific generated-text producer
and composition inputs; the live checks above still use scope5 v2 Build ID
`d3b5cf1b208028495b5fa9be2a3750b0831a2ec3`. The producer requires exact page
extents, retained core metadata and an acquired live-module reference for each
successful module reply, with a bounded 4,096-unit query scan. The extracted
consumer fixture does not validate those producer inventories in a booted
kernel.

The subsequent return to ordinary `7.0.0-38-kdlock1` is observed at boot
`eef8aa5d-cd97-4a7e-8a4b-692d0e374ea9`. V2 preservation precedes any v3 amendment;
no v3 build or boot pass is recorded here. Full callee closure still requires
complete leased instruction bytes and supported lowering. A known source owner
does not supply the signature of an unknown dynamic target. Live generated-page
ownership/retirement, both unchanged mmap1 models and per-syscall returned-body
joins remain pending. No mmap1 throughput, performance acceptance or promotion
is claimed.

## V2 preservation and build headroom

The v2 preservation inventory passes after two retained controller-preparation
failures: an intermediate install-receipt hash differs from the final receipt,
and the older ordinary-kernel bundle omits `variant`. The revised controller
uses the maintained verifier's absent-variant default while preserving the
exact normal release, manifest hash and running notes checks. Neither failed
attempt applies a kernel change.

The passed inventory reports 16,955,797,504 available bytes on DATA2, below the
unchanged 17,179,869,184-byte incremental reserve. The existing disk-expansion
authorization is used to grow only the second build disk from 160 to 168 GiB.
The initial 192 GiB proposal stops at its physical-host space check before any
monitor action; the bounded 8 GiB increase passes. The whole-device ext4 grows
online and reports 25,410,990,080 bytes free. All old builds and results remain.

The completed 7,492,842,002-byte v2 archive has SHA256
`e55b4b7d223582b29e01baf5539b09ee2c65bba739b9b85746ee76af2f524965`.
All 218,953 member contents, metadata, links and exact preserved roots pass the
read-only 380G10 check. Its receipt SHA256 is
`0e19fa99479d393d04218376ca0aef365a8efd59794c1665547c0d1bacd7e696`,
retained at `/tmp/kdlock-mm-scope5-v2-archive-check-20261103/verification.json`.
The archive stays at
`/mnt/kdlock-builds/kdlock-retained/mm-scope5-v2-20261103/linux-7.0.0-38-kdscope5-v2.tar.zst`.

The separately reviewed v3 controller is now running from normal boot
`eef8aa5d-cd97-4a7e-8a4b-692d0e374ea9`, with frozen kernel recipe
`1ab7124abb6140752c1f0bb6e862144d426a3875`. It rechecks the complete preserved
inventory before applying only the two producer C files and shared header.
A completed v3 build, installation, new boot and actual mmap1 proof remain
separate pending stages at this entry.


## V3 build, installation and both mode captures

The subsequent v3 amendment completes on the normal boot recorded above. It
applies only `arch/x86/kernel/alternative.c`, `kernel/module/main.c` and
`include/linux/kd_generated_text.h` from kernel recipe
`1ab7124abb6140752c1f0bb6e862144d426a3875`. Both affected objects and the full
`bzImage modules` build pass with `W=1`; the final receipt records drained,
idle state and unchanged Native MM body hashes. The resulting
`7.0.0-38-kdscope5` v3 Build ID is
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, distinct from the preserved v2
image despite sharing its release name.

The exact amendment result SHA256 is
`1437648901d99f473903f0e72832c591e8f643d8f91f2a501258967b7e1ea054`;
its fetched envelope is
`/tmp/kdlock-mm-scope5-v3-modules-stage-launch-20261103/amendment.json`.
The 511,824,768-byte `vmlinux` has SHA256
`75f511e8eecdc1cd06e480ea1d4b465def3697d8ab5ad5dd64a55013b45f934d`.
Module staging verifies 6,901 modules (676,818,883 stripped-tree bytes), then
installation and initrd-content verification pass. Their distinct receipts are:

| Completed stage | Actual receipt SHA256 | Retained source-host reference |
| --- | --- | --- |
| Module staging | `2ff73ff886cbcff9dc89c6dbf6850d008b664e1973ddfd6aeba53f239ded2a37` | `/tmp/kdlock-mm-scope5-v3-modules-stage-launch-20261103/progress-final-or-running.json` records the guest result path and hash. |
| Installation | `598c1c9e172a26ed554bc7f9c7d5231856c695b9de814dd0c9de8009338ed257` | `/tmp/kdlock-mm-scope5-v3-install-stage-launch-20261103/progress-final-or-running.json` records `INSTALLED_NOT_ARMED`. |
| Initrd-content check | `baee556a52b547cbb7329206e935197be39e103edbfb04fa49f72ebf268cf104` | `/tmp/kdlock-mm-scope5-v3-initrd-check-20261103/result.json` binds the installed module manifest and exact initrd. |

The existing one-shot entries preserve the ordinary default. Independent
reconnect and maintained bundle verification establish both v3 boots:

| Mode | Observed boot UUID | Capture receipt SHA256 | Bundle manifest SHA256 |
| --- | --- | --- | --- |
| Native, `kd_mmap=off` | `60b94472-0ccd-4eec-8661-4e733dfc8fa2` | `de3072a81bb4cdf42d1dc4a0da1299c6900b522779e8c7fd0e5cb07f533ac5fc` | `85949b47f94cd67894cb86f96126b523708ecc899a446756fb68454c7e4091a0` |
| KD, `kd_mmap=on` | `22c0a1d3-64b3-4de3-867c-e0521c6ba8c3` | `b96bd938b63862ca81b91d1b36efe94ae46e3155ae66cf6ff53ab4042d554938` | `5a67837a36698a6292513e0ce9ff386f7ce03068ef7feb8f98e9a62c5e72ba5f` |

The captures are retained as `capture.json` under
`/tmp/kdlock-mm-scope5-v3-native-boot-capture-20261103/` and
`/tmp/kdlock-mm-scope5-v3-kd-boot-capture-20261103/`. Each verifies the running
Build ID, 12 build files, 70 source files, four installed files, 59 bundle files
and the declared mode with `full (lazy)` preemption. The first KD arm attempt
stops on the amendment-controller file check; the second stops on an existing
host-capture byte mismatch. Their original empty replies and error logs remain
in the first and second arm-launch directories. The third arm attempt precedes
the independently observed KD boot. Neither a launch receipt nor a reboot
request alone is treated as a boot pass.

## Runtime 79b prerequisites and actual prewarm failure

Runtime source `79b6a7683e0fa93b152c0543a0e6bf18e947856c` remains separate
from the composed kernel recipe. Its initial VM checks pass nine syscall-pair,
one argument-representation and four application-continuation unit cases, plus
observer module compilation. Receipt
`/tmp/kdlock-mm-79b-units-20261103/reply.json` has SHA256
`ae26646fc9bcc808e78f2e33839020601a54da75578412be32292b4f6b8b71b7`;
these checks run on the ordinary kernel and do not claim live MM execution.

On the v3 KD boot, nine private-source cases and all nine helper phases pass.
The first outer wrapper then fails while reading a nonexistent `returncode`
field from launch-only build metadata. Its empty reply and `KeyError` remain in
`/tmp/kdlock-mm-79b-v3-first-20261103/`. The second prerequisite receipt binds
the actual completed helper result and build log without repeating the helper,
then runs all eleven killable/nesting phases successfully. It records
`passed=true`, `drained=true`, `final_idle=true`, `scored=false` and
`accepted=false`. This receipt is
`/tmp/kdlock-mm-79b-v3-prerequisite-second-20261103/reply.json`, SHA256
`54198c72bb1d361358b42ec4e4e6849b77c867cfe068de4b2f0f0a113b12d15f`.
The original helper result remains separately bound at SHA256
`6ba9e1c79550e67f865dcaa1f35d2aa48953057fb1e26c46f9ef2f0c0e0fe50a`.

The actual application attempt builds and loads the provider and observer, but
stops during required-site prewarming with
`prewarm site failed or became Native-only`. Both **`mmap1_threads`: NOT STARTED**
and **`mmap1_processes`: NOT STARTED** apply to this `79b` attempt. The retained
provider parameters are `rwsem_provider_active=N` and
`rwsem_provider_bindings=0`. Its original result remains `FAILED`,
`passed=false`, `drained=false`, `accepted=false` and `scored=false`; no
application invocation, completed syscall pair, delegated MM body or throughput
sample is established by the prewarm attempt.

The exact failed result is
`/tmp/kdlock-mm-79b-v3-failure-first-20261103/0-result.json`, SHA256
`82fada902adb5980cdc8e2ef116f51323fe76c6fb09e81029c21587c110e5e59`.
The retained `2-daemon.log` in the same directory has SHA256
`f389e6bd777bbbb260e2036b5f0afd7fe527fd03a2de328225b35c0438c0cb4e`.
It contains decoded-instruction and proposed-cache evidence; the immediate
blocker is the 262,144-byte text-cache bound, not evidence of a completed CFG:

| Entry's containing function | Cached bytes | Selected decoded instruction bytes | Proposed merged bytes at refusal |
| --- | ---: | ---: | ---: |
| `__do_sys_brk`, `0xffffffff817f7413` | 205,232 | 93,709 | 304,544 |
| `userfaultfd_unregister`, `0xffffffff81961fae` | 241,872 | 98,680 | 324,384 |
| `do_mbind`, `0xffffffff818724ea` | 226,528 | 85,635 | 311,776 |
| `__do_sys_remap_file_pages`, `0xffffffff817f845e` | 232,240 | 80,750 | 365,648 |

The source-host arithmetic record
`/tmp/kdlock-mm-79b-window-observations-20261103.json`, SHA256
`9bcab166aa5483a9cf6ad4fa673fb957b8cecb3d04cb33c289469577e284999c`,
binds the log and exact v3 ELF. Proposed bytes are not fetched bytes; cached
bytes outside the selected instructions are not proof that those bytes can all
be discarded or that subsequent callee closure will fit.

Normal retirement is recorded separately. The first retirement helper stops
at its expected daemon-working-directory check before sending a signal. The
second binds the actual daemon start identity and `workspace/daemon` directory,
closes it with normal SIGTERM, observes stable STOP, reaches source state
`2/0/0/0`, unloads observer and provider normally, and verifies final idle.
Its receipt is
`/tmp/kdlock-mm-79b-v3-normal-retirement-second-20261103/reply.json`, SHA256
`827e328690174b1e55cd3785d43d55a511cef6f793be7e195b723902fcd6b8e2`.
It records `drain_unknown=false` and the unchanged original failed-result hash.
This is daemon/module retirement on the KD boot, not a return to the ordinary
kernel and not a rewrite of the failed application result.

## Bounded lookahead follow-up: focused checks pass, actual validation pending

Runtime `0b33995c5aa8c6f8bab046900b6b3fb00c449719` adds a retained-service-only
planning retry when optional lookahead exceeds the existing text-cache bound:
1,024, 512, 256, 128, 64, then 15 bytes. It preserves all existing cached bytes
and roots, each mandatory 15-byte prefix, source lease acquisition before reads,
complete CFG construction, 32 expansion passes and the 640 KiB image bound.
The ordinary 8,192-byte policy remains unchanged. A smaller next plan fitting
is not proof that full reachable callee closure fits or lowers successfully.

Fresh v3-focused validation passes nine private-source, 66 text-region and 16
returning-call cases, the required provider build, nine helper phases and eleven
killable/nesting phases. Both live results explicitly pass and drain under the
same v3 Build ID. The actual receipt is
`/tmp/kdlock-mm-0b3-v3-first-20261103/reply.json`, SHA256
`b8075331f9cc8f4293afc81008c0d46e072419777b26129674c396d329f3f8b4`.
These are fresh results, not relabeled `79b` checks. Actual two-model validation
is newly launched and remains **pending at this entry**. No actual mmap1
returned-body, delegation, throughput, performance acceptance or promotion is
claimed. Generated-text ownership, a published image and controlled helper
returns do not by themselves establish complete actual MM callee closure or
per-syscall original-task completion.


## Bounded lookahead: actual retry still stops before either model

The subsequent actual diagnostic on runtime `0b33995c` also stops during the
all-site prewarm. The failed original result SHA256 is
`fed833fdea0e0f37e85ef9b42663d7d0bc348b047c636a35ca8a7282c1c42efe`;
[the retained attempt](lookahead-attempt.json) preserves that result separately
from successful normal retirement and the focused prerequisite receipt.
The factory remains `N`, bindings and body/completion counters are zero, and
both `mmap1_threads` and `mmap1_processes` are **NOT STARTED**.

The new planner successfully admits two smaller plans for the brk entry,
first 238,720 bytes with 256-byte optional lookahead, then 261,088 with 128.
The next mandatory 15-byte-prefix plan needs 265,777 bytes and fails the
unchanged 262,144-byte cap. The userfaultfd entry similarly reaches 259,712
bytes before its minimum plan needs 263,680. Thus optional trimming makes
observable preparation progress but does not establish complete callee closure.
The point-in-time daemon snapshot SHA256 is
`49b743fb86a43e4872a037459a029a6779273d4c5555ab8ff792c823a676c912`.
It contains a later entry beginning preparation, not a completed result for
that entry; do not infer all later sites have the same failure.

Normal retirement binds the daemon PID/start identity, sends ordinary SIGTERM,
waits for zero source writers, obtains repeated identical observer STOP,
reaches exact source retirement `2/0/0/0`, unloads both modules normally and
verifies final idle. The independent source-host retirement receipt SHA256 is
`23f97e46104387cdbb099fc6269ee9cf62a523053a96f6f083ef9375dc57211e`.
It confirms the failed result bytes remain unchanged. This is no application
return, delegated MM completion, throughput score or performance acceptance.

The next bounded general change is documented in
[explicit Native argument mapping](../../../../../docs/design/native_call_arguments.md):
use Linux's existing explicit-caller allocation API for a single returning
Native interval while retaining the logical source CALL identity and resuming
the same image on E. It does not increase cache/image bounds or change an MM
body. Implementation and subsequent actual mmap1 proof remain separate gates.

## Explicit Native argument mapping: implementation and focused checks

Runtime `8f12f82000ea73d28526f938cc21b87bcfa1c744` implements the separately
registered argument map. The logical source target, declared source arity and
real CALL successor remain distinct from the Native execution target and its
arguments. Both executable targets are retained before image publication; the original
source CALL word is consumed once when execution resumes on the same executor
and image. Existing identity descriptors keep their ABI and discovery format.
The allocation rows use Linux's explicit-caller APIs, including the exact
`CONFIG_SLAB_BUCKETS` arity variants; the two cache API rows retain their Native
identity signatures. This does not change Native MM bodies or enlarge the
text-cache, expansion-pass or image bounds.

Fresh focused checks pass on the v3 KD kernel, boot
`22c0a1d3-64b3-4de3-867c-e0521c6ba8c3`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, with `kd_mmap=on` and
`full (lazy)` preemption. The kernel recipe remains the distinct
`1ab7124abb6140752c1f0bb6e862144d426a3875`. The 6,787-file private runtime
snapshot, exact source/kernel identities and selected live observations are
bound in [mapped-call-checks.json](mapped-call-checks.json). Its original focused
reply is `/tmp/kdlock-mm-8f12-v3-first-20261103/reply.json`, SHA256
`6afe6a95dd502899b26535d38169f42870f90ff2d0528cbb8394203ad5aed69e`.

| Fresh focused check | Observed result |
| --- | --- |
| Production mapping validation, marshaling and lifetimes | 1,756 checks with slab buckets enabled; 1,752 disabled; seven negative controls detected. |
| Native scheduling contract | 156 checks in each preempt-RCU configuration; five negative controls detected. |
| Returning-call lowering | 16 cases pass. |
| Private source provenance | Nine cases pass. |
| Helper / mapped observation validators | Six / four cases pass. |
| Continuation runner lifetime checks | Seven cases pass. |
| Live helper / killable and nesting phases | 11 / 11 complete, pass and drain; all original phases remain. |

The helper run includes its required successful provider build. The build
command metadata records launch details; the focused wrapper derives completion
from the successful helper run and does not claim a duplicate standalone build.
All final phase observations have zero errors, active users, holders and queue
counts. Retained release-control bits are preserved in the JSON.

The new two-to-five phase observes original task `14633` on its own Native
stack, with zero preemption count and enabled IRQs. The five Native arguments
are source0, zero, source1, minus one and the exact source CALL successor.
There is one Native execution, one post-call body effect and no execution of
the logical Native body. The same executor `14565`, root identity and image
generation `1` resume with identical full AX and flags in the done/resume
records. Five source `SETcc` observations independently match CF/PF/ZF/SF/OF;
they do not independently observe AF.

The additional allocation phase returns one actual 53-byte production
allocation. All 53 bytes are initially zero, then written and checked; the
same pointer is released exactly once through `kfree`, with one body
completion. This is bounded allocator mechanism evidence. It is not a separate
live cache-allocation test, unchanged-application result or performance sample.

The subsequent two-worker threads/processes diagnostic has been launched from
this exact runtime and remains **pending at this entry**. Launch metadata does
not prove that either model started or completed. No nano result, actual mmap1
returned-body or delegation proof, throughput, performance acceptance or
promotion is claimed. Full callee closure, actual MM source/owner lifetimes and
per-syscall original-task completion remain separate obligations.


## Mapped allocation: actual retry still exceeds source capacity

The subsequent actual `8f12f820` preparation fails before either application
starts. The original result SHA256 is
`df8e45587cd8465c8d34ec9b24e129856dcb057459ab4d17f1465b909c405b75`.
[The retained actual attempt](mapped-call-attempt.json) keeps this original
FAILED/drained-false result distinct from later successful normal retirement.
The factory stays inactive with zero bindings and zero body/completion counters;
`mmap1_threads` and `mmap1_processes` are both **NOT STARTED**.

At brk entry `0xffffffff817f7413`, expansion 19 holds 262,032 cached bytes,
131,000 selected instruction bytes and 33,443 instructions across 8,075 blocks.
There are still 212 incomplete blocks and 214 pending targets. The smallest
next plan needs 265,401 bytes, above the unchanged 262,144-byte bound. The
point-in-time daemon log SHA256 is
`dcb982381245b673cd204639b0bc966f45c7c8244e4d5195510b1dc592d7c662`.
It begins a later entry after this failure; that entry's final outcome is not
established by the captured snapshot. Neither full graph nor emitted brk-image
size has been measured. The passed mapped allocation fixture remains valid
mechanism evidence, without establishing actual MM completion.

The separate cleanup verifies the exact daemon start identity, normal SIGTERM,
zero source writers/frames, stable repeated observer STOP, source retirement
`2/0/0/0`, normal observer/provider unload and final idle. It confirms the failed
result bytes remain unchanged. Its source-host receipt is
`/tmp/kdlock-mm-8f12-v3-normal-retirement-first-20261103/reply.json`; its exact
hash is retained in the JSON. Master remains unchanged. No Nano, application
throughput, delegation-length result, performance acceptance or promotion is
claimed for this attempt.


## Capacity candidate: focused checks stop before any build/live phase

Runtime `759dcf3aa8122b2f3e26843268ba6fabeaa2d558` implements the bounded
retained-capacity design. Its first focused VM receipt is retained unchanged as
[capacity-first-checks.json](capacity-first-checks.json), SHA256
`d1219746ed566ab4e794c9a167e55272b27698f99492916f238d488c449ba177`.
Private-source nine cases, text-region 75 cases, returning-call 19 cases and
15,663 executable Native-call wrapper checks pass. The three image-capacity
cases and seven existing Native-image cases fail because the new shared-header
reader requests ASCII while the existing C header contains UTF-8 comments.
The registry fixture also fails compilation: its userspace kernel-interface
model lacks the integer aliases required by the already included origin-memory
header and the current returning-call source-pin entry. This is not a successful
compile, skip or Native registry execution.

The wrapper records `live_started=false`; no provider build, module load, helper
phase, killable phase or mmap1 attempt runs from this source identity. Correct
header decoding to UTF-8 without rewriting established header comments. Update
the fixture's exact-width kernel aliases and source-pin interface model while
retaining production registration/retirement checks and adding an explicit
source-pin failure witness where needed. These corrections do not change the
capacity design or any lock acquisition/cancellation/ownership behavior. A new
frozen source identity must pass the affected checks before live validation.


The next source, `f012053213f35709c3f429e233b5be9641fccbad`, passes private
nine, text-region 75, image-capacity four, returning-call 19 and Native-call
15,663 checks; the registry fixture compiles and detects all sixteen required
negative controls. Its unchanged receipt is
[capacity-second-checks.json](capacity-second-checks.json), SHA256
`f850e2e60262accd2911cc0ec5270a45e25bb3c7189f145e6dea82f203c0cf76`.
Two of the seven Native-image observation cases still error because their
existing global `Path.read_text` mock returns synthetic kallsyms for the newly
added shared-header read as well. The other five observation cases pass.
Restrict that external-I/O substitution to `/proc/kallsyms`, allowing every
other path to use the original reader. Preserve all receipt hashes, relocation
checks and negative cases. This is a fixture correction; no production behavior
changes. The parent still records `live_started=false`, with no build, module
load, helper/cancellation phase or mmap1 attempt from this identity.

## Bounded capacity: corrected focused checks and fresh live prerequisites

Runtime `3a0171f33516b9c914f4f33da1c7f0c415473ba0` completes the focused
validation chain after the two retained fixture failures above. The implemented
retained profile permits 1 MiB of aggregate cached source and 262,144 return-flow
analysis steps. Ordinary translation retains 256 KiB and 65,536 steps. The
shared daemon/provider/Python image capacity is 4 MiB; CFG expansion remains
bounded to 32 passes. Larger merged source windows use consecutive reads of at
most 256 KiB, each leased before its own read. Missing, short or refused
mandatory pieces prevent completion; old bytes, roots and each required
15-byte instruction prefix remain retained. The optional-lookahead retry does
not remove existing source or permit incomplete graph publication.

The exact `f0120532` to `3a0171f3` delta contains the Native-image test mock and
two report files only. All production bytes remain unchanged. The historical
passing `f012` checks therefore remain recorded under their actual source,
while the corrected observation driver and live prerequisites run freshly on
`3a01`. [capacity-checks.json](capacity-checks.json) binds both original replies,
the exact three-path Git/source-map delta, current private snapshot and selected
live observations. It does not relabel the earlier unit executions.

| Source and executed scope | Observed result |
| --- | --- |
| `f012`: text regions / shared capacity / returning calls | 75 / four / 19 cases pass. |
| `f012`: production registry fixture | 32,174 checks pass; all 16 negative controls detected. |
| `f012`: executable Native-call wrapper | 15,663 checks pass; userspace lowering fixture only. |
| `f012`: Native-image observations | Two errors among seven cases remain preserved; no build/live phase starts. |
| `3a01`: freshly rerun private source / Native-image observations | Nine / seven cases pass. |
| `3a01`: required provider build and live helper / killable phases | Build succeeds; 11 / 11 phases complete, pass and drain. |

The fresh reply is `/tmp/kdlock-mm-3a01-v3-first-20261103/reply.json`, SHA256
`bd6bd6c3ed5dcbb2dac465dbabee54675c1b947e6666ba5de99ffdda83b8b945`.
It binds runtime `3a01` on the same scope5 v3 KD boot
`22c0a1d3-64b3-4de3-867c-e0521c6ba8c3`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`. The composed kernel recipe remains
`1ab7124abb6140752c1f0bb6e862144d426a3875`. The successful helper establishes
completion of its required build; launch-only build metadata is kept distinct.
Both new mapped-call phases pass again, including the original-task return and
one 53-byte allocation/write/check/free sequence. Every phase records zero
errors and final idle state; retained release-control bits remain unchanged.

The compact record also binds nine exact decoder and kernel trace source
captures, including Miasm's core and x86 subclass. Source inspection does not
establish a numeric limit for an instantiated decoder or substitute for complete
CFG coverage. Those observations remain separate from the project's explicit
source, return-flow and image bounds. The captured v3 configuration selects
`CONFIG_FRAME_POINTER=y` and `CONFIG_UNWINDER_FRAME_POINTER=y`, with ORC disabled;
the config bytes and capture receipt are separately bound in the JSON.

The subsequent unchanged two-model diagnostic is **pending at this entry**.
Neither launch nor site prewarming proves that an application model has started
or returned. No actual mmap1 completion, delegated MM body, Nano result,
throughput, performance acceptance or promotion is claimed. Larger preparation
capacity and controlled helper returns do not establish complete actual-MM
callee closure or exact per-syscall ownership/retirement.
