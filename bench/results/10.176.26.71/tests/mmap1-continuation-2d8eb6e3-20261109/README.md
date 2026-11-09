# Bounded learning continuation: deadline stop

Harness commit `2d8eb6e35049c89be1efd58fe0cdc8eb411aae88` adds short
application invocations after settled replacements, before the fixed receipt.
One fresh live experiment ran. It reached two completed continuations and a
third drained application, but exhausted the shared learning deadline during
settlement. No fixed receipt, required-publication gate or fixed measurement ran.
There is no accepted throughput result or measured performance gain.

## Change and focused check

The original 730-sample preparation remains. At most eight additional ordinary
eight-process applications use the existing six warmup plus two selected samples
and 30-second application bound. All invocations and compilation settlement share
the original 1,800-second deadline. Startup verification checks the remaining
application budget again before launch. Only an unchanged settled registry can
proceed to the existing fixed receipt, publication and stability checks.

The original JIT, eligible old images, miss records, exact handback, source leases
and publication rules are unchanged. This change does not infer new indirect-CALL
return continuations.

The directly affected `bench/test_mmap1_settled.py` driver passed all **21 tests**
in the normal VM, with no skips. No other tests or builds ran. The test controller
verified final idle and unchanged original receipts. See [focused-check.json](focused-check.json).

## Live outcome

| Stage | Munmap generation | Mmap generation | Munmap finished handbacks | Munmap returned JIT bodies | Reported pairs/s |
| --- | --- | --- | ---: | ---: | ---: |
| Long preparation, settled | 7 | 5 | Not summarized here | Not summarized here | 20,531.9 |
| Continuation 1, completed | 7 → 8 | 5 → 6 | 165,110 | 0 | 20,651.5 |
| Continuation 2, completed | 8 → 9 | 6 → 7 | 164,507 | 0 | 20,602.5 |
| Continuation 3, application drained; settlement failed | Bound to 9 | Bound to 7 | Delta not retained | Delta not retained | 20,411.5 |

Each completed continuation passed counter conservation and recorded zero
`local_no_image` selections. These counts cover each complete learning
application, not one miss target. The third application exited with status zero
and drained in `8.086250197` seconds, but its final verification failed; its
receipt is `passed=false`. Its counter delta was not retained. All rates above
are unscored, changing-image learning observations using nominal sample divisors,
not stable fixed-point or quiet benchmark throughput.

The exact stop was
`AssertionError('demand learning did not reach a quiescent boundary')` at the
shared deadline `1812.508514939` seconds in the guest monotonic clock. The last
published registry retained mmap **g7 NORMAL** and munmap **g9 CALL_MISS**.
Munmap g9 execution is established by its newly admitted CALL record.

The final pending CALL target is **`0xffffffff8181ad20`**. Authoritative batch 17
has base generation 9, revision/sequence 11, one CALL record, `from=0` and
overflow zero. Published g9, batch 16 assembly lines 282954–282959, contains its
CALL-miss stub. Its sole emitted caller is CALL `0xffffffff817e3c64`, pushing
return word `0xffffffff817e3c69` (lines 150626–150635). The target's symbol name
was not established. This is a missing-callee boundary; it does not establish a
RET correction failure.

The next candidate includes the decoded target and that continuation. Its child
3356 finished successfully at `1826.942833892` seconds, **14.434318953 seconds
after the deadline**, with wall time `243.250242936` seconds. The daemon log ends
at that successful compile/reap metric. No g10 publication occurred; an upload
attempt is not established. The records do not identify the precise interruption
point between compilation completion and publication.

The original failed result remains `STOPPED_RETIREMENT_PENDING`. Exact
finalization separately succeeded with state 2, modules/frames/writers all zero,
and final idle; it correctly retains `passed=false` and `campaign_complete=false`.
See [finalization.json](finalization.json). Normal recovery verified kernel
`7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`1eeab914-c1d7-4c69-bc7c-1db2921c3135`, idle. No experiment was repeated.

## Identity and retained evidence

The unchanged 128-image diagnostic provider, daemon and kdscope5 kernel were
reused after exact source-byte and artifact checks. Their real build commits
remain provider `ac0b5b8271f0d88fe3ce0a5b040868973dfa62cc` and daemon
`76b0147cfbb58246b4a3a0f371434cd758032588`; they were not rebuilt or relabeled
as the harness commit. Standard guest identity checks and publication gates
were preserved. The KD boot was `3c097f1e-4ecc-46b5-9768-25c0c6161746`.

External progress reads stopped before the first continuation. Subsequent
progress monitoring used only the local controller stream and its declared
boundary observers. Evidence collection occurred after retirement and normal
recovery.

[receipt.json](receipt.json) binds selected facts to the original result hashes,
full collection index and recovery identity. Full immutable evidence remains at:

- Guest: `/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/kdlock-continue-run-2d8eb6e35049-jh0fkiq3/processes/kd`.
- Local: `/tmp/kdlock-continue-collected-links/evidence.tar`, 702,443,520 bytes,
  SHA256 `5443989842032f11b045cd416f72df3a34520897fd0ae47498ec2f6967bc47cb`.
- All 445 indexed entries were verified, including literal workspace link
  metadata without following targets. The initial collector stopped on a
  workspace link; its failed receipt remains under `/tmp/kdlock-continue-collected`.

The earlier g7 compilation took `113.243566075` seconds, almost entirely CPU
time; `106.031755470` seconds was the portion remaining after application exit.
Its 26,102 instructions are a static decoded-source inventory, not an execution
count or a count wholly inside the write critical section. Saved assembly
contains post-release continuations. Per-stage costs and a reliable numerical
inside/outside split are unavailable. See [the saved scope review](prior-g7-scope.md).
