# Actual-MM serial campaign results, 2026-10-22

**All 24 sessions completed correctly and drained. All 24 fixed endpoints failed; zero sessions qualify for performance acceptance.** These are retained diagnostic rates, not accepted comparisons or evidence of a causal fix.

The single coordinator ran six distinct boots in Native/KD, KD/Native, Native/KD order. Each block ran untouched shared-mm mmap/munmap at 1/16 workers, then independent-mm fault cycles at 1/16 workers. Readers stayed local and writers stayed on their original task; no TCLock MM case ran. Frozen binaries and the candidate image were unchanged. Both-mode correctness was reused; no API suite was repeated.

Candidate Build ID: `687ff5a29315d732f93a618e50ac407c794bbf9b`. Frozen input manifest: `69271dff3cbb70e098a0b7157125b32a97ee7499b5903a539d0259bc5dff9b6f` (683 bindings, nine binaries). Serial wrapper revision `78a1b04`; source coordinator `27d4d5e`.

There were 85 retained readiness/session host observations, including 55 ineligible observations. All six readiness checks and all 24 session admissions passed the full original gate. Every fixed endpoint retained the original 67 tasks plus extra workers: counts ranged from 68 to 70. Later quiet observations never replaced those endpoints.

## Every repetition

Rates below are Mops/s. Every row passed business validation and normal drain, and every endpoint is rejected. Full-precision values, receipt hashes and artifact paths are in [session-results.json](session-results.json) and [CSV](session-results.csv).

| Run | Repeat | Completed operations | Whole Mops/s | Conservative peak Mops/s | Endpoint threads |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mm-block-0-native/case-0-mmap-1` | 0 | 759,968 | 0.379977 | 0.446267 | 68 |
| `mm-block-0-native/case-1-mmap-16` | 0 | 228,352 | 0.113950 | 0.119464 | 69 |
| `mm-block-0-native/case-2-fault-1` | 0 | 525,952 | 0.262972 | 0.268785 | 68 |
| `mm-block-0-native/case-3-fault-16` | 0 | 8,668,672 | 4.334119 | 5.482675 | 68 |
| `mm-block-1-kd/case-0-mmap-1` | 0 | 745,024 | 0.372507 | 0.450509 | 68 |
| `mm-block-1-kd/case-1-mmap-16` | 0 | 66,496 | 0.033182 | 0.041813 | 68 |
| `mm-block-1-kd/case-2-fault-1` | 0 | 526,080 | 0.263032 | 0.266226 | 68 |
| `mm-block-1-kd/case-3-fault-16` | 0 | 7,738,880 | 3.869162 | 5.064123 | 69 |
| `mm-block-2-kd/case-0-mmap-1` | 1 | 751,840 | 0.375911 | 0.460764 | 68 |
| `mm-block-2-kd/case-1-mmap-16` | 1 | 67,136 | 0.033505 | 0.040960 | 68 |
| `mm-block-2-kd/case-2-fault-1` | 1 | 525,760 | 0.262871 | 0.264526 | 68 |
| `mm-block-2-kd/case-3-fault-16` | 1 | 8,442,272 | 4.220934 | 5.497155 | 68 |
| `mm-block-3-native/case-0-mmap-1` | 1 | 712,864 | 0.356427 | 0.357799 | 68 |
| `mm-block-3-native/case-1-mmap-16` | 1 | 223,264 | 0.111385 | 0.117759 | 68 |
| `mm-block-3-native/case-2-fault-1` | 1 | 526,784 | 0.263381 | 0.264533 | 69 |
| `mm-block-3-native/case-3-fault-16` | 1 | 8,872,896 | 4.436260 | 5.177472 | 70 |
| `mm-block-4-native/case-0-mmap-1` | 2 | 717,984 | 0.358983 | 0.360106 | 68 |
| `mm-block-4-native/case-1-mmap-16` | 2 | 226,880 | 0.113211 | 0.119773 | 68 |
| `mm-block-4-native/case-2-fault-1` | 2 | 526,496 | 0.263241 | 0.265076 | 68 |
| `mm-block-4-native/case-3-fault-16` | 2 | 8,842,400 | 4.421061 | 5.505558 | 68 |
| `mm-block-5-kd/case-0-mmap-1` | 2 | 715,616 | 0.357800 | 0.360143 | 68 |
| `mm-block-5-kd/case-1-mmap-16` | 2 | 62,432 | 0.031153 | 0.040960 | 68 |
| `mm-block-5-kd/case-2-fault-1` | 2 | 525,760 | 0.262873 | 0.264533 | 69 |
| `mm-block-5-kd/case-3-fault-16` | 2 | 8,626,496 | 4.313044 | 5.488401 | 68 |

## Descriptive spread of rejected observations

Each group has three observations and zero qualified observations. CV is 100 × population standard deviation / arithmetic mean. Min/median/max preserve boot-block variation; three observations do not establish significance. All values are diagnostic and cannot support performance acceptance.

| Task / workers | Mode | Whole min / median / max Mops/s | Whole CV % | Peak min / median / max Mops/s | Peak CV % |
| --- | --- | --- | ---: | --- | ---: |
| mmap / 1 | native | 0.356427 / 0.358983 / 0.379977 | 2.890 | 0.357799 / 0.360106 / 0.446267 | 10.610 |
| mmap / 1 | kd | 0.357800 / 0.372507 / 0.375911 | 2.131 | 0.360143 / 0.450509 / 0.460764 | 10.668 |
| mmap / 16 | native | 0.111385 / 0.113211 / 0.113950 | 0.955 | 0.117759 / 0.119464 / 0.119773 | 0.744 |
| mmap / 16 | kd | 0.031153 / 0.033182 / 0.033505 | 3.192 | 0.040960 / 0.040960 / 0.041813 | 0.976 |
| fault / 1 | native | 0.262972 / 0.263241 / 0.263381 | 0.065 | 0.264533 / 0.265076 / 0.268785 | 0.710 |
| fault / 1 | kd | 0.262871 / 0.262873 / 0.263032 | 0.029 | 0.264526 / 0.264533 / 0.266226 | 0.302 |
| fault / 16 | native | 4.334119 / 4.421061 / 4.436260 | 1.023 | 5.177472 / 5.482675 / 5.505558 | 2.775 |
| fault / 16 | kd | 3.869162 / 4.220934 / 4.313044 | 4.626 | 5.064123 / 5.488401 / 5.497155 | 3.778 |

| Task / workers | Whole KD/Native, repeats 0 / 1 / 2 | Peak KD/Native, repeats 0 / 1 / 2 |
| --- | --- | --- |
| mmap / 1 | 0.980342 / 1.054664 / 0.996704 | 1.009505 / 1.287774 / 1.000102 |
| mmap / 16 | 0.291196 / 0.300803 / 0.275174 | 0.350007 / 0.347827 / 0.341978 |
| fault / 1 | 1.000231 / 0.998063 / 0.998602 | 0.990479 / 0.999974 / 0.997954 |
| fault / 16 | 0.892722 / 0.951462 / 0.975568 | 0.923659 / 1.061745 / 0.996884 |

These ratios include rejected endpoints and are unaccepted. In particular, the observed 16-worker mmap whole-rate ratios of 0.275–0.301 require a qualified follow-up before an environment-controlled performance conclusion. The other observed whole-rate ratios also remain unqualified. The fault task includes PTE reset and uses independent process/mm instances; it does not measure isolated fault handling or same-mm contention. Callback/progress overhead is unisolated. New p95 and sampling-cost measurements remain deferred.

The unchanged [stock summary](campaign-summary.json) assigns block-level endpoint status to all four rows. The per-case companion above retains the actual session statuses; all happen to fail in this campaign. The summary source SHA-256 remains `dc332eea7f81902ec6903a842d0dc2314d7e1451237eaa9dd75dd74876d640dc`.

## Run and archive identities

| Block | Mode / repeat | Boot ID | Archive manifest SHA-256 |
| ---: | --- | --- | --- |
| 0 | native / 0 | `f1b7a12f-aba2-4b94-b711-a736676f22aa` | `c355b2d9d5f87f41113fbed24ccf25a717e7f7d2de0507158397c5a7c1dcf56f` |
| 1 | kd / 0 | `08809fb2-55d3-4dc0-9be0-85af91171609` | `30d4dda7462c57b76e074222dd86e71eed35bdc287d7ead3fbd721570b164d2c` |
| 2 | kd / 1 | `7370eeed-5dba-4550-94aa-8bd361ce3f29` | `03196251f811d81ec7e5f3c6e978eb0c3b6d0623bdb4c12dc0bfb543a971ac06` |
| 3 | native / 1 | `f0794861-fa8c-43b1-8452-eacb4dbf00fb` | `68781f37c91688fe1b592b390b49d80735c00286e31817c4258cb819d0a2c9a9` |
| 4 | native / 2 | `ccc554a0-d84b-4cb5-a923-9abd62c51430` | `9993eeb2c88b6e3eed43701aecff9d03b6552b9f041b2647db0af2ca6c36ef64` |
| 5 | kd / 2 | `bc33af7c-d6d3-4d03-b2f2-dd063338d0b7` | `3964359aba3855cc2732a4be8d1df04c004eda14b6e40c074d7b761bc5098a4e` |

Each block has `transition.tar.gz` and `metadata.tar.gz` in `raw/tests/serial-continuation-20261022/campaign-1/block-<index>-<mode>/archives`. The source-side directory also retains every command/PID receipt, admission observation, lifetime scan, fixed endpoint, controller and copied result. [Independent audit records](campaign-archive-reviews.json) preserve the completed reviews. Earlier eight actual-MM archives and six RCUHT archives remain unchanged, as recorded in [preservation review](preservation-review.json).

The [artifact index](artifact-index.json) binds all 31 retained archives and
their sizes/hashes. Final control manifest
`8e2dc5ede7f1075d1a70050ccc1a66c7575223e0079dd512bfa21d0fed2b942d`
seals the source-side histories, validation receipts, summary and recovery logs.
The [independent summary audit](summary-review.json) reproduced all 24 rows,
eight groups and twelve paired ratios without mismatch. Documentation was
reviewed read-only with no blockers and no helper file edits.
The sealed source-control report is the snapshot taken before final archive
links were added. Its original CSV uses CRLF; the maintained CSV uses LF with
identical cells. Sealed bytes and their captured hashes remain unchanged.
The [final seal audit](final-archive-review.json) found no artifact-integrity
gaps across 1,349 regular files and all 24 immutable result bindings.

## Recovery and unresolved gaps

Recovery is restored to `6.1.159-kdclobber2`, boot `e8e0a914-ef13-4063-ab95-e5e89c1eb7da`, with the exact 73-module set and preserved recovery/default/module artifacts. The final retained log has no configured kernel-fault signature. Known floppy boot I/O messages remain retained. See [recovery transition](recovery-transition.json), [fresh final health](final-health.json), and [summary receipt](summary-receipt.json).

| Original regression | Disposition |
| --- | --- |
| c08 / 3 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| c08 / 4 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| c08 / 5 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| pipebytes / 3 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| pipebytes / 5 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| pipecap / 5 workers | Unresolved; this actual-MM campaign supplies no causal resolution |
| RCUHT / 2 workers | Unresolved; this actual-MM campaign supplies no causal resolution |

Qualified actual-MM repetitions and their variance remain unresolved (qualified n=0). The reported variance describes all rejected observations only. The added workers' initiating operations, activity during measurement and causal effect on rates are not established. Endpoint chronology proves immediate local request ordering, not instantaneous remote sampling. This stage does not validate arbitrary delegated MM bodies, all callbacks, RT/lockdep or whole-kernel replacement.
