# Untouched anonymous partial munmap correctness

The later [resident-partial guide](../resident_partial/README.md) records `kdmm8`
resident support and post-split failure injection. This guide retains the
completed `kdmm7` untouched baseline and its original coverage limits.

The `kdmm7` milestone passed five partial-unmap cases and five preservation
smokes serially in the existing `10.176.26.71:2222` VM. The new cases exercise
prefix, suffix and interior removal, including VMA (virtual memory area)
splitting, resident refusal with sticky local fallback, and queued cancellation.
The [scope guide](../../../../kernel_integration/mmap_lock/UNMAP.md) explains
caller preparation and ownership; the [single result record](../../../../bench/results/10.176.26.71/tests/mm-partial-unmap-20261023/README.md)
binds sources, build/boot identities, logs and limitations.

This client uses the existing unmap probe's reader/queue controls and a local
read-locked query for exact VMA bounds and mm accounting. The module supplies
no replacement body. Real userspace `munmap`, or `vm_munmap` for cancellation,
reaches the shared in-tree split/adjust/removal helpers. Readers stay concurrent
and local. Every counted remote completion must identify the original mm, range,
request and task, and a different executing task. Local head execution, fallback,
cleanup and synthetic callbacks do not count as remote bodies.

## Reuse the installed kernel and frozen probes

From `380G10`, with sole ownership of the VM test slot and an idle guest:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-partial-unmap-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-partial-unmap-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence. Use the next unused attempt number. Run recovery
only after the test command passes and drains. A timeout does not establish
drain: retain the failed state and loaded module, inspect live workers, and never
force unload or reboot an active operation. The helper verifies the real recovery
snapshot and host placement, selects the installed `kdmm7` image for one boot,
and restores the original recovery entry. It preserves the VM configuration.

The workflow reuses four unchanged client binaries and the four modules built
for this kernel. It runs the five partial cases, whole unpopulated removal,
four-page and single-page resident removal, advice, and the separate first-write
fault workload in one serial stream. Do not rerun `prepare` or `build` for an
unchanged rerun. Collection is optional and separate; it never runs automatically
after each case. The pinned guest environment and all identity/admission checks
are retained.

Guest stage root:
`/root/kdlock-evidence/10.176.26.71/tests/mm-partial-unmap-20261023`.
The frozen driver is `control/focus.py`; binaries are in `probes-1/`; the next
results would be `focused-2/<case>/{client.json,kernel.log}` and
`focused-2/result.json`. Source-host transition and result receipts go to
`bench/results/10.176.26.71/raw/tests/mm-partial-unmap-20261023/kd-2/`.
Existing output directories are refused.

Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm7-20261023`.
The persistent identity snapshot at
`/root/kdlock-kernel-work/mm-partial-unmap-20261023/identity` stores the new
kernel ELF compressed once. The transition expands it and the small captured
files into `/dev/shm/kdmm7-identity` as regular files for the unchanged strict
identity checks. Recovery reboot removes this RAM copy. This is an identity
snapshot, **not a complete kernel module build directory**. Future source changes
need a new verified incremental build workspace, never edits to frozen inputs.

## What the cases prove

- `prefix`, `suffix`, `middle`: 16 isolated untouched three-page mappings per
  case, one page removed from each. Fifteen requests execute on a different task.
  The removed address must be absent and raise `SEGV_MAPERR`; retained VMA bounds,
  flags, offsets and zero-filled contents must match, and later pattern writes
  must read back correctly. Exact total/data/stack/exec page counts, VMA counts
  and page-table bytes are checked while worker stacks remain mapped. A real
  later hardware fault blocks behind writer admission and sees the removed hole.
- `refusal`: a healthy local head, then a resident partial request with one exact
  handback/ACK (acknowledgement), then a sticky-local request. Surviving resident
  bytes retain their patterns. The original CPU's warm translation is invalidated
  by the fallback's native removal. The refused request consumes neither prepared
  split descriptor.
- `cancel`: a healthy head completes; a queued victim returns `-EINTR` before
  splitting and retains its complete mapping. Both unused descriptors retire.

The client checks every remaining target/neighbor mapping and performs 159
explicit local cleanup calls across these five cases. Completion/retirement
receipts account for all 112 prepared descriptors, including the first cleanup
preparation before that entry becomes sticky-local. Exact queue retirement and
ordinary module unload are required. Six receipt-control tests reject corrupted
execution, range, accounting, ACK, object identity, cancellation and reader/fault
evidence; they do not replace the live checks.

Only untouched whole VMAs within the existing 16-page bound are eligible for
partial removal, with all original admission exclusions. The live partial tests
cover three-page inputs and one-page slices, not other widths or longer slices.
Supported inputs have no leaf translations to invalidate: the warm-TLB (cached
address translation) partial test proves local fallback, not remote teardown.
Resident whole-VMA preservation smokes separately exercise real remote teardown.
Retained-range faults concurrent with splitting, forced allocation/post-split
errors, VMA-count exhaustion, tree-height growth, broader memory-pressure races
and general mapping creation remain untested. The historical full API/fault-retry
suite and Native-control boot were not repeated. See the scope guide for the
remaining exclusions. No performance result is claimed.
