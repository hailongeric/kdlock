# Linux 7 MM campaign controller

`linux70_mm.py` runs on 380G10 after the lock/API campaign drains. Its guest
runners, builds, correctness checks and timing run only in the designated VM.
The controller never builds, installs or boots a kernel. Its original focused
checks passed in the VM. The
[current campaign](../results/10.176.26.71/bench/catalog-linux70-mm-trusted-20261027/README.md)
has completed all 84 private-suite points. Shared timing remains pending after
a failed KD contention witness; the
[enabled-MM checkpoint](../results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
records its completed operations, failed verdict and separate normal cleanup.
Diagnostic and controller error-reporting changes require their own affected
VM checks and a separate source generation.

The fixed plan has 84 private-suite points (21 untouched Native mmap/munmap,
63 private-backing fault cycles) and 42 actual shared-mm points (21 Native,
21 KD). Every point uses one two-second plain round, workers 1–8 and 12–60 by
four, and collector CPU63. The shared suite has no TCLock arm. Neither MM suite
delegates native MM operation bodies; private fault readers execute locally.

First synchronize the reviewed inputs while idle and finish the focused checks
in [the MM runner plan](../mmap_fault/LINUX70_PLAN.md), including
`bench/catalog_single/test_linux70_mm.py`. No authored test is a passing check.
Confirm recovery, the exact kernel identity and a fresh boot UUID. Invoke the
controller from the source checkout:

```bash
MM_CAMPAIGN=catalog-linux70-mm-20261027
MM_BASE=/root/kdlock-evidence/10.176.26.71/bench/$MM_CAMPAIGN
MM_ARGS=(--campaign "$MM_CAMPAIGN" --guest-base "$MM_BASE"
  --mode private --boot-id "$MM_BOOT" --snapshot "$MM_SNAPSHOT")
python3 bench/catalog_single/linux70_mm.py private-prepare "${MM_ARGS[@]}"
python3 bench/catalog_single/linux70_mm.py private-measure "${MM_ARGS[@]}" --suite independent-mmap
python3 bench/catalog_single/linux70_mm.py private-measure "${MM_ARGS[@]}" --suite private-fault
```

The controller retains an exact `raw/.../inputs/` copy and hashes of the selected
working-tree sources and verifies
every byte against the actual guest checkout after synchronization. It records
the Git commit and dirty status separately; dirty source is never described as
the commit's contents. Subsequent phases require the same selected source bytes.
Do not edit frozen inputs. Native/KD split correctness, then TCLock split
correctness, eight plain preparation controls and nine negative oracles must
pass before either private timing grid can run.

Every live phase takes a fresh schema-2 2.0 GHz host capture and uploads those
exact bytes with a hashed reference. Permanent QEMU task identities, affinities,
NUMA bindings and frequency policy must remain unchanged. Only literal auxiliary
`worker` creation/retirement on CPU63 is allowed, under explicit exploratory
qualification. APERF/MPERF telemetry and host endpoints remain separate from
the configured frequency. Rates never become strict timing qualification.

Each phase retains its command, stdout/stderr, boot/idle observations, host
captures, telemetry, full guest tree archive and complete file/hash inventory.
Archive extraction rejects unsafe paths, duplicate/omitted members and changed
bytes. Symlinks stay in the archive and are not materialized on 380G10. Source
and binary checks still gate publication. Out-of-tree/unsigned taint bits are
recorded; other taint changes or kernel faults fail qualification.

After each measured suite, tables and charts appear under
`bench/results/10.176.26.71/bench/$MM_CAMPAIGN/<suite>/`.
Shared-mode tables also feed a combined `shared-mm` chart only when the exact
image/source identities match. Raw receipts are under the parallel `raw/bench/`
tree. Every missing, failed or unqualified point stays visible without an
accepted throughput value. No error bars or repetition variance are invented.

For the shared suite, follow the separate kernel build/boot procedure in the
[identity guide](../../kernel_integration/linux70/IDENTITY.md). After each
explicit mode boot, set `MM_MODE` to `native` or `kd`, use its boot UUID and
confirmed recovery snapshot, then run:

```bash
MM_ARGS=(--campaign "$MM_CAMPAIGN" --guest-base "$MM_BASE"
  --mode "$MM_MODE" --boot-id "$MM_BOOT" --snapshot "$MM_SNAPSHOT")
python3 bench/catalog_single/linux70_mm.py shared-sites "${MM_ARGS[@]}"
# Review the retained exact ELF writer-site receipt and set its SHA256:
python3 bench/catalog_single/linux70_mm.py shared-correctness "${MM_ARGS[@]}" \
  --writer-sites-sha256 "$MM_WRITER_SHA"
python3 bench/catalog_single/linux70_mm.py shared-prepare "${MM_ARGS[@]}"
python3 bench/catalog_single/linux70_mm.py shared-measure "${MM_ARGS[@]}"
```

Prepare Native first. KD preparation automatically reuses the preserved Native
timed artifacts and requires the same image. Measurement needs both successful
preparations, including their one/sixteen-worker controls and eleven negative
mutations. Both modes also require API, mapping, fault and completed-fault passes
from the current boot. After returning to a mode on a different boot, repeat
`shared-sites` and `shared-correctness`; the earlier exact-image preparation may
be reused. No mode is inferred from the currently supplied bundle.

A failed phase stops execution. A timeout leaves transport and guest completion
unconfirmed; it does not establish drain or authorize more live work. No task
is force-unloaded. A completed prerequisite is reused only after rechecking its
preserved archive and named bytes. A STOP file in the campaign's raw directory
stops at the next drained phase boundary.

For a measured grid interrupted after confirmed completion and normal drain,
an operator may author a reviewed continuation JSON and pass both
`--resume-review FILE --resume-sha256 SHA256`. It must contain `schema: 1`,
`approved: true`, `purpose: "resume-unmeasured-mm-coordinates"`, the exact
`campaign`, `suite`, `context` and `source_manifest_sha256`, and all
`prior_attempts` in order. Each attempt binds `name`, `result_sha256`,
`archive_sha256`, `preservation_sha256`, `session_receipts` and
`attempted_coordinates` from `phases.json`. `coordinates` must equal the original
ordered grid minus every previously attempted coordinate.

The controller counts retained session directories, including empty ones, and
START announcements as attempts; a failed or partly timed coordinate is never
rerun. Unknown directories or completion stop continuation. The guest dispatcher
rechecks every prior source/workspace/phase byte against its full inventory and
only narrows the maintained runner's plan. All original admission, callback,
ownership, data, runtime identity and normal-drain checks still execute. A
continuation cannot repair or hide a failed point, change a boot/source identity,
or replace an unknown-completion diagnosis.
