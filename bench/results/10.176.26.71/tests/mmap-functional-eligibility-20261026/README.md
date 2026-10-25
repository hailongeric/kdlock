# Offline mmap eligibility and Native-control reuse

Implementation `9b6bb11` passed **99 focused Python tests**, the **two basic
userspace programs**, and a fixed-client build with `-O2 -g -Wall -Wextra
-Werror -pthread` in the recovery VM. The real saved Native fixed proof and all
**21 timed controls** imported and replayed successfully, including replay from
a second directory containing identical importer bytes. No control was rerun.
This is offline tooling/build evidence, **not new actual mmap runtime validation**.

The final policy is `mmap-functional-v1`: only normal functional completion
without a captured sleeping-writer bracket can report `inconclusive`. Strict
mode, positive-proof verification, exact identity/accounting, fault checks,
drain and measurement endpoints remain mandatory. Unknown/mixed policies,
arbitrary command failures and malformed positive proofs fail. The fixed-only
build reused the existing payload and timed binary exactly. No kernel/MM code,
timed workload, module state or boot setting changed.

The lock baseline remains audited `e6fc371`; the final frozen test snapshot was
prepared from `b8d9137` plus the file-bound changes now committed in `9b6bb11`.
The existing 137 Native / 161 KD actual-mm assertions and 352 standalone
assertions were not rerun. Historical failed observations remain failed.

## Checks and retained failures

| Check | Result |
| --- | --- |
| Initial `checks-1` | Two basic programs passed; 96 of 98 Python tests passed, two fixture errors |
| Corrected `checks-2` | 99 tests passed, including an added report-replay check |
| Final `checks-3` after relocation handling | All 99 passed; no skips |
| Real C completion helper | Strict/functional × observed/missing: four outcomes checked within the Python suite |
| Fixed client | Compiled only; no device open or mmap workload execution |
| Original Native import/replay | One strict fixed proof and 21 controls verified from saved raw records |
| Rejection checks on actual receipts | Modified observation verdict and failed historical KD receipt rejected |
| Archive/source inspection on 380G10 | All three source snapshots, final receipt hashes and archive member types verified |

The initial errors were
`test_run_inherits_case20_and_checks_both_validation_plans` and
`test_run_inherits_plan_and_refuses_legacy_predecessor_before_launch`.
Their mocks returned generic mock objects instead of receipt dictionaries;
the new policy check rejected them with `unknown mmap eligibility policy`.
Fixtures now return explicit legacy strict metadata. No production check was
weakened. Logs and the first frozen source remain retained.

The final relocation change permits identical reviewed code to move to the
maintained checkout. Replay still verifies saved importer/rule files, compares
their hashes with executing code, recomputes the full compatibility verdict and
preserves original provenance paths. Independent review accepted the bounded
integration and this delta; runtime policy validation remains prospective.

Commands executed in private VM snapshots under
`/root/kdlock-evidence/10.176.26.71/tests/mmap-functional-eligibility-20261026/`:

```sh
make -C offline-1/source/tests/unit run PY_TESTS=
cd offline-3/source
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/unit/bench \
  /root/kdlock-translation-venv-20261019/bin/python3 -m unittest -v \
  test_mmap_eligibility test_mmap_reuse test_mmap_paired \
  test_mmap_scaling test_mmap_throughput test_mmap_window
```

The exact fixed-build/import/replay command arrays are retained in the source
raw `*-request.json` files, with exit status and completion state in matching
transport records. Every command completed; no timeout or signal was used.

## Reusable inputs and evidence

The prepared fixed client is at `offline-2/fixed-build/result.json`; its
original source dependencies are preserved under `offline-2/prior-source/`.
The final compatibility receipt is `offline-3/native-compatibility.json` and
the final reviewed sources are `offline-3/source/`. These paths are relative to
the guest evidence base above. Keep them and all bound older build/control/API
inputs. Absolute bindings require those retained paths; do not overwrite old
receipts or reconstruct a new execution by changing their hashes.

| Artifact | SHA-256 |
| --- | --- |
| Final source archive `source-3.tar.gz` | `7a1bb9350c7c2864b5c80a7aa7b25d80b165fc760c184a1de1ea1d9283125333` |
| Compatibility rules | `00fcd4a4326b7d87fdb236e087295501df81b35bbcc54cef5461747492d2b8e4` |
| New fixed binary | `50b206a13d6cd277a2e69b1628e4202feab5df142a1a26c7614c2e4d390daef5` |
| Fixed-build receipt | `ca742eb7fce9fec233f91508a0c1d0c239865aa873a066143cd05fe7e5880642` |
| Final Native compatibility receipt | `e9517c5c704641666340ec406e600abab2e9bf33af7e7d79507fb331012bf78f` |
| Reused payload | `78210ced79da6b70132e41cc2c7a9ac289f83f0380479d1d24556c5a5403686f` |
| Reused timed binary | `5962210671ac238ae4df8dcca442b3cb7407efb2b5b2edb42ae637ac4902083f` |

Saved-evidence replay in the VM, without workloads or fresh admission:

```sh
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
  /root/kdlock-translation-venv-20261019/bin/python3 - <<'PY'
from pathlib import Path
import sys
base = Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-functional-eligibility-20261026')
sys.path.insert(0, str(base / 'offline-3/source/bench/mmap_lock'))
import paired
row = paired.validation_receipt(base / 'offline-3/native-compatibility.json',
    'native', paired.bind(base / 'offline-2/fixed-build/result.json'), paired.SCALING_PLAN)
print(row['passed'], row['writer_observation'], row['compatibility']['controls'])
PY
```

Source raw records:
`bench/results/10.176.26.71/raw/tests/mmap-functional-eligibility-20261026/`.
Its 216-file inventory SHA-256 is
`c7d8cd8088b6914e3af35f6b5fa3d5ae16c9f8a613fb0898ed0c32275eaf6894`.
The guest archive is **4,689,470 bytes**, with 1,123 regular files totaling
11,799,159 bytes; SHA-256
`270e639510b5096eb60bc85269b369353b57fa3e46d30ff00253eee6b76d0431`.
Archive and source-host copies matched. No recovery artifact was removed.

## Recovery and next stage

Final read-only health at `2026-10-25T21:06:55.154989+00:00` (05:06:55 on
October 26, Asia/Shanghai) recorded `6.1.159-kdclobber2`, unchanged boot
`d0d9b420-d956-4bb6-8405-eea7b427baca`, the exact original **73 modules**,
**taint 0**, empty `next_entry`, and no project processes or open project files.
Root had 4,300,181,504 bytes free. No reboot, module load/unload, live diagnostic,
kernel build/install, measured session or optimization occurred in this stage.

The [policy guide](../../../../mmap_lock/THROUGHPUT_POLICY.md) gives compatible
continuation commands and reduced bounds: 126 measurements, 148 payload cycles,
five boots, 384 captures and 3 GiB reserve per retention filesystem. Fresh
readiness, artifact checks, capacity and admission remain prerequisites for the
separately authorized live cycle. This receipt supplies no throughput result,
latency distribution, fairness proof or performance gain.
