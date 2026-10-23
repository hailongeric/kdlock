# Resident partial munmap correctness

The `kdmm8` milestone passed 23 serial cases in the existing MM VM, including
seven different-task resident partial removals and six delegated post-split
errors matched to native controls. See the [scope and execution flow](../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
and the [single result record](../../../../bench/results/10.176.26.71/tests/mm-resident-partial-20261023/README.md).
The correctness-only module remains in `../unmap_body/payload/`; its
`resident.inc` supplies observation and queue controls, not an alternative body.
Real `munmap`/`vm_munmap` calls execute the in-tree native split/unmap helpers.

## Reuse the installed image and probes

From `380G10`, with sole ownership of the test slot and the guest idle:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-resident-partial-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-resident-partial-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence; choose the next unused number. These commands
verify the real snapshot and original host placement, boot the installed image
once, run the cases serially and restore recovery. Run recovery only after the
test command has passed and drained. On failure, inspect live workers and retain
evidence; a timeout is not drain. Never force unload or reboot an active test.
The default recovery entry and VM configuration stay unchanged.

Do not rerun `prepare`, `build` or `finish` for unchanged tests. The recorded
build compiled one new client and four modules; five clients were reused.
`finish` only completed a failed packaging step from the existing outputs.
Collection is separate and optional, not automatic after each run.

Guest stage root:
`/root/kdlock-evidence/10.176.26.71/tests/mm-resident-partial-20261023`.
`control/focus.py --build-attempt 2 --run focused-N` is the frozen driver;
`control-2/transition.py` handles verified transitions. Probes are in `probes-1/`.
The driver records each case's `client.json`, `kernel.log` and negative receipt
controls in `focused-N/`, with one aggregate `result.json`. The source-host
transport receipts are under
`bench/results/10.176.26.71/raw/tests/mm-resident-partial-20261023/`.

The baseline is `/root/kdlock-kernel-baselines/mmap-kdmm8-20261023`.
The small persistent identity snapshot is
`/root/kdlock-kernel-work/mm-resident-partial-20261023/identity`; its one new ELF
is compressed at `/mnt/kdlock-builds/mm-resident-partial-20261023/vmlinux.xz`.
Transitions expand verified regular files into `/dev/shm/kdmm8-identity` for
strict identity checks. Recovery reboot removes that RAM copy. The snapshot is
not a full kernel module build tree; changed sources require a new verified
incremental workspace, never edits to frozen inputs.

## Cases and proof

The driver runs these 18 new cases, then five preservation smokes:

| Client arguments | Checks |
| --- | --- |
| `error native\|kd untouched prefix\|suffix 1` | Error after the successful edge split; same native return and surviving layout. |
| `error native\|kd untouched middle 1\|2` | Error between the interior splits and after both; all pages retained, no local replay. |
| `error native\|kd resident middle 1\|2` | Same errors with exact reverse-map ownership, page references and retained bytes. |
| `resident prefix\|suffix\|middle` | Three operations per shape, two executed by another task; absent target and intact survivors. |
| `resident refusal` | Busy third page, release of two earlier holds, exact handback/ACK and subsequent sticky-local call. |
| `resident cancel` | Queued fatal cancellation returns `-EINTR` before effects; victim mapping/resources preserved. |
| `resident free` | Test references dropped before real removal, including one remote body; no freed-page dereference. |

The vertical bars above denote alternatives, not shell pipelines. Native error
controls disable delegation and invoke the ordinary native body on the same KD
lock backend; this is not a separate Native-off boot. The five smokes reuse the
untouched interior, unpopulated whole-VMA, four-page resident whole-VMA, advice
and separate anonymous first-write fault clients. Prior single-page final-free,
two-/three-page whole-removal and other historical evidence remains referenced,
not repeated.

A VMA (virtual memory area) describes a mapping interval. Reverse-map links
connect physical pages to their VMAs. Every remote receipt matches the original
mm, request, range and task to a different executor, then pairs split completion,
physical page identity and generic completion. Prepared-object retirement tracks
which descriptors/links transferred into VMAs and which the origin freed.
Exact reverse-map root counts and retained links, page references/locks/charges,
mapping bounds/flags/offsets and mm accounting must match. All survivors retain
their full-page patterns. Origins warm their TLB (cached address translation)
before removal and verify the hole on the same CPU afterward. Two readers remain
local and concurrent; a real retained-neighbor fault waits for writer release.

ACK means acknowledgement of the exact handed-back request and owner, not a
successful delegated body. Local heads, fallback, cleanup and injection errors
are excluded from successful remote-removal counts. The 110 negative receipt
controls corrupt copies of real live records and require rejection; they are
not additional live executions. All requests and test references must retire,
all mappings must be cleaned up, and modules must unload normally.

Live resident coverage is one page from exactly three ordinary resident pages,
with one reverse-map link and retained page tables. Untested cases and explicit
fallback restrictions are listed in the scope guide. No performance, broad
campaign, full historical suite or general mmap-support claim follows from this
milestone.
