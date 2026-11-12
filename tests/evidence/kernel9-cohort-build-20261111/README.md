# Kernel9 writer-cohort correction: build result and runtime block

Corrected core `6e486ece` compiled and linked successfully as
`7.0.0-38-kdrebuild9`, Build ID
`8198ffae09db584dce9b71d92b5743a4146ba80a`. The changed mutex object, full
kernel image and single NLS module all returned zero. All twelve recorded
commands completed; the outer observer returned zero after 397.35 seconds.
Kernel9 was not installed, booted or runtime-tested.
[Build receipt](collection/payload/receipts/build-01/result.json.gz),
[linked identity](collection/payload/receipts/build-01/final-identity.json),
[saved-byte audit](audit.json)

Only `kernel/mutex.c` differs across the 78 core inputs from kernel8. Cohort
await validates the exact published batch identity and permits its predecessor
to initialize that storage. The prepublication initialized checks and ordinary
sleepable rejection remain, with existing selection, physical ownership and
retirement checks intact. The linked await branch selects the identity check
at `0xffffffff8150b202`; success continues at `0xffffffff8150b092`, beyond the
ordinary initialized-byte rejection. Acquire still checks initialized before
calling enqueue. This is source/disassembly evidence, not executed queue
ordering or a deterministic reproduction of the failed timing window.
[Changed source](collection/payload/source/mutex.c),
[linked await](collection/payload/receipts/build-01/kd_mutex_await-disassembly.log),
[linked acquire](collection/payload/receipts/build-01/kd_mutex_acquire-disassembly.log),
[earlier failure and source review](../kernel8-mm-step-failure-20261111/README.md)

The independent source/output tree is
`/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01/{source,build}`. It copied
the already integrated kernel8 source and changed only the reviewed mutex
file; the installer was not reapplied. The config remained SHA-256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The focused object took 52.81 seconds; bzImage took 296.54 seconds; NLS took
4.02 seconds. These are build durations, not lock performance measurements.

The mutex-object and NLS logs contain no diagnostic records. The full kernel
log has 54 warning lines: 22 compiler records (one maple-tree frame, one unused
variable and twenty fortify fixture diagnostics), 26 objtool records, and six
locale-warning lines. Objtool reports handwritten returns, an indirect call,
function fallthrough and stack realignment; complete mitigation/unwind coverage
remains unproved. Olddefconfig adds one Kconfig multiline-string warning.
The original driver's diagnostic field counted only the 22 compiler rows;
its raw receipt is unchanged, and the saved-log supplement identifies every
omitted objtool/locale row. Three warning/error strings in the focused build
are echoed shell recipes, not emitted diagnostics.
[Complete warning classification](warning-supplement.json),
[original receipt](collection/payload/receipts/build-01/result.json.gz)

Before and after checks retain kernel8's 16 output identities, all 78 core
files, eight integration files, eleven native MM bodies and the normal source,
boot/default files and module namespaces. The guest stayed on normal
`7.0.0-38-kdlock1`, boot `f1442f01-e060-46fa-a480-da508d7ce8a9`, taint 0.
Final workload and D-state lists were empty. The build ended with
40,974,196,736 bytes free on the output disk. The failed-run snapshot and
existing recovery tag were verified on all three disks before the build.

Runtime validation is **blocked**. Platform content review stopped the
delegated rwsem module/build-and-run helper preparation as a possible
cybersecurity risk before any VM command from that task. The task was not
retried or recreated through another route. The separately reviewed kernel
build was already running and was allowed to finish. No private fixture module
build/load, corrected-kernel boot or additional mmap workload followed.
[Platform review stop](controls/platform-review-stop.json)

The earlier exact 143-file private-rwsem source preparation remains unrun with
fresh runtime bindings absent. The install-only draft is incomplete, unpeered
and unconditionally refuses dispatch; missing dependencies and source work are
listed in its status. Neither preparation establishes validation. The next
intended runtime scope was the existing private rwsem fixture only; it would
exercise cohorts and lifetimes but would not force this race deterministically.
[Unrun private preparation](unrun/private-rwsem-preparation/README.md),
[incomplete install draft](unrun/install-preparation/STATUS.md)

All 53 copied guest files, their complete transfer, source/control provenance,
changed object, linked disassembly, bzImage and public certificate are retained.
The full vmlinux remains at the guest path with its exact size/hash in the linked
identity. No private signing-key bytes are copied. Larger members use lossless
gzip with raw/stored hashes. Standard-library saved-byte checks verify every
transport member, command log and protected identity; no project test ran on
the source host. [Copy provenance](copy-index.json), [checksums](SHA256SUMS)
