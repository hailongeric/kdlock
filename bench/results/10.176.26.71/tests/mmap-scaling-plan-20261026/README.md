# Expanded plain mmap plan: offline validation

`plain-scaling-v1` prepares exactly 21 counts:
`1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60`.
Native/KD × three repetitions gives **126 measured sessions per workload**.
Only the existing shared-mm writer driver is implemented here. This is offline
tooling validation; **no expanded workload, host capture, module or kernel work
ran**, and it establishes no actual-mmap correctness or performance gain.

The recovery VM ran **41 mocked tests, all passed, in 0.186 seconds**:
14 directly affected historical paired tests, 11 smaller-plain-plan fixtures
and 16 new scaling fixtures. Exact command in the frozen VM snapshot's
`tests/unit/bench` directory:

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C \
  /root/kdlock-translation-venv-20261019/bin/python3 -m unittest \
  test_mmap_paired test_mmap_throughput test_mmap_scaling -v
```

The new fixtures check the literal grid/order; all 21 controls and the fixed proof
for both modes through mocked calls; partial failure receipts; case 20/21 CLI
boundaries; refusal to reuse expanded indices with older readiness; exact
predecessor/boot/input/plan bindings; completeness; positive finite throughput;
zero latency observations; variability, equal results and regressions; and
explicit resource assumptions. Guards reject real subprocess, socket and command
calls unless a test mocks the specific path. Existing tests retain the original
67-task rejection and independent drain after invalid endpoint evidence. They
also retain the 24-session missing-plan interpretation and 12-session `plain-v1`
report behavior. No test result is a live safety or full Native-equivalence proof.

The [maintained runner guide](../../../../mmap_lock/README.md#plain-throughput-plan)
records the derived bounds and runnable estimate command: 44 unscored checks,
170 payload cycles, 259 captures, six boots, 639 dmesg dumps, no warmups.
The default assumptions estimate 44 min 36.8 s and 2 GiB per retention filesystem;
these are planning inputs, not observed performance or a live authorization.
No client, payload, host gate, diagnostic code or lock implementation changed.

Source base: `ea9241d98629e4f2ac9bf4f327557fc21ab33b7c`. Stable review snapshot:
`bench/results/10.176.26.71/raw/tests/mmap-scaling-plan-20261026/checkpoint-2/`.
The test archive contains **133 files / 1,246,242 source bytes**, compressed to
**331,260 bytes**, SHA-256
`dd665c643d81db4cc242f8c49640645cbb325495b3d85cab3f0f98ebb0b6e297`.
The file-manifest SHA-256 is
`dbac37f9210ae32d4ed01a6484ef4d88e81e6da70f1af12f4bd94c261ca172fb`.

| Tested source | SHA-256 |
| --- | --- |
| `paired.py` | `0e38d744fa00250703739757d18b6388219898c9ff1b7aebe280d71134394535` |
| `report.py` | `0a40e2f3ced6954d1a054e84fc3b0f981957c6b75c1f5396945cba4ddb9d47b9` |
| `test_mmap_scaling.py` | `617e45c90cb248760d88bbddcd59bf16f45f41af4d9ea62bee8fef8f4b09fd90` |

Raw source, command, stdout/stderr and transport receipts are retained under
`bench/results/10.176.26.71/raw/tests/mmap-scaling-plan-20261026/` on 380G10.
Guest evidence is
`/root/kdlock-evidence/10.176.26.71/tests/mmap-scaling-plan-20261026/checks-1/`.
All frozen hashes matched after testing; transport and test completion are
confirmed. Before/after checks passed on recovery `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, the exact original 73 modules, taint 12288
and empty `next_entry`. The maintained guest source was not synchronized.

Independent read-only review matched checkpoint, archive and working source
hashes, the 41-pass receipt and health records. It found no material matrix
defect; schema/order preservation, resource arithmetic and retained validation
boundaries were checked. That reviewer ran no additional tests.

The earlier actual mmap 137 Native/161 KD assertions and standalone 352 assertions
plus two basic programs remain reused, separate evidence. No C/kernel build or
basic test was repeated for this Python runner/report change. The historical
73/68-task admission failures and first failed diagnostic remain rejected;
qualified current throughput remains zero.
