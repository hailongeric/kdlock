# Offline preparation of the QEMU diagnostic, 2026-10-25

The new phase-separated diagnostic passed **43 mocked tests** in the recovery
VM. No live observer, QEMU capture, monitor query, guest diagnostic stimulus,
workload, module, build, kernel installation, reboot or cleanup ran. The prior
basic/standalone/actual-mmap checks were reused without rerunning them.
The 73-versus-67 campaign stop and zero qualified current performance cases
remain unchanged. Live diagnostic approval is still pending.

The documentation corrections are separately committed at `402179e`. They
preserve the seven mutex regression points, distinguish complete-operation p95
from acquisition latency, close the original 69-case nano execution gap, and
record the original TCLock rwsem port's limited API scope and selected completed
lock-only mmap integration. The audited lock implementation remains `e6fc371`.
No lock or Native MM body changed in this preparation.

## Tested inputs

The [raw source manifest](../../raw/tests/mmap-diagnostic-offline-20261025/source-2.json)
binds five frozen files. Source archive `source-2.tar.gz` has SHA-256
`4dbf6884668c84f487821bb869311b6e8b87adb24f6e8a3d9346a538cba7439a`.
The earlier `source-1` archive was an unexecuted preparation snapshot; it was
not a failed or successful test attempt.

| File | SHA-256 |
| --- | --- |
| `bench/mmap_lock/diagnostic_observer.py` | `b63e6f85a547a961300f99b8792be22f3611a66445e290da2eb5c8936ff8cd9c` |
| `bench/mmap_lock/diagnostic_controller.py` | `aae678d9ec1095c95389f655e83feed1ac93ac8935801e03f55bf37bf6e3720a` |
| `tests/unit/bench/test_mmap_diagnostic.py` | `60e53eabe0a5ae7d74d53a5b923a3ebc979ffa45b208b2c946f46b5ddecfd3a2` |
| `bench/mmap_lock/host_capture_control.py` (unchanged parser import) | `8a348f7a0977b2d01d99480deca026c3365477e740c6efb60f49ec274f2872a3` |
| `bench/mmap_lock/kdmm31.json` (unchanged retained identity) | `79aba1adc40eca61f9d8c9aef34908598bb84e947a48920877bd906b9c0ee940` |

The fresh VM copy is
`/root/kdlock-evidence/10.176.26.71/tests/mmap-diagnostic-offline-20261025/checks-1/source`.
All five hashes still matched after testing. Existing guest source and frozen
benchmark inputs were not synchronized or edited.

The only test command was:

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mmap-diagnostic-offline-20261025/checks-1/source/tests/unit/bench/test_mmap_diagnostic.py -v
```

It returned zero: 43 tests, zero failures/skips, reported duration 2.493 seconds.
This duration is test-run metadata, not a lock measurement. The
[retained result/log](../../raw/tests/mmap-diagnostic-offline-20261025/checks-1.stdout),
[transport receipt](../../raw/tests/mmap-diagnostic-offline-20261025/transport-1.json)
and [command/source wrapper](../../raw/tests/mmap-diagnostic-offline-20261025/run-mocks.py)
retain the execution and before/after recovery checks.

## Fixed preparation findings and limits

The draft's 250 ms cadence was restored to the proposed 500 ms. A nonzero-duration
fixture checks the strict scan-start gap; duration is not subtracted to admit a
longer interval. Scheduling jitter can stop this diagnostic before later phases.

Stop state and owned-socket cleanup now survive receipt-output failure. Tests
cover partial writes, backpressure, overflow, failed final flushing, read/identity
failures, monitor timeout/partial bytes, phase order and no later launches after
stop. The controller drains both available output streams before a queued stdin
write; a broken stdin pipe preserves those bytes. Interruption preserves earlier
guest completion acknowledgements. Timeout uncertainty stays sticky after a
later local SSH exit; no kill, signal, wait retry or fabricated drain is used.

The independent review found material issues in changing earlier snapshots. Its
review was not acceptance of these final bytes. The current hashes and test
receipt are available for read-only review; mocked passes do not establish live
safety, continuous task coverage, causality or performance qualification.
The [diagnostic guide](../../../../mmap_lock/DIAGNOSTIC.md) records exact
phases, bounds, in-flight request limits and the remaining live approval boundary.

Before and after this test, recovery matched `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, the original 73 modules, taint **12288**
and no pending boot. No conflicting build/module/test process was found by the
bounded name scan. This check did not repeat the broader artifact/recovery audit.
The unrelated empty `vm-disk-cleanup-20261022/README.md` remains untouched.
