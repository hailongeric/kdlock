# Prepared mmap window: offline tooling validation

The prospective `mmap-window-v2` interface adds prepare/start/completion/export
barriers around the existing 4 KiB shared-mm userspace mmap/munmap workload.
It keeps the original 21-count `plain-scaling-v1` matrix and preserves the
default historical policy. No kernel, lock implementation, MM algorithm or
payload source changed. The audited lock baseline remains `e6fc371`.
The tooling is committed locally as
`b42db2718d8bbac4e1b8fff20749f368f17f3b71`.

The final affected Python run passed **85 tests in 0.819 seconds**: 28 window
tests and 57 directly affected capture/paired/plain/scaling tests. The unchanged
C sources also passed **21 deterministic transport assertions**, both basic
unit programs, and the client/helper builds with `-O2 -g -Wall -Wextra -Werror`
(plus `-pthread` for the client). All execution took place in private recovery
VM directories. No module, host observer, real mmap payload workload, benchmark,
source synchronization, kernel build/install or reboot ran in this checkpoint.

The fixtures exercise socket closure, partial writes, EINTR, sustained
backpressure, expired/unterminated reads, final bytes after a deadline, lost
commands, duplicate/out-of-order commands, premature publication, completion
tokens, endpoint hashes, uncertain completion, bounded output and policy replay.
They check legitimate core/expected-service activity separately from inactive
auxiliary activity; sleeping observations with CPU/scheduling/I/O changes reject.
Identity replacement, affinity drift, invalid/regressing counters and incomplete
coverage also reject. Shell-form commands containing `cd`, `&&`, spaces and
quotes preserve their arguments and deliver the case nonce to the final program.
These are fixture/IPC results, not actual mmap runtime validation or proof that
the host observation policy has negligible cost.

The retained attempts are:

| Attempt | Frozen source | Result |
| --- | --- | --- |
| 1 | source-1 | Remote bootstrap quoting produced a SyntaxError before any guest statement/test ran. |
| 2 | source-1 | Both basic programs, both compiles and 21 C assertions passed; 83 Python tests executed with three subcase errors in one legacy replay fixture. |
| 3 | source-2 | Both basic programs, both compiles, 21 C assertions and 84 Python tests passed; Python duration 0.757 s. |
| 4 | source-3 | Final launch-quoting correction and fixture: 85 Python tests passed in 0.819 s. Unchanged passing C/basic checks were reused. |

The legacy fixture's mocked validation function now returns a receipt dictionary
instead of a MagicMock, allowing the new policy binding check to reach its
intended deleted/substituted-capture assertions. No acceptance check was removed.
All failed logs and earlier source snapshots remain retained.

Exact final Python command, from the private frozen VM source root:

```sh
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/unit/bench \
  /root/kdlock-translation-venv-20261019/bin/python3 -m unittest -v \
  test_mmap_window test_mmap_scaling test_mmap_paired \
  test_mmap_throughput test_mmap_capture
```

The other successful commands were:

```sh
make -C tests/unit run PY_TESTS=
gcc -O2 -g -Wall -Wextra -Werror -pthread -Iworkload_modules/mmap_writer \
  bench/mmap_writer/timed_client.c -o CHECKS/timed-client
gcc -O2 -g -Wall -Wextra -Werror tests/unit/bench/test_mmap_control.c \
  -o CHECKS/test-mmap-control
CHECKS/test-mmap-control
```

Raw evidence is retained at
`bench/results/10.176.26.71/raw/tests/mmap-window-20261026/` on 380G10 and
`/root/kdlock-evidence/10.176.26.71/tests/mmap-window-20261026/` in the guest.
Source archive numbers differ from guest attempt-directory numbers:
`checks-3/source-3` used source-2; `checks-4/source-4` used source-3.
Each result binds its exact source manifest. The final source-3 archive has
390 files, **3,345,964 source bytes**, and **859,771 compressed bytes**, SHA-256:

`d05a1ccfdf9901317be659b7c40c94e3ad5f0464ae9af4836643f0d8dfc5540f`

Final executable source hashes include:

| File | SHA-256 |
| --- | --- |
| `bench/mmap_lock/window.py` | `8a9913cd2bf8a74e5b1e0af5d16738bb2ca1d9c97b90ed553a917c760ea37fff` |
| `bench/mmap_lock/window_host.py` | `c6ce998ff3dfe33abc42803e4169e16ca7330cf26717ae8de237d654d4dbd101` |
| `bench/mmap_lock/window_controller.py` | `60d6bb81838e605e5e7c189da417bf531e19e003f89375c6b6a5ad89aedfab45` |
| `bench/mmap_writer/control.h` | `30debdeab36bdc0b9bc48cd25537a9bb4a7d67b1accc103a0c46d1cb7b2b6a88` |
| `bench/mmap_writer/timed_client.c` | `5e22a193e95ffb887db3afb4b4d74d12cb0b904eaf7a5762cacb9686f3813c85` |

Independent read-only review found and prompted fixes for bounded C sends,
failed STARTED delivery, premature EXPORT, publication/selector ordering,
bounded Python transport reads/writes and replay token/hash consistency. Its
final limited check verified shell-command propagation, bounded bootstrap input,
the source-3 archive hash and 85-test receipt, with no remaining finding in that
check. It executed no tests or live helpers. Documentation was reconciled after
the tests; executable input hashes still match source-3.

Latest post-test health: **2026-10-26 02:17:47 Asia/Shanghai**
(`2026-10-25T18:17:47.736399+00:00`), recovery `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, exact original 73 modules, taint 12288,
CPUs 0–63, voluntary preemption and empty `next_entry`. Before/after identity,
policy and dmesg matched; no competing project process or open project file was
detected. This is the observed checkpoint, not a claim about later VM state.

The next live scope is the separately reviewed
[two-arm screen](../../../../mmap_lock/README.md#small-matched-validation-screen).
It requires bound auxiliary-role evidence and fresh equivalent conditions.
No new actual mmap assertion count, qualified throughput, latency result or
performance gain follows from this offline checkpoint. Historical rejected
diagnostics and the unrelated disk-cleanup README remain unchanged.
