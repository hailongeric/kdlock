# KD shared-mapping diagnostic checkpoint

The separate KD mapping diagnostic **passed all six cases**, all nine negative
writer-witness mutations, normal unload and independent same-boot idle checks.
It ran on `7.0.0-38-kdmm1`, boot
`55696c5f-b3bb-46cd-8676-60877a4a79f1`, using the unchanged enabled-MM image with
Build ID `ac9ea2ec7f24be8b910547bdfdbfb071176677e6`.
[evidence.json](evidence.json) binds the result, source, binaries, host endpoints
and complete archived attempt. This is correctness evidence, not scored timing.

| Case | Result |
| --- | --- |
| Foreign-mm rejection and mapping scope | PASS |
| One-worker mapping cycle | PASS; 1,000 completed cycles |
| Sixteen-worker mapping cycle | PASS; 80,000 completed cycles, 16 joins, zero worker errors |
| One-worker VMA-only lifetime | PASS |
| Sixteen-worker VMA-only lifetime | PASS |
| Process exit and final VMA teardown | PASS |

Every case ended with zero live files, mm references and release errors. Final
normal unload succeeded; the independent endpoint found no project modules,
active workers or evidence writers. Taint was the recorded out-of-tree/unsigned
module value `12288`. Both host captures retained the configured 2.0 GHz policy,
recovery snapshot and required placement, with no endpoint differences. Source
verification passed; all 527 selected source inputs and 226 preserved regular
files were checked against their manifests.

The added diagnostics record at most four nonempty stack observations per
worker, using the same captured bytes as the unchanged acceptance predicate.
This attempt recorded five observations. The first four had valid kernel call
chains but failed the sleep bracket: all four returned `0` for the first wait
channel and changed scheduler counters; three changed from `D` to `R`, and one
from `R` to `D`. The fifth passed every original condition:

| Witness field | Observed value |
| --- | --- |
| Exact chain | `kd_mmap_down_write_killable+0xcb` → `kd_mmap_write_lock_killable+0x2b` → `__vm_munmap+0x88` |
| Task state before / after | `D` / `D` |
| Wait channel before / after | `kd_mmap_down_write_killable` / same |
| Scheduler counters before / after | `388121 335560 19` / same |

The nine negative checks still rejected changed lock identity, caller/waiter/
adapter offsets, running state, another wait channel, changed scheduler counters,
a missing chain and a missing witness. No predicate or exact ELF binding was
relaxed. Nineteen controller test methods and four actual-C classifier fixture
methods also passed with the diagnostic source bytes. A separate plotting test
failed because `matplotlib` was absent from the translation environment; that
combined check driver remains failed. An attempted isolated plotting setup then
timed out downloading binary wheels after 180 seconds. Both failures remain
recorded, and the unused temporary environment was removed.

A subsequent **one-method publication data check passed** and drained after
two separately recorded report-source changes. It checks receipt selection
without importing the plotting package. Its log binds both new source hashes
and explicitly records `graphical_rendering_tested=false`; it does not validate
chart rendering or change either earlier failed result. The original nineteen
controller and four actual-C method passes remain tied to their earlier bytes.

The [original mapping attempt](../linux70-kdmm1-20261027/README.md) remains
failed, with its later normal cleanup recorded separately. It did not retain
the bracket values, so its individual rejection reasons cannot be reconstructed.
This new sample demonstrates scheduling changes during rejected observations;
it does not establish their frequency or prove that every earlier rejection had
that cause. Diagnostic printing can also change observation timing.

The original 84 private-MM points remain frozen. KD fault/completed-fault checks
and all 42 shared-MM timing points are pending at this checkpoint. The planned
`catalog-linux70-mm-shared-20261028` generation requires fresh same-boot
correctness and both Native/KD preparations before measurement.
