# Shared-zero target sharing a boundary table: prepared, not validated

The kdmm20 candidate source and focused runner are prepared on `380G10`.
**No synchronization, build, installation, candidate boot or live test has run.**
The completed [kdmm19 baseline](../mm-boundary-shared-20261023/README.md) remains
unchanged in the guest. Recovery `6.1.159-kdclobber2` is running, test modules are
unloaded, and the original snapshot and CPU placement were verified. The deployed
kernel still refuses the newly proposed case. No different-task execution or
acceptance is claimed for kdmm20.

## Storage blocker and exact proposal

Guest root has **43,724,800 bytes free**, a **76,275,200-byte shortfall** against
the measured 120,000,000-byte cycle budget. RAM has 12,613,750,784 bytes free for
the 8-GB temporary build/identity budget; source-host free space exceeds 43 GB.
The budget retains recovery, accounts for packaging and boot growth, and keeps
the compressed identity on the source host as in kdmm19. No full disk audit or
prior deletion was repeated.

The [exact 35-file proposal](../../raw/tests/mm-boundary-shared-zero-20261023/cleanup/APPROVAL.md)
would free **84,631,552 bytes**, projecting root free space to **128,356,352 bytes**.
These inactive object files are regenerable and excluded from captured source
and build identities. [Individual hashes and allocations](../../raw/tests/mm-boundary-shared-zero-20261023/cleanup/proposal.json)
and a [verified backup receipt](../../raw/tests/mm-boundary-shared-zero-20261023/cleanup/backup-receipt.json)
are saved. Every file is verified inside one source-host `recoverable.tar.gz`
(SHA-256 `1d9429ec8df74f48d60940df667ae0bb7e4dd7e7ee2d88c1f6a3d45b8508bb06`).
**Exact-file approval is pending; none has been deleted.** Earlier approved
backups remain intact. No source, final kernel/module, recovery or unique result
is proposed for deletion. Recheck idle state, file hashes/open references and
actual capacity immediately before any approved cleanup/build.

## Proposed mechanism

For P = 4 KiB and a 2-MiB PMD (page-middle-directory) boundary B, prefix VMA
(virtual memory area) `[B-2P,B+P)` removes `[B-2P,B-P)`; suffix `[B-P,B+2P)` removes
`[B+P,B+2P)`. Slot 1 shares the target leaf table. Both retain `[B-P,B+P)`.
The existing upper hierarchy, both outer-neighbor guards and exact native
`free_pgd_range()` floor/ceiling proof remain mandatory. General table destruction
is excluded; an absent other leaf table is permitted for an untouched survivor.

The exact refusal is `edge->shared && !edge->target_private`. The candidate adds
only the existing validated zero-PTE class: present, special, read-only,
non-protection-none, non-device, `is_zero_pfn()`. PTE means leaf page-table entry.
The current table, target entry, VMA bounds, ancestry and neighbors are rewalked
under actual mmap write ownership and the relevant PTE lock. Empty/missing target
states in this geometry remain refused. Private targets still need every kdmm19
page-eligibility, reference, lock and boundary check.

The target zero page never enters the private hold array. Native `vm_normal_page()`
returns NULL for it; `zap_pte_range()` clears the PTE and records TLB (translation
lookaside buffer) invalidation before skipping private RSS (resident-page
accounting), reverse-map and page-release work. Exact native source was inspected
in [memory.c](../../raw/tests/mm-boundary-shared-zero-20261023/native-memory.c).
Caller-prepared VMA/index/reverse-map resources, zero-private-hold admission,
per-slot survivor checks and exact retirement remain unchanged. A split error
returns natively without destructive local replay. The new body receipt binds
zero ownership, retained-table partition and completed native teardown to the
request and different executor. Readers remain concurrent and local.

Two test-only controls use a real local-reader write fault after publication.
Mode 11 creates an ordinary private target with an exact GUP (`get_user_pages`)
reference and three queued requests; locked body revalidation must select the
complete kdmm19 path. Mode 12 additionally locks that new page, with two requests
queued, and must hand back before effects with an exact acknowledgment (ACK).
No production admission bypass or synthetic removal callback is added.

## Planned minimal validation; all pending

| Group | Planned cases |
| --- | ---: |
| Both directions × all nine private/zero/untouched survivor pairs × native/delegated | 36 |
| Split error, retention loss, supported zero-to-private and busy zero-to-private; both directions and routes | 16 |
| Queued cancellations, busy far-survivor refusal, waiting far-survivor fault/native control | 5 |
| kdmm19 and isolated-zero preservation, old missing/empty paths, continued shared empty/missing refusal | 8 |

This is **65 planned serial cases**, plus the two basic programs. All nine pairs
are distinct because near/far table roles differ; four pairs in each direction
have no initial private hold. Checks require real zero PTEs before admission,
request-bound different-task completion, native results, inaccessible removed
addresses, retained contents/PTEs/VMAs, RSS and table lifetimes, exact references,
independent-zero isolation, delayed untouched faults/writes, ACK/retirement and
full cleanup. The existing corrupted-evidence controls are extended, not removed.
Only static Python parsing and source review have completed; these are not VM
test passes. No historical campaign has been rerun.

## Resume after cleanup approval

Do not run until the approved cleanup is recorded and current headroom satisfies
the measured budgets. These attempt-1 directories do not yet exist in the guest:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py prepare
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py build
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py kd
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py collect
# Verify the essential evidence and actual drain before recovery:
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py recovery
```

The runner reuses eight unchanged client executables, compiles the new client
and affected module, and performs one dependency-driven incremental kernel build.
It uses the existing RAM overlay, source-host compressed-identity transport and
recovery workflow. A failed or timed-out run is not proof of drain; never force
unload or reboot an in-flight operation. Keep one archive of essential new logs.

Queued neighboring-VMA replacement remains untested: replacement requires a
writer while this fixture deliberately holds two reader shares. It cannot be
inserted there without changing the ownership model. Prepublication retention
loss remains the safe control. Uncontrolled fault/reclaim/pinning races, complex
ancestry, larger VMAs, interior crossing and general table destruction remain
outside scope. Performance, p95, mutex regressions and nano remain deferred.
The next functional step can only be chosen after this pending validation.
