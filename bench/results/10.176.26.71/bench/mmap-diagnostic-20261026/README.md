# One QEMU diagnostic, October 26

The single authorized attempt stopped during initial observation at
`task sampling exceeded 500 ms bound`. It is **incomplete and unaccepted**.
No metadata bundle, snapshot query, guest control or hash probe ran. No benchmark,
module operation, kernel change, reboot, retry or signal was issued by this
diagnostic. Host and guest completion are confirmed; the controller returned 1.

The reviewed implementation from `0771ae6` was unchanged at source HEAD
`ea9241d98629e4f2ac9bf4f327557fc21ab33b7c`. Its 43 earlier mocked tests remain
offline preparation evidence, not a successful live observation. The
[diagnostic guide](../../../../mmap_lock/DIAGNOSTIC.md) retains the bounded phases
and stop conditions. No second invocation is authorized by this receipt.

## Retained observations

Sample 2 triggered the stop: its start-to-start gap was **504.396027 ms** against
the unchanged 500 ms maximum. Samples 3–11 are the bounded stop tail, not
additional accepted phases. The maximum gap, **507.250589 ms**, occurred in that
tail. All 11 complete scans contained 68 tasks, with no observed new or removed
identity. Discrete scans cannot exclude shorter task lifetimes between them.

| Sample | Stage | Start gap (ms) | Unobserved gap (ms) | Scan duration (ms) |
| ---: | --- | ---: | ---: | ---: |
| 1 | Initial inventory | — | — | 3.725377 |
| 2 | Triggers stop | 504.396027 | 500.669657 | 5.008769 |
| 3 | Stop tail | 504.623610 | 499.614064 | 4.937199 |
| 4 | Stop tail | 504.446326 | 499.508609 | 5.916847 |
| 5 | Stop tail | 505.560782 | 499.643227 | 5.958948 |
| 6 | Stop tail | 505.480106 | 499.520682 | 6.992630 |
| 7 | Stop tail | 506.584053 | 499.590394 | 6.690197 |
| 8 | Stop tail | 506.357296 | 499.666584 | 6.985002 |
| 9 | Stop tail | 506.589833 | 499.603646 | 6.891424 |
| 10 | Stop tail | 506.401646 | 499.509632 | 6.998345 |
| 11 | Stop tail | 507.250589 | 500.251115 | 4.816831 |

The bound QEMU identity was PID 257489, start ticks 42969155, host boot
`2b39cf56-2146-4c87-9fa5-28c66dcee12c`, command SHA-256
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`.
Extra worker TID **553442**, start ticks **133435721**, was already present in
the initial inventory, pinned to CPU 63 and observed sleeping in
`futex_wait_queue`. It is distinct from TID 552994 in the earlier
[68-task admission stop](../mmap-plain-v1-20261025/README.md). Its creation cause
and timing impact remain unknown. An idle name/state does not admit that worker
under the original exact 67-task benchmark rule.

Host observation elapsed 5,461,537,762 ns including the stop tail, consuming
122,796,704 ns observer CPU (about 2.25% of one core over that interval).
The source controller elapsed 5,874,688,865 ns and consumed 81,072,129 ns CPU
(about 1.38% of one core). These are process costs over this failed short
observation, not workload overhead measurements. Completed stimulus phases,
guest launches, retries and signals were all zero.

The implementation schedules the next scan 500 ms after the previous start and
checks readiness through a 10 ms polling loop. This leaves no explicit margin
between the nominal period and maximum allowed start gap. That source property
required offline design review; the saved run does not isolate polling,
scheduling or other contributors. The user subsequently clarified that 500 ms
is an approximate target and authorized one corrected attempt after offline
validation and independent review. The [current guide](../../../../mmap_lock/DIAGNOSTIC.md)
tracks that separate correction. This original run remains incomplete; the
clarification does not alter the 67-task gate or reclassify rejected timings.

## Recovery and evidence

Saved post-run health at **2026-10-26 00:57:00 Asia/Shanghai**
(`2026-10-25T16:57:00.186787+00:00`) passed. Recovery remained
`6.1.159-kdclobber2`, boot `d32e2e18-c340-4a98-8105-335bccec0b5d`, with the
original 73 modules, taint **12288**, CPUs 0–63, voluntary preemption and empty
`next_entry`. Release, boot, command line, modules, taint, topology, preemption,
GRUB state, recovery source and dmesg matched the pre-run record. Process/open-file
checks found no project work. This is saved health evidence, not a fresh check
by a later documentation reader.

Raw evidence is retained on 380G10 at
`bench/results/10.176.26.71/raw/bench/mmap-diagnostic-20261026/`.
Its manifest binds **18 files / 627,262 bytes**, excluding itself, SHA-256
`81075ed9c3245d7f8fa98845cc49e7554ba7460801507e00439252b3ad3ede12`.
`run-1/host.stdout` retains every observation and event; `review.json` separates
the triggering sample from the tail; the transport records preserve health
commands, input hashes and confirmed completion. `commands.txt` records the
single invocation, reproduced here as history, not permission to rerun:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 bench/mmap_lock/diagnostic_controller.py --execute \
  --output bench/results/10.176.26.71/raw/bench/mmap-diagnostic-20261026/run-1 \
  > bench/results/10.176.26.71/raw/bench/mmap-diagnostic-20261026/console.json \
  2> bench/results/10.176.26.71/raw/bench/mmap-diagnostic-20261026/console.stderr
```

| Bound artifact | SHA-256 |
| --- | --- |
| Controller source | `aae678d9ec1095c95389f655e83feed1ac93ac8935801e03f55bf37bf6e3720a` |
| Observer source | `b63e6f85a547a961300f99b8792be22f3611a66445e290da2eb5c8936ff8cd9c` |
| Host parser source | `8a348f7a0977b2d01d99480deca026c3365477e740c6efb60f49ec274f2872a3` |
| kdmm31 profile | `79aba1adc40eca61f9d8c9aef34908598bb84e947a48920877bd906b9c0ee940` |
| Streamed payload | `18e7a37b2b52a86523b172abfa47db97bab4f5ac56e65e7e521e6bf545e56d51` |
| Raw host event stream | `ace1a3fa4be238e5baecd3d1a5a65835dbe136802012354bfd876465d2a8b78c` |
| Controller receipt | `cb55987c1fbead1fb9ad2435d9ec4d6a5a35708f045bf3bd3c54e70391f6d44e` |

The audited lock remains `e6fc371`; no lock defect or optimization was fixed by
this diagnostic. Qualified current mmap throughput and latency results remain
zero. The already-completed provider load diagnostic is a separate event and
is not repeated here.
