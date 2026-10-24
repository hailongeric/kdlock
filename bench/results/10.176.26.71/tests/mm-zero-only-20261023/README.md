> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Zero-target removal without private survivors

Passed on `6.1.159-kdmm12`: **44 serial cases, two basic tests and 660 negative
receipt controls**. All 12 new layouts matched native behavior. **27 zero-target
removals executed in different tasks with zero private-page holds**, plus two
resident-survivor preservation removals and one separately counted removal of a
controlled newly private target. Recovery is restored and test modules unloaded.
No build or live case failed. No performance campaign ran.

Implementation and frozen inputs: `9ab4c39fd6e0f87bbff205720f102843a0c95e2c`.
The [kdmm11 milestone](../mm-zero-target-20261023/README.md) remains separate,
unchanged evidence; its full matrix was not rerun.

## Mechanism and supported scope

One shared-zero target can now be removed from an exactly three-page anonymous
VMA (virtual memory area), at any of the three positions, with only zero or
untouched survivors. The existing opt-in and same-PMD neighboring VMAs remain
required. A PMD is the page-table directory covering this 2-MiB region; the
neighbors constrain native table freeing even when no ordinary resident page
exists. This does not enable general page-table destruction.

Three implementation assumptions were changed in `mm/kd_mmap_unmap.inc`:
admission success is separate from the count of owned private pages; absent
anonymous reverse-map metadata is accepted only when both its pointer and chain
are empty; and post-body checks depend on the validated retained table, not a
nonzero page count. A reverse map links ordinary anonymous pages to their VMAs.
Existing simple single-link metadata remains supported, including when all current
PTEs (page-table entries) are zero/absent. Inconsistent or complex metadata refuses.

The caller still prepares two VMA descriptors, two reverse-map links and mapping
index reserves before publication. Under mmap writer ownership and the PTE lock,
the executor checks the current VMA, metadata and every slot. Native cloning uses
no reverse-map allocation for empty metadata; unused caller links retire exactly.
A pre-execution private fault can create metadata and consume the prepared links.
Native zap clears a zero PTE and invalidates its TLB (cached translation) entry,
without private RSS (resident set size), page reverse-map or page-release work.
Zero pages never enter the owned page array. Admitted split errors return directly;
unsupported states hand back before effects and use matched ACK (acknowledgement)
and sticky local continuation. Readers remain concurrent and local.

## Cases and results

R denotes ordinary private resident, Z verified shared zero, U absent untouched.
Every row ran four native/KD pairs; no new combination was omitted.

| Removed position | Initial slots for survivor pairs ZZ, ZU, UZ, UU |
| --- | --- |
| Prefix | ZZZ, ZZU, ZUZ, ZUU |
| Interior (`middle`) | ZZZ, ZZU, UZZ, UZU |
| Suffix | ZZZ, ZUZ, UZZ, UUZ |

The matrix produced 24 different-task zero removals. A separate inherited-metadata
case added two, and the controlled-change case added one unchanged zero removal:
**27 with `held=0 released=0`**. The resident-survivor smoke added two zero removals,
for **29 total zero removals**. The controlled newly private target added one
private removal, counted separately. Fifteen native success comparisons include
the 12 layouts, inherited metadata, controlled change and resident-survivor smoke.
Native controls use the ordinary body on the same KD backend, not a Native-off boot.

Example `target-prefix-uu`: mm `ff11000345334140`, request 2, origin **1893**,
executor **1894**, zero PFN (physical page number) `0x3748`. Its paired completion
proves target removal with resident mask 0, zero mask 1, untouched mask 6,
`held=0 released=0`, target PTE absent, `zero_owned=0` and retained tables.
Initial reverse-map pointers were zero for all three groups.

Read faults establish Z; read-only PTE queries distinguish Z from U without
writing or pinning either. Removed addresses fault on their original CPUs after
translation warmup. VMA bounds/offsets/flags, virtual-page counts, table bytes,
per-VMA RSS/anonymous bytes and metadata lifetimes passed. U remains absent until
explicit access; one recorded competing local read fault waits at writer admission
and then populates its selected U survivor. After these observations, zero-fill
reads and isolated private writes passed for every survivor and an independent
zero mapping. The 37 target-family cases recorded 139 isolated writes, 18 exact
test-reference releases and 222 cleanup calls; 624 of the negative controls cover
them. Local heads and fallback never contribute to different-task counts.

`target-change-empty` began with no reverse-map metadata or private pages. After
three requests published while two local readers remained admitted, native locked
`get_user_pages` changed the selected Z target to private PFN `0x34ea84`.
Actor **2020** recorded pending=3/readers=2/admission=-1. Request **2**, origin
**2016**, executor **2015**, removed that exact private page with one hold/release;
new simple metadata and caller-supplied split links remained balanced. This is a
deterministic pre-execution transition, not a concurrent write-fault race test.

Both interior split-error points matched native `ENOMEM` layouts with harmless
splits, unchanged zero PTEs, zero private holds and no destructive replay. Empty
metadata consumed no reverse-map links even on these errors. Missing-target and
busy-private-page refusals matched two ACKs and sticky continuation. Queued fatal
cancellation retained its victim mapping and retired every prepared resource.
The inherited-metadata fixture writes/discards only the target before its zero
read fault; it never populates a survivor to bypass eligibility.

Seven additional preservation smokes passed: resident targets with zero survivors
(2 remote removals), mixed survivors (2), fully resident partial removal (2),
untouched partial removal (15), four-page whole removal (15, 60 physical receipts,
144 origin translation checks), advice (1,732 returned remote bodies), and separate
first-write faults (140 real remote installations). These counts are separate.

## Reproduction and evidence

On source host `380G10`, with the existing VM idle and capacity checked, reuse the
installed image and frozen probes serially; attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-zero-only-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-zero-only-20261023/workflow.py recovery --attempt 2
```

A timeout is not drain. Do not reboot or unload active workers. The
[probe guide](../../../../../tests/kernel/mmap_lock/zero_target/README.md) gives
individual modes and the direct command for an already verified KD boot.
This run used `prepare`, `build`, `kd`, one `collect`, then `recovery`, attempt 1.

Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-only-20261023`, run
`focused-1`. Essential evidence is in
`bench/results/10.176.26.71/raw/tests/mm-zero-only-20261023/`:

| Artifact or identity | Value |
| --- | --- |
| Candidate Build ID | `d6a297a710d0ecc7f2867028c031d730452a2863` |
| Candidate manifest | `0dca8672c3c9999b62131746a72ccdc827883ab08ac6be03d53b167395770c48` |
| Candidate boot | `01a8d855-bedf-4ada-912a-f9e4875b408d` |
| New client SHA-256 | `60cbe88afd8e64f1d34b4e7886a9dd2edc386e885f17506b8b34ee4b88d2ce7c` |
| Focused result SHA-256 | `739dd2811978adb24be7cc79dd266f7b789d66ec0b0392155790c8d6cac07543` |
| `collect-1/essential.tar.gz` | 565,466 bytes; SHA-256 `d929669b25d998e7ab3ddd877779eeea1473047007612921d64ab83ba9d12db6` |
| Recovery boot | `f60afcd4-a794-4e2f-a14f-2d64139b0e40` |

One offline pass verified all 44 client/log pairs before recovery. `evidence-check.json`
retains selected receipts; `recovery-1/result.json` and `final-health.json` record
restoration separately. No previous archives were copied or rescanned.

## Storage, recovery and remaining limits

Only quick capacity checks used the previous measured build/boot budget.
The RAM overlay reused the existing build tree. The distinct release required
3,161 compilation steps and 73 runtime modules; only one captured kernel source
changed. Eight clients were reused; the changed zero-target client and four test
modules were built. Persistent build/install growth was 225,099,776 bytes.
Volatile intermediates remained recoverable in RAM until the approved boot cleared
them. No additional permanent files, source, recovery artifacts or evidence were
deleted; no disk, snapshot, VM placement or recovery-setting change was made.

Final recovery is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`: exact 73 runtime modules, 5,686 preserved
recovery module files, no test modules, idle, no new faults, cleared one-shot entry
and empty temporary RAM. Root free space is **74,321,920 bytes (70.88 MiB)**;
the data disk has 10,031,104 bytes available. Another build requires a new capacity
decision; this stage needed no permanent deletion or repeat disk investigation.

Larger mappings, complex ancestry, shared private pages, swap/huge/device pages,
general table destruction and mapping creation remain unsupported. Absent target
PTEs still hand back. Uncontrolled write faults, forced VMA replacement,
reclaim/pinning races, pressure, post-admission cancellation, Native-off comparisons
and non-root memory cgroups were not tested. Inherited empty-page ancestry was
covered in one interior case; its separate split-error variants were not repeated.

The next small extension is an absent target PTE in the same three-page scope
with retained tables. It needs an explicit absent-target completion state instead
of assuming a zero PFN or owned private page, plus the same VMA/error/cleanup checks.
No broader mapping or performance claim follows from this milestone.
