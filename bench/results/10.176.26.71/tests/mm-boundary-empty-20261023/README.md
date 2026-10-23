# kdmm16: empty target PTE at a retained table boundary

Completed on the existing `10.176.26.71:2222` VM. `6.1.159-kdmm16` implements
one-page prefix/suffix removal from a three-page anonymous VMA (virtual memory
area) when the target PTE (leaf page-table entry) is empty in an existing table.
All **51 serial cases, two basic tests and 1,458 negative receipt controls
passed**. There were **26 new different-task removals**, including **14 without
private-page holds**, and two native-matched delegated split errors. Recovery
is restored and test modules are unloaded. This required a kernel change; the
[kdmm15 campaign](../mm-boundary-edge-20261023/README.md) remains separate and was
not repeated. No timing was performed.

## Mechanism and exact scope

At a 2-MiB page-middle-directory (PMD) boundary B, with 4-KiB page size P:

| Shape | Original VMA | Removed range | Native retention bounds after split |
| --- | --- | --- | --- |
| Prefix | `[B-P, B+2P)` | `[B-P, B)` | preceding VMA end to B |
| Suffix | `[B-2P, B+P)` | `[B, B+P)` | B to following VMA start |

The target occupies one PMD interval alone; both survivors share the adjacent
interval. Both intervals must lie within one valid upper directory (PUD). Both
actual outer neighboring VMAs remain required: preceding end above the first
PMD base, following start below the second interval's end. Native
`free_pgd_range()` rounding must return before any table walk. Another populated
PTE does not establish this proof. Target/survivor interval sharing, interior
crossing and general delegated table destruction remain refused.

The previous mandatory `pmd_none()` target check now distinguishes a missing
table from an existing normal table with `pte_none()` at the selected address.
The executor takes the actual mmap write lock, walks current upper levels,
observes the PMD under its lock and checks the current leaf under its PTE lock.
It records that table's physical identity, not a pointer retained from caller
preparation. Populated zero/private targets, special non-present entries,
huge/device mappings and missing higher levels refuse before any split. Native
table-retention bounds and writer ownership preserve lifetime through removal.

Caller-prepared mapping descriptors, mapping-index reserves and reverse-map
links are unchanged. A reverse map associates a private page with its mappings;
absent anonymous metadata needs no such links. Untouched/zero slots acquire no
private-page ownership. The native body splits and removes the virtual mapping
without allocating a target page/table, clearing unrelated PTEs or bypassing
cleanup. Success and admitted split errors check the same parent/target/survivor
table identities, empty target, table-byte accounting and exact held/released
private references. See the maintained
[execution and retention explanation](../../../../../kernel_integration/mmap_lock/UNMAP.md#empty-target-entry-in-a-retained-boundary-table).

Unsupported operations hand back to the original waiter with an exact
acknowledgment (ACK); sticky fallback keeps later calls on that address space
local. An error after splitting is an admitted return and cannot trigger local
replay. Concurrent readers remain local.

## Validation and native comparisons

`focused-1` ran on one verified candidate boot. Native controls execute the
ordinary munmap body on the same KD lock backend, not a Native-off boot.
R/Z/U denote ordinary private resident, shared-zero and untouched survivors,
ordered by increasing address.

| Cases | Count | Result |
| --- | ---: | --- |
| Prefix/suffix × RR, RZ, RU, ZZ, ZU, UU × native/delegated | 24 | 12 native-matched layouts; 24 remote completions |
| Post-split ENOMEM, both directions, native/delegated | 4 | Two remote errors; native-compatible harmless split; no replay |
| Retaining neighbor moved away, both directions, native/handback | 4 | Exact ACK and sticky route; native releases one target table |
| Empty target becomes zero/private, both directions, native/handback | 8 | Same table, locked refusal before split; exact ACK and page references |
| Target shares interval with middle survivor, both directions | 2 | Explicit geometry refusal and sticky local continuation |
| Queued cancellation, both directions | 2 | Victim mapping intact; caller resources retired |
| Waiting survivor demand fault, native/delegated | 2 | Two further remote removals; fault completes locally after writer release |
| Busy final private survivor | 1 | Earlier hold retired exactly before refusal |
| Preservation smokes | 4 | Missing-boundary prefix/suffix, old table-appearance refusal, same-table empty target |

The 47 new-path cases rejected 1,341 corrupted receipts/observations; four
preservation cases rejected another 117. New-path totals include nine matched
handback/ACK pairs and two cancellations. There are 19 native success comparisons
(12 layouts, two retention-loss cases, four target transitions and one waiting
fault), plus two separate native error comparisons. Preservation produced four
missing-boundary removals, two same-table empty removals and one additional ACK;
these are excluded from the 26 new-path removals.

ZR, UR and UZ were not repeated in either boundary direction. Both survivors
occupy adjacent entries of the same retained table and use the same per-slot
classifier and native surviving VMA. This is a representative reduction, not
live coverage of those six reversed layouts. Busy-second-survivor refusal checks
ordered partial acquisition and rollback separately.

The target table is created by read-faulting the target-side retaining neighbor,
never the target. Actual read-only page-table walks establish its shared-zero
PTE, the empty target and exact table identity. Before any survivor access, the
probe verifies removed-address `SEGV_MAPERR`, surviving VMA bounds/offsets/flags,
map counts, private resident accounting, anonymous metadata, page references,
neighbor state and table identities. Then U survivors demand-fault normally,
Z survivors read zero and support isolated private writes, R contents survive,
and an independent zero mapping remains unchanged. Complete local cleanup
removes every fixture and observes missing upper entries, establishing eventual
release of the retained tables.

Examples from request-bound kernel receipts:

- `empty-target-prefix-rz`: request **2**, origin **1884**, executor **1885**;
  target table **34b0f0**, `target_pte_none=1`, one exact private hold/release.
- `empty-target-suffix-uu`: request **2**, origin **1965**, executor **1963**;
  target table **34e119** retained, survivor table missing, zero private holds.
- `empty-target-prefix-change-private`: local reader **1998** faults the target
  after two requests publish, with two reader shares and closed admission.
  Table **3526c1** stays identical. Request **2**, origin **1995**, executor
  **1994**, hands back and ACKs exactly; this is not a remote removal.

Both target transitions run real read/write faults through the existing admitted
local-reader control. The private transition's exact test reference survives
native removal: mapping/reference counts move from 1/2 to 0/1 before that last
reference is released. No synthetic body or admission bypass is used.

The retention-loss control moves the target-side neighbor away **before
publication**, checks the still-existing target table and empty entry, then
requires handback and native table release. Replacing a VMA while the fixture's
two reader shares remain held would require conflicting writer ownership; no
queue-time neighbor replacement is claimed. The empty target has no positive
cached translation to warm. Native TLB (translation lookaside buffer) completion,
removed-address faults, intact neighboring translations and later survivor faults
were checked; this does not establish all hardware TLB or reclamation races.

## Build, storage and evidence

Implementation commit `e81dd92` added the path and focused controls. `build-1`
failed at the new client compile on a signed/unsigned comparison, before kernel
compilation, basic tests, installation or boot. Its source and log are preserved.
Commit `a857ebf` added the explicit comparison cast and froze retry controls.
Successful `build-2` reuses three existing clients, runs both basic tests once,
and builds one new client, the affected test module and required kernel/runtime
modules. Only `mm/kd_mmap_unmap.inc` differs from kdmm15's captured kernel source.
There were 3,155 dependency-triggered C compilations: the distinct kernel release
regenerated shared dependencies. No clean/full-tree rebuild command was used.

The quick capacity check used the existing measured 260,000,000-byte root budget
and 7,739,283,276-byte RAM budget. Before the successful build, root had
432,816,128 bytes and RAM scratch 12,613,750,784 bytes free. Packaging/link
intermediates stayed in RAM; root had 212,373,504 bytes after build/install and
208,076,800 bytes after recovery. Another cycle of the same budget would need
51,923,200 additional bytes or a newly justified smaller operation. No permanent
deletion, snapshot change, disk resize or VM configuration change occurred.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-empty-20261023 / build-2 / focused-1` |
| Frozen source commit | `a857ebfaa0917d331b76d2bd848b9932c7ab4476` |
| Candidate Build ID | `276622ad43431bd0489402061baf0969051ff98b` |
| Candidate manifest SHA-256 | `f74b8966103dc630a90a96ce577cb83276e39814f488f2e27ea73f3be4221be0` |
| Candidate boot | `1b5e6034-c0ee-4bad-b729-00b855a76e4b` |
| Recovery boot | `3617c157-90d0-4a9c-a765-ab2d80a6170c` |
| Recovery Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Essential archive bytes | `703161` |
| Essential archive SHA-256 | `41696929f36b7c1e31f829a27672853fdd31e1a7290e97946c349b0d66992738` |

One [essential archive](../../raw/tests/mm-boundary-empty-20261023/collect-1/essential.tar.gz)
contains new logs, observations, receipts and frozen sources, including the failed
compile. The [offline audit](../../raw/tests/mm-boundary-empty-20261023/collect-1/audit.json)
verified all 102 case-file hashes, 32 input hashes, 15 archived new probe source
hashes and completion counts. Existing baselines were neither recopied nor
rescanned. Guest binaries and captured kernel identity remain under
`/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-empty-20261023` and
`/root/kdlock-kernel-work/mm-boundary-empty-20261023` respectively.

After that archive was verified, [recovery verification](../../raw/tests/mm-boundary-empty-20261023/recovery-1/transition.json)
and the separate [final health receipt](../../raw/tests/mm-boundary-empty-20261023/final-health.json)
confirmed idle recovery, all 73 original runtime modules, no test modules,
cleared one-shot selection and RAM scratch. Recovery preservation verified 5,686
module-file hashes. No kernel fault matched the focused run or recovery checks.
Recovery logged the same six `fd0` read-error lines seen in the prior record;
these remain in its transition evidence. No second archive was needed.

## Reproduction and remaining limits

Reuse the installed artifacts on the same idle VM after a current boot/log
capacity check. Completed attempt directories are immutable. A new serial run,
with no build:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/workflow.py recovery --attempt 2
```

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_empty/README.md)
gives direct guest commands and exact modes. Do not reboot after failure or while
a run is in flight until drain is established.

Populated boundary targets, target/survivor interval sharing, interior crossing,
cross-PUD geometry, missing higher levels, huge/special non-present entries,
complex ancestry and general delegated table destruction remain refused. The
special/huge/higher-level guards were not newly exercised by live fault injection.
Queue-time neighbor replacement, uncontrolled write faults, broad reclaim/pinning
races, forced allocation failure, post-admission cancellation and Native-off boot
controls remain untested. Advice, first-write and unrelated whole-removal code
did not change; their historical matrices were not repeated. The four smokes
cover the changed boundary and shared probe paths. Larger mappings,
performance/p95, mutex regressions and nano reruns remain deferred.

The next useful extension is a **shared-zero-page boundary target** under the
same retention proof, with exact special-zero PTE classification and translation
invalidation but no ordinary private-page ownership or release. Private boundary
targets and general table freeing should remain separate later changes.
