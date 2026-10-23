# Mixed resident/untouched partial munmap correctness

The `kdmm9` milestone passed all 22 serial cases in the existing MM VM, including
11 real different-task removals. See the [scope and ordering](../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
and [result record](../../../../bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/README.md).
The correctness-only module remains in `../unmap_body/payload/`. It controls the
queue and observes state; actual `munmap`/`vm_munmap` calls execute the kernel body.

## Reuse the image and frozen probes

With the original VM idle and its serial test slot available, from `380G10`:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence; use the next unused number. Run recovery after
the test command passes and drains. A failed command or timeout is not proof of
drain: inspect workers and retain the loaded state; never force unload or reboot
an active test. The transition verifies the real snapshot, original placement,
kernel identity and recovery default. Configuration and admission checks remain.

These commands reuse six clients and the four modules built for this image.
Do not repeat `prepare`, `build` or `finish` for unchanged tests. Storage is very
tight: check free space before another run and arrange space before another
candidate installation. Existing evidence must remain preserved.

Guest root:
`/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023`.
The frozen driver is `control/focus.py --build-attempt 2 --run focused-N`;
transitions use `control-2/transition.py`. Binaries and validators are in
`probes-1/`. Each case retains `client.json`, `kernel.log` and receipt controls;
`focused-N/result.json` records their hashes and aggregate outcome. The source
host retains transport receipts under the corresponding `raw/tests/` stage.

Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm9-20261023`.
Small identity files are at
`/mnt/kdlock-builds/mm-mixed-partial-20261023/identity`. One compressed kernel ELF
is stored in two ordered parts, whose paths and individual/combined hashes are
recorded in `/root/kdlock-kernel-work/mm-mixed-partial-20261023/identity-store.json`.
The transition checks and streams both parts into RAM, then verifies the exact
uncompressed kernel. Recovery reboot clears that RAM copy. This identity
snapshot is not a full module build tree. No old artifact was deleted.

## Focused cases

R means an ordinary resident anonymous page; U means a slot left untouched by
these tests, with an absent page-table entry (PTE). Slots are numbered 0, 1, 2.

| Client arguments | Input and proof |
| --- | --- |
| `mixed prefix` | RUU, remove slot 0; two remote bodies. |
| `mixed suffix` | UUR, remove slot 2; two remote bodies. |
| `mixed middle` | URU, remove slot 1; two remote bodies. |
| `mixed left` / `mixed right` | RRU / URR, remove slot 1; two remote bodies each, exact surviving physical-page identity. |
| `mixed refusal` | Busy final resident page; one earlier hold released before handback/ACK; next call local. |
| `mixed zero` | A survivor already maps the shared zero page; refused before splitting, with exact rollback/ACK and sticky fallback. |
| `mixed missing` | Untouched target between resident survivors; refused with exact rollback/ACK and sticky fallback. |
| `mixed cancel` | Queued fatal cancellation retains the victim mapping and releases prepared resources. |
| `mixed free` | Drop test references before real removal; one remote body exercises final physical-page release. |
| `error native resident middle 1` / `error kd resident middle 1` | Compare an error after the first interior split; no replay or lost mapping. Repeat both with final argument `2` for the second split. |

The four error cases and ten mixed cases are followed by eight preservation
smokes: fully resident interior success/rollback/error, untouched interior,
unpopulated whole VMA, four-page resident whole VMA, advice and separate
first-write fault. A VMA is a virtual memory area describing one mapping.
The native controls run the ordinary native body on the same KD lock backend
with delegation disabled; they are not a Native-off boot.

Sparse test pins acquire references only for resident slots. Read-only PTE
queries prove untouched slots were not populated by observation. Every remote
body pairs physical-page and resident/untouched-mask receipts with exact
mm/request/range/origin/executor identity. A real fault into an untouched
survivor waits behind writer admission, then resolves locally. Original resident
bytes and zero-filled survivors match, and subsequent survivor writes read back.
TLB (cached translation) invalidation is checked on the originating CPUs.
Reverse-map links, VMA/page accounting, references and cleanup must balance.
ACK means acknowledgement of the exact handed-back request/owner; it is not
remote-body completion. Local fallback and synthetic callbacks do not count.

All 153 negative controls corrupt copies of real records and require rejection;
they are not extra live executions. Limits include wider ranges, complex ancestry,
zero-page survivors, shared/swapped/huge pages and general table destruction.
Mixed edge cases with one resident survivor were not separately exercised;
broader races, pressure and historical full suites remain untested. No timing
or general mmap-support claim follows from this milestone.
