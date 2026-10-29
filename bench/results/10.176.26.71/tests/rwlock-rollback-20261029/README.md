# Rwlock reader-admission candidate: same-boot comparison

Candidate `1ad2ef7fb377407e96f7cf264784aef026e47835` integrates
`233f3f50d8abd9c5ffba390400024ca52922d6cb` on corrected role-exchange source
`1c86d6d1a15d96d75c09504f1041772247707804`. It remains isolated.
It withdraws a contended reader's speculative count before checking interrupt
context. IRQ/BH readers restore that count and wait for actual writer ownership,
retaining the bypass needed when interrupting a reader behind a queued writer.
The ordinary uncontended source path is unchanged.

Two basic unit programs and the affected rwlock driver passed (3/3), including
a writer winning the interrupt-reader rollback gap. The live IPI/IRQ/BH probe
passed and drained. The rwlock basic preset completed 1,600,000 operations,
30,234 returned JIT bodies and final idle. [Exact receipts](checks.json) retain
these separate scopes; none proves arbitrary recursive reads, upgrades or NMI
support.

Baseline `67361fee6440765e130385b2961246a41052b953` and candidate each ran
24 points on boot `677b7afa-5358-4ece-a650-5f4a4adecd55`, Linux
`7.0.0-38-kdlock1`. Arguments match except output paths: c01/c16, 1%/20%
writes, 1/8/20/32/36/60 workers on CPUs0..N-1, collector63, two seconds,
post256 and 1024/1024 mutex limits. Each point ran once; no real-world API
benchmark ran. The baseline predates all API work, so this comparison does
not isolate only the three-file rollback-first change.

Whole-run rates are Mops/s. [All original summaries and commands](comparison.json)
are retained, including the default three-round summary fields despite the
requested one valid observation per point.

| Workload | Writes | Workers | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01 | 1% | 1 | 1.918089 | 1.916831 | -0.07% |
| c01 | 1% | 8 | 9.794692 | 9.800210 | +0.06% |
| c01 | 1% | 20 | 9.019902 | 8.746092 | -3.04% |
| c01 | 1% | 32 | 8.916648 | 8.632219 | -3.19% |
| c01 | 1% | 36 | 7.576110 | 7.341060 | -3.10% |
| c01 | 1% | 60 | 7.527502 | 7.307894 | -2.92% |
| c01 | 20% | 1 | 1.918259 | 1.917729 | -0.03% |
| c01 | 20% | 8 | 5.619582 | 5.640341 | +0.37% |
| c01 | 20% | 20 | 5.454872 | 5.655903 | +3.69% |
| c01 | 20% | 32 | 5.476788 | 5.559473 | +1.51% |
| c01 | 20% | 36 | 4.511277 | 4.491045 | -0.45% |
| c01 | 20% | 60 | 3.560847 | 3.323738 | -6.66% |
| c16 | 1% | 1 | 1.918889 | 1.916494 | -0.12% |
| c16 | 1% | 8 | 10.954553 | 11.115353 | +1.47% |
| c16 | 1% | 20 | 9.687459 | 10.196507 | +5.25% |
| c16 | 1% | 32 | 10.093771 | 10.191705 | +0.97% |
| c16 | 1% | 36 | 8.895904 | 8.349752 | -6.14% |
| c16 | 1% | 60 | 8.710975 | 8.244970 | -5.35% |
| c16 | 20% | 1 | 1.918250 | 1.916727 | -0.08% |
| c16 | 20% | 8 | 4.347425 | 4.253496 | -2.16% |
| c16 | 20% | 20 | 4.237797 | 4.255432 | +0.42% |
| c16 | 20% | 32 | 4.204400 | 4.257002 | +1.25% |
| c16 | 20% | 36 | 3.259473 | 3.238011 | -0.66% |
| c16 | 20% | 60 | 2.464292 | 2.485055 | +0.84% |

The earlier c01/1% eight-worker loss is absent in this pair: 9.794692 versus
9.800210 Mops/s. Other points still lose approximately 3–7%; correctness and
this single pair do not close the no-regression gate. The c16/1% eight-worker
rate is 11.115353 Mops/s, but this does not establish the cause of the earlier
8.681424 observation. Additional matched investigation remains necessary.

The [offline archive receipt](archive-verification.json) verifies four
compressed hashes and all 4,434 inventory paths. Raw evidence is under
`bench/results/10.176.26.71/raw/tests/rwlock-rollback-20261029/`. Guest roots
are `tests/rwlock-rollback-20261029` and `bench/rwlock-api-matched-20261029`
below `/root/kdlock-evidence/10.176.26.71/`.
