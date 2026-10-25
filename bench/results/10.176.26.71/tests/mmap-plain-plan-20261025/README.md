# Plain mmap throughput plan preparation, 2026-10-25

The runner/report now supports an explicit **`plain-v1`** campaign: Native/KD,
1/16 shared-mm writers and three paired repetitions, all plain. **25 mocked
tests passed** in the recovery VM: 11 new plan tests and 14 directly affected
historical paired/report tests. No live diagnostic, capture, payload load,
benchmark, build, install, reboot or cleanup ran. The earlier 43 diagnostic tests
and prior basic/standalone/actual-mmap validation were reused without repetition.

The lock implementation audited at `e6fc371` is unchanged. This work changes
only `bench/mmap_lock/paired.py`, `report.py`, the new focused test and their
documentation. It reuses the existing plain timed client and build-3 artifacts;
no latency sampling, lock optimization or Native MM change was introduced.

## Binding and compatibility

`--plan plain-v1` is selected only by `ready`; bound readiness carries it through
validation, run, finish and saved-evidence replay. Missing plan fields mean the
original `paired-v1` 24-case schema. A 12-case set without an explicit plain plan
fails. Mixed/unknown plans, legacy predecessors/validations, missing or duplicate
records, incorrect boot/order/specification and sampled plain-plan output fail.
The valid historical report shape remains unchanged, including its sampled data.

The existing strict 67-task admission, image/mode/input/placement identity,
fixed writer proof and nine negative proof mutations, exact business/drain,
immediate endpoint and chronological predecessor requirements remain. A malformed
endpoint still permits independently proven normal drain while rejecting timing.
Plain reports retain each rate, paired ratios, median, min/max and sample CV,
including measured losses. They do not publish workload latency metrics.

Derived maxima are **12 measurements + 6 unscored checks = 18 payload cycles**,
**31 host captures** (1 initial + 5 readiness + 24 measurement boundaries + 1
recovery), and **6 boots** (5 candidate + recovery). Pair order remains K0/N0,
N1/K1, K2/N2. Adjacent repetitions share boots. The historical maxima remain
24 measurements, 10 unscored checks, 34 payload cycles, 55 captures and 6 boots.

## Exact offline evidence

A fresh guest snapshot holds 132 frozen source/dependency files, 1,221,617
uncompressed bytes, under
`/root/kdlock-evidence/10.176.26.71/tests/mmap-plain-plan-20261025/checks-1/source`.
The [source manifest](../../raw/tests/mmap-plain-plan-20261025/source-1.json)
and archive `source-1.tar.gz` retain those bytes. The archive is 326,844 bytes,
SHA-256 `2f282ec911fef21dad7eb908bf73a374083e694cfa9c2e05ae463a8282b24a34`.

| Changed source | SHA-256 |
| --- | --- |
| `bench/mmap_lock/paired.py` | `b64a241219eaf6b3161e5697f332f6b991ad3450f7cfedf8332720da1fd670ac` |
| `bench/mmap_lock/report.py` | `fc496db3eca2707858f398d7d7edbcad7d129c10ce501242b59d7c3306117fb2` |
| `tests/unit/bench/test_mmap_throughput.py` | `45bab25e7c6e1ce110bbeb1d61ca33fc1f6bebca7447eb8b4e70881f746dc7d4` |

From that snapshot's `tests/unit/bench` directory, the only test command was:

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C \
  /root/kdlock-translation-venv-20261019/bin/python3 -m unittest \
  test_mmap_paired test_mmap_throughput -v
```

It returned zero: 25 tests, no failures/skips, reported duration 0.073 seconds.
That is test metadata, not lock throughput. The
[result and complete log](../../raw/tests/mmap-plain-plan-20261025/checks-1.stdout),
[transport receipt](../../raw/tests/mmap-plain-plan-20261025/transport-1.json)
and [bounded execution wrapper](../../raw/tests/mmap-plain-plan-20261025/run-mocks.py)
are retained. All 132 source hashes matched afterward. Existing guest source and
frozen benchmark inputs were not synchronized or changed.

Before/after checks matched recovery `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, the original 73 modules, taint **12288**,
no pending boot and no conflicting processes in the bounded name scan.
The unrelated empty cleanup README remains untouched.

The [plain plan and commands](../../../../mmap_lock/README.md#plain-throughput-plan)
are ready for review. Live execution and the separate diagnostic remain
unapproved; the 73-versus-67 stop remains in force and qualified current
performance count is zero. Optional lock screens do not block this first mmap
baseline. Actual page-fault throughput needs its own later runner; private
backing-lock faults are not an equivalent substitute.
