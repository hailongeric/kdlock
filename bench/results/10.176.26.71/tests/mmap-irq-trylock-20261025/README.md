# IRQ-disabled read trylock: focused actual mmap validation

**The corrected built-in adapter passed 137 Native and 161 KD assertions on
actual mm objects, with zero errors, complete drain and normal unload.** Both
modes used the same verified `6.1.159-kdmm31` image and prebuilt probe. Recovery
`6.1.159-kdclobber2` is restored and healthy. The change was developed on
`codex/mmap-irq-trylock-20261025`, based on `769ba5b`.

The initial automatic approval rejection prevented installation from running.
After explicit user approval on October 25, the same installation was retried
once through the ordinary approval mechanism and succeeded. No denial was
bypassed. The earlier standalone result and initial blocked state remain
preserved separately; the subsequent actual-mm results close that runtime gap.
The preserved kdmm1 still contains the old deliberate refusal.

## API and implementation

The common read/write family is `include/kd_rwsem.h`, `struct kd_rwsem`, with
`kd_down_read` / `kd_up_read`, `kd_down_write` / `kd_up_write`, the existing
trylock/killable/interruptible acquisitions and `kd_downgrade_write`. Linux MM
keeps its `mmap_*` facade through `struct kd_mmap_lock`; preparation namespaces
these shared primitives as `kd_mmap_down_*` / `kd_mmap_up_*`.
`kd_mutex_local_*` inside the rwsem implements physical writer ownership; direct
caller use of the embedded gate bypasses reader admission and drainage.
`KD_RWSEM_OUTER_WRITE_*` remains a separate explicit delegation pair. API
unification does not move native MM bodies to another task. See the
[maintained API guide](../../../../../kernel_integration/mmap_lock/README.md#public-readwrite-api-and-atomic-read-trylock).

Production changes are limited to `kernel_module/kd_rwsem.c`, its public contract
comment and the adapter's IRQ refusal. No structure, native MM body, kernel
scheduler body, exported native interface, physical ownership record, ABI2 entry,
source lease, unlock ACK or frame-retirement protocol changed. The mutex remains
32 bytes and the rwsem 320 bytes. Read admission remains concurrent.

The safety argument covers acquisition, rollback and release:

- Read trylock still checks admission, publishes an ordered reader increment and
  rechecks admission with acquire ordering. The writer reservation RMW and its
  acquire-ordered reader check retain the existing exclusion/barrier argument.
  A failed speculation cannot access protected data.
- Both rollback and successful read unlock use the same fully ordered decrement.
  When IRQs or preemption are disabled, they do not acquire a waitqueue/scheduler
  lock, allocate, schedule, modify IRQ/preemption state or retain a deferred pointer.
  The x86 atomic path contains a fixed sequence, without a software retry loop.
- Every reader-drain wait, including ordinary, interruptible, killable and
  unpublished outer-writer reservation paths, now has a one-jiffy condition
  recheck. A last decrement that omits an unsafe synchronous wake cannot leave a
  writer indefinitely asleep due to a lost notification. A timeout only rechecks;
  it never permits entry while readers remain. Ordinary phase waits are unchanged.
- IRQ-enabled, non-atomic final release retains its immediate wake. Applicable
  signals still cancel a drain, remove its waiter, release the physical gate and
  then reopen admission. Timer/wait storage belongs to the schedulable writer;
  there is no new object lifetime beyond a read unlock. The existing exact BPF
  token/mm-reference transfer remains intact.

This is a correctness/latency tradeoff, not full Native equivalence or a
performance-neutral change. At the selected `HZ=250`, one jiffy is 4 ms. An atomic
final release can wait for that recheck, and scheduling may add delay. Prolonged
reader drains cause periodic writer wakeups. No new throughput, tail-latency,
fairness or broad callback claim is made; historical timings are not relabelled.

## Checks and failures

All compilation and live checks ran serially in the established VM. The source
host performed edits, Git and read-only archive verification.

| Check | Actual result |
| --- | --- |
| Pinned dependencies and two basic programs | Passed; two programs, zero failures. Expected negative-fixture diagnostics remain ordinary test output. The encompassing inspection shell later returned 2 for deliberately absent candidate installation paths; that is not a test exit status. |
| Five uninstrumented production lock objects | Passed with W=1; subsequent harness attempts reused these exact objects after matching generated inputs, commands, kernel identity, BTF base and object hashes. |
| Native/KD standalone adapter probe `check-4` | **352 assertions, zero errors**; six context cases, six concurrent-reader cases, 15 writer-drain cases, three cancellation cases and three forced rollback cases; zero observed atomic-context wake callbacks; final idle and normal unload. |
| IRQ/preemption contexts | IRQ enabled, IRQ disabled and preemption disabled; uncontended success, writer-held refusal and exact state preservation. KD unlock is also exercised inside atomic context. Native unlock restores its permitted context first. |
| Writer progress/exclusion | Native ordinary/killable and KD ordinary/interruptible/killable writers; sleeping writer, late-reader exclusion, last-reader release, payload visibility and final cleanup. Native 6.1 has no `down_write_interruptible`; the three additional writer cases and one additional cancellation case are KD-only. |
| Forced read rollback | A test-only wrapper around the real reader increment injects exactly the writer's `0 -> -1` reservation before recheck. All three contexts roll back to zero readers; synthetic reservation and observer are retired. This is a controlled interleaving, not a timing measurement. |
| Existing full shared-rwsem probe | Provider and probe built, but provider load **failed**: reserved per-CPU allocation could not supply 7,592 bytes. Its init did not run and no provider remained loaded. This runtime regression is not a pass. |
| Disabled-config compatibility | Reused the prior four-object/fixture/partial-link result; all 12 recorded inputs match. The disabled wrapper patch and layout inputs did not change. No disabled runtime claim. |
| kdmm31 image and module closure | Image and 73 matching signed modules installed; allocated ELF sections and split BTF match the built outputs. All 73 modules plus the prebuilt probe parsed against the exact base. The initramfs contains 49 byte-identical boot modules. |
| Actual-mm Native mode | **137 assertions, zero errors**, final idle and normal unload; boot `2e18270d-cf6c-4e8d-868d-69659d239f46`, `kd_mmap=off`. |
| Actual-mm KD mode | **161 assertions, zero errors**, final idle and normal unload; boot `941c85d6-00d5-44d6-9e57-fb5e2c241afd`, `kd_mmap=on`. |
| Native MM preservation | Six native mmap, memory, advice, reverse-map, Maple Tree and x86-fault source files match recovery exactly. |

`check-1` failed on a harness reference to nonexistent Native
`down_write_interruptible`; `check-2` failed on builtin boot declarations under
module preprocessing; `check-3` failed modpost because builtin I/O scheduler
helpers are not exports. `check-4` uses the existing module resolver for those
helpers and passes. No native symbol was exported or stubbed. The test-only
adapter selects policy at initialization and operates on standalone adapter
objects, not actual mm objects. Source/ELF bindings and all failed diagnostics
remain in the essential archive.

The actual-kernel module build initially reproduced the historical `serio_raw`
double traversal: module and builtin compilations wrote the same object/command
file, followed by modpost failure. An exact-directory attempt then diagnosed the
corrupted command file. Its bytes and failed object were preserved before that
one generated command file was removed; the single exact-directory target then
built successfully. The other 72 successful modules were reused. No module
license, symbol or BTF check was disabled. Image build also retains the three
previously documented x86 objtool warnings; successful exit does not erase them.

The extra preboot BTF inspection first failed when system libbpf 0.5.0 returned
`-EINVAL` parsing the candidate base. No boot occurred at that point. The existing
pahole 1.25 parser then successfully read the base and all 74 split-BTF inputs;
no BTF data or admission check was changed. Its commands, zero statuses and empty
diagnostics are retained in `resume-preboot.tar.gz`. The first checker source and
diagnostic remain recorded; that failed inspection is not a pass.

## Candidate identity and runtime validation

- Release: `6.1.159-kdmm31`.
- Build ID: `ef5179e8def44f0255adcd62585f62f118fee30f`.
- Image SHA-256: `17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040`.
- Base BTF SHA-256: `6fb6b4d74442e1e36636392a3b551a246788f0cd231cd9f1729b6f5a58e90fdf`.
- Configuration SHA-256: `67d4c96cfd29f657d642c5ffe969a9215892c0209125dfe83f283873b366ae01`.
- Initramfs SHA-256: `fbc72a78911ab1f07f3892bad720ad56e57d36311bbe8af63b43f41fca1a7fa3`.
- Probe SHA-256: `6339c3d92082b6b6d45adaa6f4921c9b2794db5b4e45e250cc65466123152a5b`.
- Original private tree: `/dev/shm/kd-mmap-irq-20261025/linux`; persistent receipts:
  `/root/kdlock-kernel-work/mmap-irq-20261025/candidate-1`.
- Captured bundle: `/root/kdlock-kernel-baselines/mmap-kdmm31-irq-20261025`.

The 5,820,383,232-byte kdmm1 tree was privately copied with 8,183,332,864 bytes
of temporary space and 3,699,806,208 bytes of persistent space available. Four
compiler jobs were used. Only three generated lock files differ; configuration
changes only the distinct release relative to kdmm1. The original kdmm1 source,
configuration and 11 captured build files remain verified and untouched.

The resumed preflight rechecked the original boot ID, exact candidate/recovery
hashes, all 73 loaded modules, source/test ownership and real recovery snapshot
`before-mutex-kdonly-20261017T140354Z`. All 9,166 old volatile entries, 102,993
candidate entries and its full kdmm1 reconstruction base matched their preserved
contents and metadata. Archive hashes also matched. Persistent free space was
3,771,551,744 bytes before preserving 796,711,603 bytes of runtime identity inputs;
2,974,515,200 bytes remained before installation. No unique data was deleted.

Installation retained the recovery default and added distinct Native/KD entries.
The same image, configuration, installed modules, initramfs and prebuilt probe
were verified before both serial actual-mm runs. Each boot used 64 CPUs, nodes
0–31/32–63, voluntary preemption, `nokaslr` and `nopvspin`. Both loaded the same
68-module subset; `intel_uncore_frequency_common`, `nfit`, `nfnetlink`,
`skx_edac_common` and `tls` from the 73-module build closure were not loaded in
either candidate boot. No claim is made that these five ran on kdmm31.

The actual-mm payload checks read trylock success and writer-held refusal with
IRQs enabled, IRQs disabled and preemption disabled, preserving the exact state.
KD matching unlock executes inside each context; Native release restores its
permitted task context or uses its exact asynchronous token. KD reader workers
also release with IRQs off while a real writer drains. Both results include eight
API cases, distinct-mm nesting, three cancellation cases, two sleeping readers,
one sleeping writer, one excluded late reader, downgrade, exact transfer,
destruction and final idle. Native MM bodies remain unchanged on their original
task. The controlled speculative rollback check remains standalone evidence.

The runner's `--reuse-probe` verifies exact payload source/ELF, kernel ELF and
live BTF bindings before copying the binary into each frozen result. Both runs
record `basic_programs=0`: the two basics and 352 standalone assertions already
passed and were not repeated. Kernel logs and post-unload health contain no
fault matches. Candidate taint was 4096 before the probe and 12288 afterward;
the test module was unsigned and unloaded normally. The runner leaves its
`accepted` field false; `passed=true` and `drained=true` record the completed
correctness checks. No performance acceptance is claimed. The failed shared-provider
allocation remains unresolved and is not covered by these built-in results.

## Preservation and final state

The initial rejection left candidate installation paths absent; the approved
resume installed them. Candidate boot files, modules and GRUB entries remain
available, with no pending one-shot boot. Recovery is again
`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`. All 73 original modules are loaded after
restoring optional `nfnetlink` and `tls`; no test module or active project worker
remains. Taint is zero, there are no failed systemd units or kernel fault matches,
and the 64-vCPU/two-node/voluntary policy is intact. Recovery boot files and all
5,686 retained module files match; only GRUB's menu gained candidate entries.
Final recorded free space: root 2,935,193,600 bytes; temporary RAM filesystem
12,613,750,784 bytes. The data disk remained at 10,031,104 bytes free.

The unrelated `vm-disk-cleanup-20261022/README.md` edit is untouched. Historical
MM bodies, experiments, kdmm1, recovery artifacts and failed receipts remain
reachable. The approved reboot cleared the old `kdmm30-cow`, `kdmm30-identity`,
interrupted `kdmm30-vmlinux.xz` and candidate temporary paths. Their verified
archives retain the exact contents. The candidate's `runtime-identity` directory
persists with all 44 captured source files, 11 build files and configuration;
it supports identity verification but is not a complete build tree. Reconstruct
the full build from the unchanged kdmm1 base, the delta and its two recorded
removed dependency files, then the preserved post-install `modules.order` change
before using installed candidate build/source links. No new build is implied.

Essential evidence is under `raw/tests/mmap-irq-trylock-20261025/`:

- [Standalone result](../../raw/tests/mmap-irq-trylock-20261025/check-4.json),
  [initial safe-stop health](../../raw/tests/mmap-irq-trylock-20261025/final-health.json),
  [installation rejection state](../../raw/tests/mmap-irq-trylock-20261025/install-denial-state.json),
  [disabled reuse](../../raw/tests/mmap-irq-trylock-20261025/disabled-reuse.json).
- [Actual Native result](../../raw/tests/mmap-irq-trylock-20261025/actual-native-1.json),
  [actual KD result](../../raw/tests/mmap-irq-trylock-20261025/actual-kd-1.json),
  [restored recovery](../../raw/tests/mmap-irq-trylock-20261025/resume-final-health.json).
- `resume-preboot.tar.gz`: 31,745,633 bytes; SHA-256
  `5a7f5713ab73b0647d516cccccd2d35562c6472e9621bf6abc08cd3e1e920c46`.
  Its 177 entries retain verified boot files, installation/BTF/initramfs receipts
  and the exact post-install `modules.order` delta.
  [Review](../../raw/tests/mmap-irq-trylock-20261025/resume-preboot-review.json).
- `actual-runtime.tar.gz`: 1,578,144 bytes; SHA-256
  `d069cf167d2597e9784d3a0030ffaf6283e93f989e2ba5150d5a5773f070af9a`.
  Its 570 entries retain both results, 230 frozen source bindings per mode,
  identical probe ELFs, command receipts, kernel logs and idle endpoints.
  [Review](../../raw/tests/mmap-irq-trylock-20261025/actual-runtime-review.json).
- `essential.tar.gz`: 2,556,038 bytes; SHA-256
  `d6e785c320382ad4ae4f8ad1a8e3d659aa4c81086db508a6090be09d08c81cca`.
  Its 226 entries retain commands, failed diagnostics, source bindings and probe
  binaries; [review scope](../../raw/tests/mmap-irq-trylock-20261025/essential-review.json).
- `kdmm31-delta.tar.gz`: 1,053,929,601 bytes; SHA-256
  `cde7ad43033ea25812ec608482200e754b56ccb271a88b48665c89918630cf16`.
  All 779 changed entries verified against the full base/delta manifest; the
  unchanged kdmm1 tree supplies the remainder. [Review](../../raw/tests/mmap-irq-trylock-20261025/new-archive-review.json).
- `volatile-kdmm30.tar.gz`: 1,566,105,936 bytes; SHA-256
  `9c3b7ffb744b8221c59c573ecfd0921fea7318ab41315d322cecd2a604793400`.
  All 9,166 entries, including 8,814 regular files, verified with contents,
  permissions, ownership, timestamps, links, device IDs and xattrs.
  [Review](../../raw/tests/mmap-irq-trylock-20261025/old-archive-review.json).

No full-suite or performance result is reported. Full shared-provider runtime,
end-to-end BPF lookup, RT, lockdep and whole-kernel
semantic equivalence remain outside the obtained proof.
