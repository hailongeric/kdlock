# Qualified 16-worker Native/KD mmap validation pair

The October 26, 2026 (Asia/Shanghai) screen completed **one qualified,
drained pair** under `mmap-window-v2` with explicit `qemu-workers-v1`
admission. Native achieved **108,245.61 completed mmap/munmap cycles/s**;
KD achieved **35,406.14**, or **0.3271× Native (67.3% lower)**. This is an
unscored harness-validation pair, not the repeated 126-session baseline.
It supplies no variability estimate, causal bottleneck diagnosis or optimization
gain. Earlier rejected runs remain rejected.

| Arm | Completed cycles | Actual wall time (ns) | Cycles/s | Fixed-proof checks / cycles |
| --- | ---: | ---: | ---: | ---: |
| Native | 216,992 | 2,004,626,359 | 108,245.60848 | 266 / 80,000 |
| KD | 71,008 | 2,005,528,120 | 35,406.13532 | 497 / 80,000 |

Both arms passed workload validation, window qualification, endpoint replay and
normal drain. Each fixed proof used 16 workers × 5,000 iterations. Final payload
health was `files=0 mm_refs=0 destroyed=1 release_errors=0`; normal unload
completed. These fixed proofs do not rerun the earlier 137 Native / 161 KD API
assertions or the separate 352-assertion standalone probe.

## Matched inputs and measurement boundary

Source HEAD was `ee076d246003ab662d9af09238cf5ea165563d6c`; admission tooling
was introduced in `b196e73`. Lock and mmap integration bytes remain the audited
`e6fc371` implementation. No lock, MM body, kernel, payload or client changed
for this pair, and no kernel was built or installed.

Both arms used the same `6.1.159-kdmm31` image, Build ID
`ef5179e8def44f0255adcd62585f62f118fee30f`, with only `kd_mmap=off/on`
selecting the backend. Image SHA-256:
`17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040`.
The reused `client-build-2/result.json` receipt SHA-256 is
`24ad837c95906a6a304ba8eae7a87eca7eb570a88269d811fee593f948f0adfb`;
the timed executable SHA-256 is
`5962210671ac238ae4df8dcca442b3cb7407efb2b5b2edb42ae637ac4902083f`.
[kdmm31.json](../../../../mmap_lock/kdmm31.json) binds the remaining kernel,
configuration, module and topology identities.

Sixteen pthreads shared one mm, on CPUs 0–15, with guest collector CPU 63.
Each iteration mapped and unmapped one untouched 4 KiB `PROT_READ`, `MAP_SHARED`
device range. The two-second target, 100 ms scheduled start delay, accounting
and syscall shell were identical. This measures actual shared-mm writer
throughput with payload accounting overhead; it does not measure isolated lock
latency, concurrent readers, page faults or delegation. TCLock has no equivalent
actual mmap interface here.

Each arm recorded the required single 90-second interval after payload setup:
90,001,077,231 ns Native and 90,001,097,957 ns KD. Prepared workers preceded
the host guard; the host measurement endpoint preceded receipt export. The
observer made ten scans per arm. Observer CPU / elapsed time was
210,381,878 / 4,240,884,768 ns Native and
188,173,497 / 4,226,525,034 ns KD. No auxiliary workers were observed in those
sampled windows. Admission had 83 Native and 71 KD QEMU tasks; the reviewed
policy permits verified auxiliary lifetimes/activity. Empty sampled worker
sets do not prove zero interference or qualify historical refused runs.

## Scope, evidence and recovery

Actual consumption was **3 boots, 8 full host captures, 4 payload cycles,
2 fixed proofs, 2 timed sessions, 2 observers and 20 scans**. There was no
retry, warmup, latency collection, provider diagnostic or optimization.

Raw commands, source manifest, controllers, streams, role evidence, receipts
and recovery checks are retained on 380G10 at
`bench/results/10.176.26.71/raw/bench/mmap-worker-screen-20261026/` and in the
guest at `/root/kdlock-evidence/10.176.26.71/bench/mmap-worker-screen-20261026/`.
The source inventory contains 143 files; its `evidence-manifest.json` SHA-256 is
`2ea2e509f0ef31f74cefbef6107c59a89129d8ce4f44a03e5dbb99c255b58cfc`.
The guest archive is 1,047,129 bytes, with 96 regular files containing
8,294,893 bytes; SHA-256:
`3b71dc3b2ead00f41896af19f1fabf948c83b0def838543c3e5423325a0cfa18`.
Read-only archive inspection checked member types and both result/client
hashes against `pair-details.stdout`; inventory hashes matched. Independent
saved-evidence review found no material mismatch.

The exact launch requests are `native-controller-command.json` and
`kd-controller-command.json`; the maintained
[screen procedure](../../../../mmap_lock/README.md#small-matched-validation-screen)
requires fresh output paths for any separately authorized repetition. To replay
the retained pair in the VM:

```sh
cd /root/host_fs/kdlock
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
  /root/kdlock-translation-venv-20261019/bin/python3 bench/mmap_lock/report.py \
  --screen \
  /root/kdlock-evidence/10.176.26.71/bench/mmap-worker-screen-20261026/native-case/result.json \
  /root/kdlock-evidence/10.176.26.71/bench/mmap-worker-screen-20261026/kd-case/result.json
```

Recovery health passed at `2026-10-25T19:22:24.971559+00:00`:
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`d3fbbe90-87d3-4374-a9a5-98996c1a3f28`, all original **73 modules**, **taint 0**,
idle and empty `next_entry`. Normal `modprobe` restored only missing original
`nfnetlink` and `tls`; the recovery default stayed unchanged. The final host
capture at `19:25:26.375012 UTC` passed placement checks and confirmed snapshot
`before-mutex-kdonly-20261017T140354Z` remained listed. These are the recorded
end-of-cycle checks, not a claim about future VM state.

The next performance step is the separately authorized 21-count, three-pair
throughput baseline, after recalculating captures, runtime and storage for the
current window/worker policies. The historical 259-capture estimate excludes
the additional window endpoints and must not be reused for that execution.
