# Instrumentation sensitivity

These separate one-round observations share frozen source inputs. They show substantial sensitivity to profiling; they do not estimate isolated overhead or repeat variability. Stat and record throughput remain diagnostic and score ineligible.

| Body | Workers | Backend | Unprofiled Mops/s | Stat / unprofiled | Record / unprofiled |
|:---|---:|:---|---:|---:|---:|
| mutex | 16 | native | 7.185 | 0.527 | 0.891 |
| mutex | 16 | kdlock | 6.529 | 0.546 | 0.394 |
| mutex | 36 | native | 7.111 | 0.309 | 0.890 |
| mutex | 36 | kdlock | 4.746 | 0.941 | 0.947 |
| mutex | 60 | native | 5.621 | 0.216 | 0.707 |
| mutex | 60 | kdlock | 4.941 | 0.953 | 0.963 |
| mutex-locality | 16 | native | 5.985 | 0.241 | 0.432 |
| mutex-locality | 16 | kdlock | 5.196 | 0.456 | 0.391 |
| mutex-locality | 36 | native | 3.989 | 0.316 | 0.701 |
| mutex-locality | 36 | kdlock | 3.954 | 0.927 | 0.918 |
| mutex-locality | 60 | native | 2.616 | 0.396 | 0.770 |
| mutex-locality | 60 | kdlock | 4.174 | 0.907 | 0.919 |

[Full-precision ratios](instrumentation-effects.csv). The archived source manifests match across all three modes within each body. ELF executable section equality is recorded separately in `bench/results/10.176.26.71/raw/bench/mutex-profile-20261026/analysis/instrumentation-effects.json`; different archive/build paths and debug sections remain distinct binary identities. The CSV also preserves aggregate worker CPU/op, Jain completed-work fairness and maximum/minimum worker completion ratios separately for each mode.

Interpret counter and sample attribution within their instrumented contention regime. In particular, a lower aggregate polling fraction or a favorable instrumented throughput ratio does not establish a production optimization. Fresh unprofiled rates remain the comparison control.
