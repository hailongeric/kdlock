# Final independent evidence review

The final captured inputs include the corrected CONFIG_RETHUNK return sequence, which uses the kernel return helper. Captured runtime, test and runner inputs match the reviewed checkout; documentation differences are listed separately.

Archive and recorded-data checks passed (5,622 checks). This review read archives without extracting or running their code. No repository tests or VM work were executed.

| Archive | Source files | Binary files | Recorded outcome |
| --- | ---: | ---: | --- |
| `native-escape-units-20261018-03.tar.gz` | 387 | 0 | PASS |
| `native-escape-live-20261018-03.tar.gz` | 177 | 4 | PASS |
| `native-escape-rwsem-20261018-02.tar.gz` | 234 | 5 | PASS: two functional rwsem sessions |

All archive sizes and SHA-256 hashes match the imported manifest. Frozen source, prepared provider inputs, recorded binaries and live published-image hashes were checked against their captured manifests.

`native-escape-units-20261018-03.tar.gz` records 18 successful basic/affected commands, including two basic C programs and 214 Python unittest cases. No recorded test was skipped. The restore fixture reports all 64 arithmetic-flag combinations; this is separate from the live workload. Expected daemon error-handling diagnostics remain in the basic log.

`native-escape-live-20261018-03.tar.gz` completed 6,400,000 operations with exact prefix/suffix counts, zero worker errors and complete retirement:

| Phase | Operations | Generated-code entries | Completed generated bodies | Instruction exits |
| --- | ---: | ---: | ---: | ---: |
| cold-warmup | 1,600,000 | 1,130,210 | 1,130,210 | 0 |
| cold-delegated | 1,600,000 | 1,479,585 | 1,479,585 | 0 |
| hot-escape | 1,600,000 | 1 | 0 | 1 |
| post-ban | 1,600,000 | 0 | 0 | 0 |

The instruction event matches the source instruction address, image version and a recorded worker process. The native continuation started, completed and unlocked once; later calls produced zero generated-code entries and retained the disabled registry state. Kernel logs contain no matched runtime fault. Build warnings remain recorded, but the new marker restore has no bare-return warning after the CONFIG_RETHUNK correction.

The two rwsem checks each completed 3,200,000 measured operations (640,000 reads and 2,560,000 writes), with all 16 workers progressing and source retirement complete. Generated writer completions were 860,947 and 224,329. Their separate warmups and recorded protected-data totals also agree.

Initial failures remain evidence: unit01 refused RDTSCP because the decoder called its bytes `INVLPG ECX`, and its restore fixture was missing from the snapshot; live01 completed correct local work but returned no generated bodies because Python workers did not match `target_process=kd_test`. Neither failed attempt is counted as a pass.

See [the machine-readable review](final-review.json) for hashes, exact input counts, retained warnings and validation limits.

The final guest was idle with no retained project modules or worker tasks. Its boot identity, CPU set and boot arguments match preflight. The restore fixture passed all 64 arithmetic-flag combinations in each of the ordinary-return and CONFIG_RETHUNK configurations.

Current-source comparison counts (runtime / tests / runners / other captured inputs):

- `native-escape-units-20261018-03.tar.gz`: 117 / 159 / 18 / 4.
- `native-escape-live-20261018-03.tar.gz`: 118 / 16 / 21 / 10.
- `native-escape-rwsem-20261018-02.tar.gz`: 118 / 30 / 35 / 51.

Captured documentation differences: {"native-escape-live-20261018-03.tar.gz": ["disassem/README.md"], "native-escape-rwsem-20261018-02.tar.gz": [], "native-escape-units-20261018-03.tar.gz": []}.

This remains basic plus affected validation. It does not claim a full unit suite, a new performance comparison, or live execution of the other reviewed privileged instructions.
