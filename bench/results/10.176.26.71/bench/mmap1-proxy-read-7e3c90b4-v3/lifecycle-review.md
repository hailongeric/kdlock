Offline audit passes for one compile-excluded, counter-enabled nominal-throughput point: **25,670.9 mmap/munmap pairs per nominal second**, from 256,709 completed pairs in the final ten samples. This is not quiet-performance, strict-peak or Native-gain qualification.

All 19 archived compiler records have status/result zero. The complete compiler record list is identical before and after the fixed application, no compiler overlaps its whole 16.060509-second lifetime, and the exact image registry and superseded history remain unchanged through both sample boundaries. The last compiler finished 16.768834 seconds before application start. Preparation took 2358.837496 seconds before that start; it is excluded from the rate denominator. Compiler and application durations are not added as disjoint phases.

Whole-application root counters are mmap **398,610 returned / 0 handbacks** and munmap **398,608 returned / 0 handbacks**, with positive JIT/submission counts and no missing-image or cancellation counts. These are whole-lifetime counters, separate from the ten-sample pair denominator. They do not establish consumption of a particular proxy-downgrade branch or a physical delegation-chain length.

All eight unchanged applications exited zero, completed and drained:

| Application | Body lifetime (s) | Application cap (s) | Return / drained |
| --- | ---: | ---: | --- |
| learning | 730.152564 | 800 | 0 / yes |
| continuation-01 | 8.038199 | 30 | 0 / yes |
| continuation-02 | 8.038292 | 30 | 0 / yes |
| continuation-03 | 8.038693 | 30 | 0 / yes |
| continuation-04 | 8.085143 | 30 | 0 / yes |
| continuation-05 | 8.039106 | 30 | 0 / yes |
| continuation-06 | 8.040049 | 30 | 0 / yes |
| fixed-point | 16.060509 | 30 | 0 / yes |

The conditional schedule used the existing supported 3,600-second shared learning cap, 16 of at most 64 continuation opportunities and a 600-second close cap. Candidate/runner 7e3c90b4 stayed unchanged. The complete current 1,099-file map equals the checked build map; provider and daemon retain their actual 3ceb7f00 build identity. The archived preflight is byte-identical to its source-host receipt and its complete reuse-map flags plus fixed-session binary hashes join exactly.

The original campaign remains `MEASURED_RETIREMENT_PENDING` with its generic initial passed/drained/accepted flags false, while recording one stable point. The separate normal finalizer and outer result passed, reaching exact source retirement `2/0/0/0`, ordinary unload and final idle. Finalization references the unchanged original SHA256 `5adc7090edbcfda0ad6c759c137ad92f7c7d7c65ba2006cbaf37190ab314b9c4`. Normal-kernel recovery separately verifies schema 2/runtime policy and Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot `3d32656f-6162-4a0a-9304-bf383d34298d`, idle; its request binds the same candidate and KD boot.

The generic application receipt has `scored=true` because tracing is off and it is not learning; the settled point/campaign/outer result explicitly remain `scored=false` with selected-service counters and sample callbacks enabled. Quiet/performance acceptance remains false.

Every stored application kernel log has zero matches under the current case-insensitive fault pattern and no `log_error`. The traceN path supplies no continuous collector completeness/overflow summary. Archive SHA256 `3f58be968edf403e45bfbc793a4b3f1a87915b9d2a074c22b0f2a6e3785c53e6` and 897218560 bytes match the collection receipt; selected audit files also match its manifest.

Offline archive/source inspection only. No VM/network action, build, unit check or further workload ran. Full receipt joins and qualifiers are in [validation.json](validation.json); [measurement-audit.json](measurement-audit.json) retains the independent fixed-point audit. The original `audit.json` is retained under the raw root's `controls/` directory.
