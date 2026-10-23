# Mixed resident/untouched partial munmap correctness

All nine mixed layouts passed native comparisons on the existing `kdmm9` kernel:
18 real different-task removals, 27 serial cases, 262 rejected corruptions of
real receipts and two basic programs. Recovery is restored. See the
[mechanism and scope](../../../../kernel_integration/mmap_lock/UNMAP.md#resident-partial-removal-and-post-split-errors)
and [complete matrix result](../../../../bench/results/10.176.26.71/tests/mm-mixed-matrix-20261023/README.md).
The [initial 22-case milestone](../../../../bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/README.md)
and [fully resident baseline](../../../../bench/results/10.176.26.71/tests/mm-resident-partial-20261023/README.md)
remain separate evidence. This follow-up rebuilt only this userspace client;
all kernel code, four test modules and preservation clients were reused.

## Reuse the image and frozen probes

With the same VM idle, its serial test slot available and enough disk headroom,
run from `380G10`:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-mixed-matrix-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-mixed-matrix-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence; use the next unused number. Run recovery after
tests pass and drain. A failed command or timeout does not establish drain:
inspect workers and retain loaded state; never force unload or reboot an active
test. The transition checks the actual recovery snapshot, original placement,
kernel identity and recovery default. All admission checks remain intact.
Current root/data free space is only about 3.5/10 MB; arrange headroom before
another transition. Existing evidence must remain preserved.

Do not repeat preparation, kernel builds or module builds for unchanged inputs.
The matrix's guest root is `/mnt/kdlock-builds/mm-mixed-matrix-20261023`.
`control-1/focus.py --run focused-N` runs the matrix on an already verified KD
boot, without rebooting. `probes-1/mixed_partial/client` is the new binary;
`build-1/result.json` records its hash and exact reused paths/hashes. The remaining
clients/modules are frozen under
`/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023/probes-1`.
Each case keeps `client.json`, `kernel.log` and receipt controls;
`focused-N/result.json` binds their hashes, native comparisons and outcomes.

Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm9-20261023`, release
`6.1.159-kdmm9`, Build ID `e33aeaba03177030ec750342593246d18908c776`.
Transitions reuse the initial milestone's `control-2/transition.py` and verified
split compressed kernel ELF, reconstructed in RAM for identity checking. Recovery
clears that temporary RAM copy. No prior archive or binary is copied by this run.

## Complete mixed matrix

R means an ordinary resident anonymous page; U means an untouched slot with an
absent PTE (page-table entry). A VMA is one virtual memory area describing a
mapping. Each row runs both `native MODE` and `mixed MODE`. Native uses the
ordinary native body on the same KD lock backend with delegation disabled;
it is not a Native-off boot. Every mixed row completes two bodies on other tasks.
All nine combinations run separately; no symmetry is assumed.

| MODE | Initial slots 0/1/2 | Removed slot |
| --- | --- | --- |
| `prefix` | RUU | 0 |
| `prefix-near` | RRU | 0 |
| `prefix-far` | RUR | 0 |
| `middle` | URU | 1 |
| `left` | RRU | 1 |
| `right` | URR | 1 |
| `suffix` | UUR | 2 |
| `suffix-near` | URR | 2 |
| `suffix-far` | RUR | 2 |

Sparse test pins retain only originally resident pages. Independent PTE queries
do not access the addresses. Native/KD comparisons cover VMA bounds, offsets,
flags and per-VMA RSS (resident set size)/anonymous bytes from read-only `smaps`
walks before removal, before controller survivor reads and after local writes.
Removed addresses fault on their original CPUs, checking TLB (cached translation)
invalidation. Original resident bytes and physical pages remain intact.
Untouched slots remain empty through body completion; one deliberate competing
read fault waits at reader admission, then resolves locally to the shared zero
page. Full-page zero reads and subsequent writes verify the survivors normally
fault in and remain writable. Zero-page reads do not count as private RSS.

The same run includes `error native resident middle 2` and
`error kd resident middle 2`, `mixed refusal` (a busy final page), and
`mixed cancel`. These check native-compatible harmless splits, exact returned
errors, no destructive replay, release before matched handback/ACK
(acknowledgement), sticky local fallback and queued cancellation. Five smokes
preserve fully resident partial, untouched partial, four-page whole removal,
advice and separate first-write fault behavior. The initial milestone retains
split-point-1, zero-page/missing-target refusal and final-release coverage.

Unsupported cases still hand back: zero-page survivors, nonresident targets,
complex reverse-map ancestry, shared/swapped/huge pages and general page-table
destruction. Forced prepublication layout/residency changes, broad fast-pinning
and reclaim races, pressure and wider mappings remain untested. Successful local
fallback, queue admission and synthetic callbacks are never counted as remote
body execution. No performance or general mapping-support claim follows.
