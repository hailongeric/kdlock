# Historical static-call spin experiment

Authorized on 2026-09-15 as an independent recovery-guest source/build. The original
kernel and captured baseline remain preserved. This is the historical ancestor of
[spin-clobber](../spin_clobber/README.md) and
[mutex-clobber](../mutex_clobber/README.md); current providers require the spin clobber
interface and cannot be built for this static-only interface.

[guest-kernel.patch](guest-kernel.patch) changes the captured spin selector and
callbacks to static calls without changing the `(lock,rsp,rip)` callback or two-word
wrapper input. kdstatic1 keeps selector→callback; kdstatic2 adds a load-time combined
entry/static key. The original int3 selector remains. Updating call sites is serialized
outside the workload; it does not supply arbitrary hook-reader hot-unload safety.

The former provider's site cache allowed only its checked native fast path and did
not authorize JIT. Its Linux-lock-plus-private-queue behavior is historical; current
explicit KD spin uses one KD word. Do not apply old branch descriptions to current code.

[capture.py](capture.py) preserves source/config/build/live identity and the verified
parent bundle. Independent releases, installed boot files and recovery materials
must stay separate. Use a matching frozen checkout for reproduction. Old results,
failures and commands remain in the fixed
[experiment record](https://github.com/hailongeric/kdlock/blob/e533214/kernel_experiments/spin_static/README.md)
and [benchmark history](../../bench/results/380G10/bench/tclock_compare/HISTORY.md).
