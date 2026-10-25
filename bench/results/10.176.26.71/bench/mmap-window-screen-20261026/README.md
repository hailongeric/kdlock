# Prepared-window screen stopped at Native admission

The authorized 16-worker Native/KD screen stopped on October 26, 2026
(Asia/Shanghai), before any payload or timing. After the installed Native
candidate boot, the first full admission capture contained **82 QEMU tasks**.
The reviewed empty role manifest admitted only the original 67. All 15 extra
tasks were named `worker`, in state `S`, with affinity CPU 63. This single
observation neither proves inactivity nor identifies their creation cause.
No role was added, no admission was retried and no KD boot followed.

This attempt also **omitted settling after the guest idle check**. The
historical procedure required 60 seconds; later user instructions require
90 seconds. The attempt met neither and is retained as an execution failure. It cannot
establish that properly settled admission would fail or pass. No later quiet
observation can qualify this attempt.

## Inputs and completed preparation

- Source/tooling: `b42db2718d8bbac4e1b8fff20749f368f17f3b71`; reviewed commands
  and documentation: `aecd5d0b915a7ebb03c01d3f44165424d07b0d97`.
- Lock implementation and mmap overlay remain the audited `e6fc371` bytes.
  The earlier 137 Native / 161 KD actual mmap assertions and 352 standalone
  assertions plus two basic tests are separate evidence, not rerun here.
- Installed candidate: `6.1.159-kdmm31`, Build ID
  `ef5179e8def44f0255adcd62585f62f118fee30f`, image SHA-256
  `17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040`.
  No kernel was built or installed. Native selected `kd_mmap=off`.
- Reused unchanged build-3 payload and fixed client, bound by receipt SHA-256
  `34dcfa933162bcd068e340a8abd0b140ef9cd432bd9502de7aaca79377f8f2e0`.
  Only the controlled timed userspace client was rebuilt, with
  `gcc -O2 -g -Wall -Wextra -Werror -pthread`; its build-only receipt passed.
- Empty role manifest SHA-256:
  `4f0bd1486aadb5fae237421e8d976cf74ca5b10e1c1e845d0c88087255b580cb`.
  Initial recovery capture passed with 67 tasks before source sync/preparation.
  It was not reused as candidate admission.
- The idle source sync verified 347 selected files, including private `.inc`
  files, and copied 19 changed files. It excluded Markdown and the unrelated
  cleanup README edit. The guest tree was verified directly; this is not a
  claim that the benchmark host mirror was refreshed.

The first preparation launcher kept its own guest evidence log descriptor open.
The unchanged idle check rejected `/proc/12490/fd/3` before compilation. Parent
and child exited with status 1; no completion was uncertain. The corrected
invocation logged on the source host, used a new `client-build-2` directory and
exited 0. Both attempts remain preserved. The separate
[offline checkpoint](../../tests/mmap-window-20261026/README.md) passed 85
focused Python tests, 21 C transport assertions and two basic programs; none
is a measurement-window runtime pass.

## Rejected capture and settling evidence

Native boot ID: `9ac58480-830a-47f2-917b-adea05477e55`. The candidate had the
expected 68 modules, taint 4096, voluntary preemption, CPUs 0–63 and an empty
pending boot entry. The idle check passed. At
`2026-10-25T18:37:05.851740+00:00`, the host capture completed with all original
tasks plus TIDs `553976`, `553977`, and `553983`–`553995`.
Their captured cumulative CPU runtimes ranged from 9,241,870 to 96,555,911 ns;
timeslice counts ranged from 255 to 3,561. There is no paired activity interval
for these tasks. The host capture's `passed` field describes complete identity,
snapshot and placement capture; it does not admit these unreviewed roles.

The local empty-manifest check rejected 82 tasks before generating the
admission-copy request. The subsequent missing-request-file error launched
no SSH command. Neither `paired.py ready` nor the window observer ran.

The retained Native journal implies boot time approximately
`18:36:48.279275 UTC`, about **17.572465 seconds** before the capture. This is
guest journal realtime minus monotonic time, compared with the host clock;
it is not a synchronized boot-to-capture timing measurement. Source receipt
mtime and controller dispatch imply only **8.063903 seconds** after the idle
transport completed. There was no explicit settling receipt. The initial
review recorded the historical 60-second requirement; the separate
`settling-instruction-addendum.json` records the later 90-second requirement
without rewriting that review. The
first journal lookup used an unsupported hyphenated boot-ID spelling and
failed; the corrected read-only lookup and both outcomes are retained.

## Scope consumed and recovery

| Operation | Actual | Authorized maximum |
| --- | ---: | ---: |
| Boots | 2: Native, recovery | 3 |
| Full host captures | 3: initial, rejected Native, final recovery | 8 |
| Payload load/run/unload cycles | 0 | 4 |
| Fixed proofs / timed sessions | 0 / 0 | 2 / 2 |
| Window observers / samples | 0 / 0 | 2 / 194 |

Recovery identity passed at `2026-10-25T18:39:30.630828+00:00`:
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`b632d1e3-8c42-4f58-a7f5-053d063959fa`. Normal `modprobe` restored only the
missing original `nfnetlink` and `tls`; all original 73 modules were present,
taint was zero, `next_entry` was empty and the recovery default was unchanged.
CPU/boot/preemption policy matched, the fault scan and idle checks passed, and
no workload or uncertain command remained. No unrelated module was unloaded.
The final recovery host capture passed after 110.886491 seconds without guest
commands, recorded 68 QEMU tasks and confirmed the recovery snapshot remained
listed. It is recovery
evidence only and cannot qualify the failed Native admission.

## Retained evidence and next step

Source-host raw evidence is under
`bench/results/10.176.26.71/raw/bench/mmap-window-screen-20261026/`.
Guest preparation evidence remains under
`/root/kdlock-evidence/10.176.26.71/bench/mmap-window-screen-20261026/`.
The 78,392-byte guest archive SHA-256 is
`b3f31f10ed3ee2ec48d0b576c1fdde572103f18532d76627c90c6b05540476fe`.
Read-only archive inspection verified its 21 members, exact preparation receipt
and timed executable hash. The raw file inventory is bound by
`evidence-manifest.json`, SHA-256
`a61e16db07214b149a32b3acd553f46b01d410eb58493507cbe84ce4b019d451`.

Raw records include the exact command/request JSON, transport outcomes,
source manifest, prepared sources and executable, both host admissions,
`screen-rejection.json`, `settling-review.json`, recovery checks and scope
accounting. The [maintained runner guide](../../../../mmap_lock/README.md#small-matched-validation-screen)
provides the bounded procedure; it now explicitly records the existing settling
step. Historical rejected captures remain unchanged.

Accepted throughput count is zero; no latency, variability, bottleneck or
optimization gain was measured. The next useful step is to correct admission
preparation and establish reviewed role evidence before another explicitly
authorized small pair. Do not expand the workload or run the 126-session matrix
to work around this refusal.
