# kdmm31 audit and performance preparation, October 25

Audited implementation: `e6fc371b032cc0444dba34ee9025e7d939811125`, branch
`codex/mmap-irq-trylock-20261025`. Master remained
`769ba5b0c595a2739f61e372bab9230027050c88`. The unrelated emptied disk-cleanup
README is user WIP and was preserved. Protocol, workload and tooling audits were
read-only; implementation and validation used one owner. The subsequent
documentation reconciliation was restricted to explicitly handed-off paths.

No new demonstrated lock correctness defect was found in this scoped audit.
No qualified current performance baseline or optimization gain is claimed.
The maintained [benchmark guide](../../../../mmap_lock/README.md) contains the
bounded proposal and commands; kernel boots and root host metadata access remain
subject to exact approval.

## Lock audit

| Classification | Evidence and implication | Minimal next action |
|---|---|---|
| Validated tradeoff: atomic reader release | `kd_rwsem.c::kd_up_read` performs the fully ordered final decrement but avoids scheduler/waitqueue locking under IRQ/preemption-disabled contexts. `kd_rwsem_drain_readers` rechecks after one jiffy: at HZ=250 about 4 ms plus scheduling delay. | Retain this baseline. Measure actual affected waits before redesigning wakeup. Embedded irq_work needs late-publication/cancellation/object-lifetime proof. |
| Progress hypothesis | Admission uses competitive compare/exchange and `wake_up_all`; no native rwsem handoff/fairness equivalence is established. A positive delegation phase can be prolonged by further reservations. | Measure the exact killable admission path and starvation indicators; do not infer starvation from contention alone. |
| Historical performance clue, unqualified | The October 22 profile placed 87.11% of 1,000 KD samples in phase admission and sampled no physical-gate contention. Intrusive phase observation counted 129,152 acquisitions, 1,683,343 blocked returns and 1,583,015 failed following predicates (94.04%). | Retry amplification is a hypothesis, not elapsed wait time or proof that wake-all is causal. All associated endpoint failures remain rejected. |
| Wrong potential tuning target | `kd_down_write_killable`, used by mmap/munmap, bypasses the 16,384-probe uninterruptible polling macro. Ordinary writers reserve exclusive admission before taking the physical gate. The corrected ELF confirms these call sites. | Establish qualified whole-workload measurements before changing polling or OSQ. |
| Provider diagnostic gap narrowed | The already-authorized one-attempt load of the unchanged provider succeeded, retired and unloaded. This was no workload/JIT execution. The old 7,592-byte per-CPU allocation failure remains unexplained. | Do not repeat the attempt or unload unrelated modules. Keep capacity, fragmentation and allocator hints as unresolved alternatives. |

The acquisition/release trace covered:

- Reader admission: fully ordered increment plus acquire recheck, with ordered
  rollback through `kd_up_read`; read trylock preserves atomic caller state.
- Ordinary writers: exclusive admission reservation precedes the local physical
  gate; release drops that gate before fully ordered admission reopening.
  Interruptible/killable failures unwind gate and reservation in that order.
- Downgrade: the reader count is installed before writer gate/phase release.
  It neither drops original-task context nor delegates the native MM body.
- Explicit outer writer reservation: exact ownership transfers back only after
  the outer mutex ACK; published requests cannot cancel or downgrade.
- Local mutex owner/waiter/handoff/pickup state and independent OSQ/delegation
  links: slot retirement and public unlock's exact provider route remain intact.
- mmap lifetime: `mmgrab` precedes token publication, exchange consumes a token
  once, and unlock precedes `mmdrop_async`. Destruction requires stopped/joined
  users; an idle observation does not independently establish object lifetime.

References: `kernel_module/kd_rwsem.c`, `include/kd_rwsem{,_direct}.h`,
`include/kd_mutex.h`, `kernel_module/lock/mutex_calls.inc`, and
`kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c`.
The integration patch remains limited to lock selection and minimal API/lifetime
wrappers; native MM/scheduler bodies and originating tasks are preserved.
Full JIT/provider, whole-kernel, RT/ww_mutex and lockdep equivalence are not
established by this review. Retired operation-specific unmap/page-layout work
remains historical.

## Tooling findings

The independent review inspected the untracked controller SHA-256
`90452be147b60b18c2c55f4d7b23e597cd6b8ded61a67daeaa864a9cac1b413f`.
Its original bytes are reachable at archive ref
`archive/host-capture-control-before-audit-20261025`, commit `27b17859dd91207c0d289e7487c0c736be358973`.
Frozen historical helpers and controllers were not edited.

| Severity | Finding | Maintained remedy / check |
|---|---|---|
| P1, source-reachable | Historical monitor `read_prompt` can loop forever on EOF. No saved attempt demonstrated that loop. | `host_state.read_prompt` rejects EOF, bounds bytes and total time, and closes its own socket; mocked EOF/deadline tests. |
| P1 | Endpoint/final identity exceptions discard available controller evidence. | `host_capture_control.observe` finalizes partial receipts, records child ownership immediately and retains every consumed output byte. |
| P2 | Timeout/interruption omit partial bytes and leave child status ambiguous. | Explicit phase, PID/start where available, timeout/interruption timestamps and unknown-completion fields; no signals or retry. Transport loss/SIGKILL still cannot guarantee receipt delivery. |
| P2 | Final command equality alone cannot reject PID reuse. | PID/start/command checks bracket captures; partial task rows/errors survive; runtime deltas require matching identities. |
| P2 | Historical fetch timeout can leave `passed=true` with unconfirmed drain. | New controller sets success only after required stages and resets it on every exception; mocked fetch timeout. |
| P2 | Missing/malformed endpoint evidence aborts old finalization before cleanup. | New finalization independently requires normal client completion, exact business/lifetime checks and fault-free state before ordinary unload; endpoint failures still reject performance. |

A further paired-runner/report review found four issues. The following remedies
are implemented in `e15a5aa3dd2b8cfcac5846d5e6f4a90743cd94dc` and passed all
14 focused paired/report mocked tests. This supersedes the earlier nine-test
paired result; it does not establish live workload or timing acceptance.

| Severity | Finding | Implemented remedy with focused mocked coverage |
|---|---|---|
| P1 | Reporting trusted final acceptance flags without replaying endpoint/controller/admission evidence. | Persist bindings and replay saved qualification, validation and raw measurement evidence; missing or changed captures reject the report. |
| P2 | Repeat labels and boot grouping could disagree with the full workload specification and predecessor chain. | Require the canonical specification, four measured boot blocks, consistent readiness and the exact chronological predecessor binding. |
| P2 | Fixed/timed clients could start after module load without an intervening kernel-fault check. | Check the kernel log immediately after each load, before starting the client. |
| P2 | Validation admission checked flags and row count without proving the complete fixed/timed case set. | Bind and replay the fixed-work writer proof and all four exact timed-client validation cases. |

The saved October 25 control failed with `PermissionError` reading
`/proc/257489/numa_maps`, before monitor connection or snapshot query. Its two
67-task observations are diagnostic only. The prior controls already showed
setup/no-op phases can create workers without the benchmark; repeating those
controls would not isolate SSH from background writeback. The historical helper
captures tasks **before** the snapshot query. All 24 October 22 actual-MM
endpoints had 68–70 tasks; qualified count remains **zero**. Later quiet samples
cannot replace rejected endpoints. See the
[QEMU controls](../qemu-workers-20261021/README.md) and
[actual-MM receipt](../../tests/serial-continuation-20261022/ACTUAL_MM.md).

## Retained validation and artifacts

Existing corrected-image actual mmap API validation passed **137 Native** and
**161 KD** assertions. Standalone validation passed **352 assertions and two
basic programs**. These are different validation classes. The one-attempt full
provider load used ELF SHA-256
`eab86044148276b133f1e24b5c6b33508a13a4b56833f5a02e977ee9ff7f8f49`:
3,398,744 bytes, per-CPU section 7,592 bytes/alignment 128, all 85 imports matched.
Reserved per-CPU free space was 8,100 → 508 → 8,100; retirement had zero remaining
modules/frames/writers. It does not prove why the previous allocation failed.
Raw diagnostic: `raw/tests/provider-load-once-20261025/`.

The new private reconstruction verified all **102,993** entries against both
base and corrected inventories, including types, modes, every regular file's
bytes and symlink targets. Two removed dependency files were moved into retained
`displaced/` storage, not deleted. The exact post-install `modules.order` was
restored. Captured identity verification passed 5 bundle, 44 source and 11 build
files plus configuration. Nothing compiled or installed a kernel. Inputs:

- Delta: `cde7ad43033ea25812ec608482200e754b56ccb271a88b48665c89918630cf16`.
- Full inventory: `9687419fcbc6165a929c6652e65321abab3a93a87e72386c329df64c72fb7aca`.
- Post-install delta: `0d5bbb6d8ed27ef5b521efb02ab0e70de7aa60d2abe40f95f3458d3e686a5b4a`.
- Candidate vmlinux: `fea94797765cf9f1ac4acdf91fc89dfe54b22696a8ffc18fdf09573ff65a1190`.
- Candidate Build ID: `ef5179e8def44f0255adcd62585f62f118fee30f`.

The first benchmark preparation compiled the module and checked CRCs, then
failed because bpftool was unavailable. The second failed parsing the retained
base BTF with the guest's installed libbpf (`EINVAL`). Both are failed attempts,
not passes. The preserved installation receipt identifies the existing pahole 1.25 parser
that successfully checked this exact base and 74 split inputs. Subsequent
preparation reuses that operation. A copied private bpftool remains unused; no
package/system installation or BPF load is involved.

**Build-3 passed** using the existing `/usr/bin/pahole` 1.25. The unchanged
benchmark payload and both clients compiled, all **16 imported CRCs** matched,
and base/split BTF parsing passed against the corrected candidate. Build-1 and
build-2 remain failed attempts. This preparation loaded no module and did not
compile, install or boot a kernel. Source and binary hashes are retained in
`build-3/result.json`, also copied to the source-side
[build receipt](../../raw/bench/mmap-kdmm31-prep-20261025/build-3-result.json).

The two basic programs and current **30 mocked tooling tests** (16 capture,
14 paired/report) passed in the recovery VM. The retained logs are `unit-1.log`,
`test_mmap_capture-final.log` and `test_mmap_paired-review-fixes.log`; the last
records `Ran 14 tests, OK`.
Capture fixes are committed at `82c20b4f2cf32d580d2a9c130f682d63e123bf4c`;
preparation, paired runner and report fixes at
`e15a5aa3dd2b8cfcac5846d5e6f4a90743cd94dc`. These checks do not execute an actual
mmap workload or establish provider/JIT execution, new runtime coverage or timing.
Prior actual mmap correctness receipts were reused rather than rerun.

The preparation owner retained `preparation-summary.json` under
`/root/kdlock-evidence/10.176.26.71/bench/mmap-kdmm31-prep-20261025/` and sealed
the preparation archive with SHA-256
`d09d1ee5c06e454e248115335956850de6159e4e9581b257f8393699acd949a7`.
The source-side [preparation summary](../../raw/bench/mmap-kdmm31-prep-20261025/preparation-summary.json)
and [archive check](../../raw/bench/mmap-kdmm31-prep-20261025/archive-check.json)
bind these results to the retained `preparation.tar.gz`, including the logs and
both failed build attempts.

At the last live check the VM was still `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, with the exact original 73 modules, no project
module/workload and empty `next_entry`. Taint was **12288**, reflecting the prior
unsigned out-of-tree diagnostic; do not repeat the earlier zero-taint claim.
Recovery inputs and installed candidate artifact hashes still matched. This is
the final health reported by the preparation owner, not approval for a live
cycle. The six-boot/24-session proposal and read-only root host capture remain
unapproved. New qualified measurements remain zero; runtime readiness and timing
acceptance require their own retained evidence.

## Completion and handoff

Preparation ended at `eb10f2165fc9ee4b9d3e68e5642130545f5d07d1`, with 26
changed files across three separate local commits:

| Commit | Scope | Files |
|---|---|---|
| `82c20b4f2cf32d580d2a9c130f682d63e123bf4c` | Capture failure evidence, monitor bounds and focused mocked checks | 3 |
| `e15a5aa3dd2b8cfcac5846d5e6f4a90743cd94dc` | Reconstruction, benchmark preparation, paired qualification and reporting | 8 |
| `eb10f2165fc9ee4b9d3e68e5642130545f5d07d1` | API/support guidance, audit evidence and bounded performance instructions | 15 |

The [commit inventory](../../raw/bench/mmap-kdmm31-prep-20261025/commits.json)
records every changed path. The core lock/MM implementation and master remained
unchanged, and the unrelated disk-cleanup README was left uncommitted. The
[final source-sync receipt](../../raw/bench/mmap-kdmm31-prep-20261025/final-source-sync.json)
confirmed all 15 documentation hashes in the VM at `eb10f21`; that receipt
predates this handoff update. No build, test or synchronization owned by this
session remained running when preparation ended.

On October 25, the user explicitly approved sending the completion summary to
Codex task `01a15996-4e4d-7002-985e-aa239685e038`. Delivery failed with
`thread/read failed: thread not loaded` (code `-32600`), and a follow-up read
returned the same error. The handoff was not delivered; this receipt retains
the completion record. The approval covers sending the summary only. The
six-boot/24-session benchmark cycle and root host capture remain unapproved.

The `92f773f` documentation update added no VM health observation or runtime result.
The next performance step is the bounded Native/KD comparison after its required
approval, followed by one optimization selected from qualified measurements.

## Local integration and read-only readiness

After the user's bounded local-integration authorization, local `master` was
fast-forwarded from `769ba5b0c595a2739f61e372bab9230027050c88` to
`92f773f50511e9f3685918730ecaf2551e067a71`. The five linear commits are `e6fc371`,
`82c20b4`, `e15a5aa`, `eb10f21` and `92f773f`: 39 changed files, with no MM or
scheduler body changes, retired experiment additions or untested optimization.
The lock implementation still matches `e6fc371`; executable tooling still
matches `e15a5aa`. Recorded validation above was reused, not rerun. The feature
branch and archive refs remain reachable; no history was rewritten or pushed.
The sole unrelated dirty path remains
`bench/results/10.176.26.71/tests/vm-disk-cleanup-20261022/README.md`, still empty
with SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

The guest inspection began on **2026-10-25 at 17:00:37 (Asia/Shanghai)**. It used
bounded read-only SSH commands, without executing a benchmark or readiness
runner. Recovery release, boot ID, exact 73-module set, taint 12288, 64 online
CPUs, voluntary preemption and empty `next_entry` matched the preceding receipt.
The generated default still selects recovery through
`/etc/default/grub.d/99-kdlock-nopvspin.cfg`; the two kdmm31 menu entries are
present in `/etc/grub.d/42_kd_mmap_kdmm31` and generated GRUB configuration.
All four installed candidate boot-file hashes matched. No matching guest
build/workload process or open descriptor under the inspected project, build,
boot and module paths was found; the descriptor scan reported no access errors.
This is a guest observation, not a host-wide open-reference proof.

All 13 prepared source/binary bindings and 22 recorded runner hashes matched.
The persistent runtime-identity tree has all 44 source and 11 build inputs;
its ELF, Module.symvers, configuration and embedded BTF matched their recorded
hashes, as did the candidate bundle manifest, both prior actual mmap receipts,
the full reconstruction inventory and post-install delta. The three original
environment receipts also matched. Pinned packages remain miasm 0.1.5,
future 1.0.0, pyparsing 2.4.7 and pyelftools 0.27. No full archive audit or new
correctness campaign was performed. Current qualified performance cases remain
**zero**.

### Cleanup preservation dependencies

These are preservation requirements, not a deletion authorization:

| Class | Exact location and reason |
|---|---|
| Required boot/recovery | `/boot/{vmlinuz,initrd.img,config,System.map}-6.1.159-kdclobber2`, the equivalent four `6.1.159-kdmm31` files, both `/lib/modules/<release>` trees, `/boot/grub`, `/etc/default/grub*` and the two configuration files named above. |
| Required recovery source | `/mnt/kdlock-builds/linux-6.1.159-kdclobber2`: both `/root/linux-6.1.159-kdclobber2` and the recovery module build/source links resolve here. Preserve the target, not just the links. |
| Required identity bundles | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919`, `/root/kdlock-kernel-baselines/mmap-kdmm31-irq-20261025`, and `/root/kdlock-kernel-work/mmap-irq-20261025/candidate-1/runtime-identity`. The current runner consumes the persistent candidate identity tree. |
| Required prepared run | `/root/kdlock-evidence/10.176.26.71/bench/mmap-kdmm31-prep-20261025`, especially `build-3/result.json`, `build-3/fixed`, `build-3/timed`, `build-3/source/workload_modules/mmap_writer/kd_mmap_writer_native.ko`, every source path bound by the receipt, and `prior/actual-{native,kd}-1.json`. Preserve its adjacent `.tar.gz` and source-side raw copy. |
| Required qualification environment | `/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/{host-state,environment,topology}.json`. These historical files remain active hash-bound dependencies. |
| Required source and tools | `/root/host_fs/kdlock`, source checkout and Git/archive refs on 380G10, benchmark-host source mirror, and `/root/kdlock-translation-venv-20261019`. Preserve the bound C/header/private `.inc`/Python/JSON inputs and unrelated user work. |
| Required reconstruction/provenance | `/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux`, candidate `new-volatile.json`, `resume-20261025/post-install-tree-changes.tar.gz`, retained `kdmm31-delta.tar.gz`, and existing recovery/candidate raw archives and manifests. The source-side delta is under `bench/results/10.176.26.71/raw/tests/mmap-irq-trylock-20261025/`. Preserve the historical archive containing the previously removed guest `vmlinux.o` as well. |
| Reproducible scratch; not needed by the prepared live run | `/dev/shm/kdmm31-perf-prep-20261025-build` and duplicate inputs under `/dev/shm/kdmm31-perf-prep-20261025-inputs`. Reconstruction receipts/displaced files are retained in preparation evidence, and the delta/source manifest have retained copies. The unused copied `bpftool-6.8` is not a campaign dependency. Removing tmpfs files would reclaim memory, not persistent disk space; nothing was removed. |

The installed candidate build/source links still name absent
`/dev/shm/kd-mmap-irq-20261025/linux`. This known limitation does not block the
prepared run: it uses the persistent build-3 binaries and runtime-identity tree.
Do not repoint those links or rebuild merely to start the existing campaign.

The cleanup worker's conditional source-host candidate,
`bench/results/10.176.26.71/raw/bench/mutex-kdonly-20261017T140354Z/replay`, is
outside current runner inputs and bound source directories. Matching text in
current runners refers to the recovery snapshot tag, not that replay directory.
Its reported 3,314,864,128 allocated bytes would free source-host space only.
The cleanup worker reports that all 150,984 manifest-listed regular files match
names, types, sizes and modes, with single links and no extra paths; 3,916
archived symlinks are absent. Archive and manifest hashes match, but payload
bytes were not rehashed, restoration was not exercised and global open-reference
absence is unproven. It is not yet deletion-ready, and no guest deletion
candidate was established by this dependency inspection.

### Campaign headroom and remaining gates

| Guest filesystem | Available bytes | Available inodes |
|---|---:|---:|
| Root, including `/boot` and `/tmp` | 2,996,535,296 | 10,352,410 |
| `/mnt/kdlock-builds` | 10,031,104 | 1,499,205 |
| `/dev/shm` | 5,740,777,472 | 2,976,510 |

Use root for new campaign receipts; the data disk's reserved free blocks are
not a working-space budget. No new kernel, payload build or reconstruction is
needed. The 32 timed checks (eight validation plus 24 measured) include eight
sampled runs at each worker count. With 65,536 latency entries per worker and
at most 21 decimal/comma bytes per entry, their latency arrays total at most
187,170,816 bytes (178.5 MiB). Progress/worker records are much smaller. At the
observed 47,289-byte kernel-log size, 129 planned log copies add about 5.8 MiB;
five readiness bundle copies add 1,465,370 bytes. The retained host receipt is
129,813 bytes, about 6.8 MiB if repeated 55 times before transfer duplicates.

Allowing 256 MiB for raw campaign evidence and another 256 MiB for an archive
is a planning estimate derived from those quantities, not a hard output bound.
Fresh host-capture sizes, log growth and metadata/transfer copies must still be
checked before execution. Root would retain 2,459,664,384 bytes after that
512 MiB allowance; current guest capacity therefore does not require deleting
an archive to start this prepared campaign. No new tmpfs build space is needed.
Benchmark-host backing-disk capacity and open references were not inspected.

The remaining gates are exact approval for the six-boot/34-payload-check/
55-host-capture cycle, fresh recovery snapshot and host admission evidence,
and both-mode payload validation on the candidate. The denied host metadata
capture was not retried. Neither later quiet task observations nor successful
build/hash checks establish accepted performance. Cleanup, kernel boots and
the live cycle remain unperformed and separately subject to their approvals.
