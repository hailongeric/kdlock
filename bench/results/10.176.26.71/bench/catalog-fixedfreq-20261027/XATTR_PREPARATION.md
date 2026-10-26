# Xattr preparation coverage

**One retained attempt per coordinate; no reruns.** This compares failed preparation outcomes, not throughput across sources. All eight current xattr workloads are archive-audited.

| Workload | Historical KD failures /21 | Current KD failures /21 | Current KD measured /21 |
|:---|---:|---:|---:|
| `xattr-front-n16` | 12 | 21 | 0 |
| `xattr-front-n128` | 15 | 20 | 1 |
| `xattr-tail-n16` | 1 | 21 | 0 |
| `xattr-tail-n128` | 16 | 21 | 0 |
| `xattr-miss-n16` | 0 | 13 | 8 |
| `xattr-miss-n128` | 3 | 21 | 0 |
| `xattr-size-n16` | 0 | 3 | 18 |
| `xattr-size-n128` | 0 | 19 | 2 |

For matching completed workloads, failures increased from **47/168** historical KD attempts to **139/168** current attempts. The increase is measured; its cause is not established.

The exact refusal is `helper learning did not establish complete delegation within configured waves`. A failed point has no timed measurement or throughput. These attempts completed their syscall/oracle checks and drained; this signature is neither a translation timeout nor a data-correctness or teardown failure.

Preparation is identical at every nominal worker count: up to four bounded helper waves, CPUs 0–7, at least 48,000 operations per helper and at least 1 second per wave. The helper-ready predicate requires a NORMAL image **and at least one returned delegated body**. This prerequisite remains in force when the later timed point allows NO_JIT. A nominal 60-worker failure therefore happened in the same eight-worker preparation cohort, before its 60-worker timed cohort started.

The unchanged spin admission code checks for an outside holder, a queue head and six linked successors at or before the captured tail. With only eight helper workers, this demands the entire cohort be at the lock at the observation instant. Short protected work and syscall work outside the lock can prevent that queue depth. This is a source-grounded explanation for sensitivity of the preparation policy; the archives do not count individual admission vetoes and therefore do not prove that this condition caused the increased failure incidence.

The two current front cases illustrate the failure signature: 41 of 42 KD attempts failed, versus 27 of 42 previously. Those 41 failures completed 164 valid helper waves and 630,913,536 syscalls with **zero JIT entries and zero returned bodies**, despite a byte-matched NORMAL generation 1 image (1,592 bytes, requirements 20). Their retained kernel counters have zero batch entries/direct `strcmp` calls and final `cpu_hot=0` snapshots. Final heat counters describe unfinished windows, not lifetime admission decisions; historical n16/t40 failed preparation despite one CPU finishing hot. The sole new front success (n128, t12) progressed through a partial entry to generation 2 / 1,648 bytes and then returned 708,096 helper bodies. Historical front successes also reached generation 2; some later timed NO_JIT, so preparation success is not itself timed returned-body evidence.

No preparation-policy change was found: plans differ only in source identity, and the kernel/topology identifiers, helper settings, provider arguments, API runner/client, xattr body, translator and spin/hotlock sources match. Client and daemon binaries are byte-identical. For the retained front-n16 ELFs, all 8 functions in each xattr payload match in bytes and canonical relocations. Of 361 provider functions, 356 match; the five differences are mutex functions, while all 90 spin/hotlock functions match. Whole provider/module hashes and loaded addresses still differ; this is not proof of identical runtime behavior.

The current fixed 2.0 GHz host policy, earlier variable-frequency environment, elapsed run state and module layout are distinct experimental conditions. There is no controlled factor comparison assigning this preparation-coverage change to frequency or any one condition. Preserve the failures; do not convert them to zero throughput or enlarge the cohort within this frozen campaign.

[Evidence-bound analysis and per-case counts](../../raw/bench/catalog-fixedfreq-20261027/xattr-failure-analysis.json) and [reproducible offline helper](../../raw/bench/catalog-fixedfreq-20261027/xattr-failure-analysis.py). The JSON binds both campaigns’ full archives and records, current public audits, per-case sessions/kernel logs and exact ELF comparisons. Strict timing qualification remains failed.
