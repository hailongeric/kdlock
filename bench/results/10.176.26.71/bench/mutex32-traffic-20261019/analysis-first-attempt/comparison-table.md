| Arm | Workload | Workers | Whole Mops/s median [min, max] | Execution | Status |
| --- | --- | ---: | ---: | --- | --- |
| baseline | c01 | 8 | — | MIXED | INCOMPLETE |
| baseline | c01 | 60 | — | MIXED | INCOMPLETE |
| baseline | c08 | 8 | — | MIXED | INCOMPLETE |
| baseline | c08 | 60 | — | MIXED | INCOMPLETE |
| baseline | pipebytes-query-n16 | 8 | 5.276 [4.854, 5.641] | RETURNED_JIT | COMPLETE |
| baseline | pipebytes-query-n16 | 60 | 3.666 [3.617, 3.696] | RETURNED_JIT | COMPLETE |
| baseline | seek-set-n16 | 8 | 4.261 [3.846, 4.341] | RETURNED_JIT | COMPLETE |
| baseline | seek-set-n16 | 60 | 3.871 [3.753, 3.908] | RETURNED_JIT | COMPLETE |
| fetchadd | c01 | 8 | — | MIXED | INCOMPLETE |
| fetchadd | c01 | 60 | — | MIXED | INCOMPLETE |
| fetchadd | c08 | 8 | — | MIXED | INCOMPLETE |
| fetchadd | c08 | 60 | — | MIXED | INCOMPLETE |
| fetchadd | pipebytes-query-n16 | 8 | 5.119 [5.117, 5.451] | RETURNED_JIT | COMPLETE |
| fetchadd | pipebytes-query-n16 | 60 | 3.763 [3.758, 3.764] | RETURNED_JIT | COMPLETE |
| fetchadd | seek-set-n16 | 8 | 4.247 [4.206, 4.251] | RETURNED_JIT | COMPLETE |
| fetchadd | seek-set-n16 | 60 | 3.845 [3.841, 3.867] | RETURNED_JIT | COMPLETE |
