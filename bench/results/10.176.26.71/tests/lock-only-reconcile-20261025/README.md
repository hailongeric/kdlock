# Lock-only runtime evidence reconciliation

**Completed: reuse the verified kdmm1 runtime evidence. No new build, live test,
module load, installation or boot was needed.** The restored lock-only source at
`b8c2d1f55fa9437d46140cb5875be9fab248f743` matches the preserved artifact's inputs
and prepared outputs. This closes the cleanup's runtime-evidence question for
the existing focused scope; it does not establish general Linux equivalence.

Native MM operations still run on their originating tasks. No mapping algorithm,
page classification, prepared teardown or MM-body delegation was added. The
unrelated disk-cleanup README change remains untouched.

## Identity and compatibility

| Binding checked read-only | Result |
| --- | --- |
| Current lock-source and overlay inputs | All 15 hashes match kdmm1 preparation |
| Preparation script, nine-file patch and base-file manifest | All three match exactly |
| Outputs retained from cleanup `check-1` | All 24 generated/patched files match kdmm1; no regeneration or compilation |
| Preserved kernel tree and bundle | All 44 captured source files, 11 build outputs and five bundle files match |
| Native MM bodies | `mm/mmap.c`, `mm/memory.c`, `mm/madvise.c`, `mm/rmap.c`, `lib/maple_tree.c` and `arch/x86/mm/fault.c` match recovery |
| Configuration | Only `CONFIG_KD_MMAP_LOCK=y` and local version `-kdmm1` differ from recovery |
| Installed artifacts | All 90 recorded image/configuration/initramfs/module/metadata hashes match; exactly 73 installed modules |
| Module compatibility | All 73 report `6.1.159-kdmm1 SMP preempt mod_unload modversions` and the recorded build-time signing identity |
| Initramfs, the early-boot filesystem image | Hash and complete listing match installation; its 49 modules belong to the verified installed set |

The captured compiler is **GCC 11.4.0**, Ubuntu package
`11.4.0-1ubuntu1~22.04.3`, with **GNU ld 2.38**. The exact artifact identities are:

- Build ID: `687ff5a29315d732f93a618e50ac407c794bbf9b`.
- Image SHA-256: `cb82b0d1ccf3c2b5ce27571783fa2001d7b971d8f36ff1316c114972ff354f0d`.
- Kernel manifest SHA-256: `3243e17005ed55c83af417ed3979ca9e89c077b89fcacd99dab5ae117c06b34b`.
- Initramfs SHA-256: `cbedc084770d27237e35f8c87260d211becb7209bc0365aae270164055ea4e98`.

The version name alone was not used as an identity check. The eight reused run
records match their archived originals, the same captured kernel manifest and
their retained probe binaries. Selected probe/source bindings were checked;
archived code was not executed and the previous full archive audits were not
repeated. No new archive was created.

The only changed source among the selected historical runner inputs is
`tests/kernel/mmap_lock/mapping.py`: it later gained an explicit writer-site
manifest option and preservation checks. The default manifest, actual payload,
writer proof and kernel inputs remain unchanged. Historical results retain their
original runner identity; they are not presented as fresh execution of that edit.

## Reuse and gap matrix

All Native/KD counts below are historical, matched-artifact results from the
[original focused validation](../mmap-kd-kernel-20261021/README.md).

| Wrapper/backend behavior | Reusable evidence | Disposition |
| --- | --- | --- |
| Actual-mm backend selection; read/write acquire/release and trylock; exact writer identity | `native-api-3`: 121 total assertions; `kd-api-1`: 139, both zero errors | Reuse |
| Concurrent sleeping readers, blocked writer, late-reader exclusion and final queue drain | Same API runs: two readers, one writer and one late reader observed sleeping | Reuse |
| Fatal-signal cancellation in reader, writer and reader-drain waits | Three cancellation cases per API run; nonfatal signal does not cancel | Reuse |
| Nested locks on distinct mm objects and writer-to-reader downgrade | One nested and one queued-downgrade case per API run | Reuse |
| IRQ-disabled trylock refusal, exact deferred read-token transfer and final destruction in process context | API runs exercise all three, with worker completion and normal unload | Reuse; end-to-end BPF lookup workload remains untested |
| Native mapping lifecycle and originating-task writer route | `native-mapping-2`, `kd-mapping-1`: six cases and 81,000 cycles each, no payload faults, nine corrupt-proof rejections | Reuse |
| Fork, copy-on-write, remote-mm access, exit, fault retry and VMA revalidation | `native-faults-2`, `kd-faults-1`: 16 lifecycle plus 16 userfault retry cases each | Reuse |
| Fault-completed implicit lock release and subsequent write-lock acquisition | `native-completed-1`, `kd-completed-1`: 64 entries/returns/completed results each, persisted bytes verified | Reuse |
| Restored patch, five lock objects, basic programs and unified mutex facade | Cleanup `check-1`: patch/object checks, two basic tests and one API driver passed | Reuse; no changed inputs justify repetition |

There is no uncovered check newly required by this restoration within the selected
configuration and 73-module runtime. The 1,440 historical recovery-initramfs
modules not rebuilt for kdmm1, all filesystem/device fault callbacks, an end-to-end
BPF lookup workload, a `CONFIG_KD_MMAP_LOCK=n` rebuild, RT, lockdep and whole-kernel
replacement remain outside the validated scope. These are limitations, not
implicit passes. Broader races, performance, p95 and the seven mutex investigations
remain deferred. Existing historical build/probe failures remain preserved.

The subsequent [disabled-configuration object/link check](../mmap-disabled-build-20261025/README.md)
closes the affected-wrapper compile/link gap without changing production code.
A full disabled kernel build and runtime validation remain unperformed.

## Records and reproduction

New evidence is limited to read-only reconciliation receipts:
[result](../../raw/tests/lock-only-reconcile-20261025/result.json),
[source match](../../raw/tests/lock-only-reconcile-20261025/source-match.json),
[artifact hashes](../../raw/tests/lock-only-reconcile-20261025/artifact-identity.json),
[compatibility](../../raw/tests/lock-only-reconcile-20261025/compatibility.json),
[runtime reuse](../../raw/tests/lock-only-reconcile-20261025/runtime-reuse.json)
and [final health](../../raw/tests/lock-only-reconcile-20261025/final-health.json).
The original archives remain at
`raw/tests/mmap-kd-kernel-20261021/correctness-archives-1/`; only the three relevant
kernel/Native/KD archive hashes and selected bindings were inspected.

For a future read-only identity recheck in the idle guest, without booting kdmm1:

```sh
cd /root/host_fs/kdlock
python3 - <<'PY'
import hashlib, json, runpy
from pathlib import Path
b = Path('/root/kdlock-kernel-baselines/mmap-kdmm1-20261021')
k = Path('/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux')
print(runpy.run_path('kernel_baseline/verify.py')['verify'](b, k, build=True))
p = json.loads((b / 'prepare.json').read_text())
inputs = dict(p['inputs'])
for name, key in [('prepare.py', 'script_sha256'),
                  ('guest-kernel.patch', 'patch_sha256'),
                  ('base-sha256.json', 'base_manifest_sha256')]:
    inputs['kernel_integration/mmap_lock/' + name] = p[key]
for name, expected in inputs.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
installed = Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-kd-kernel-20261021/install-1/installed-sha256.json')
for name, expected in json.loads(installed.read_text()).items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
print('Source inputs and installed artifacts match; no runtime test performed.')
PY
```

No source synchronization, installation or configuration change occurred. The VM
remained idle on recovery `6.1.159-kdclobber2`, boot
`1602542f-b2ec-4f6b-b67d-db89dee83137`, with its 73 expected runtime modules, no
test modules and no pending boot. The host checkout observation found no visible
writable descriptor; 544 of 609 observed processes were inaccessible or vanished,
so that snapshot has bounded visibility. No process was interrupted.
