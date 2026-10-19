| Arm | Workers | Profile returned JIT | Plain returned JIT | Ref acquire % | Ref put % | Hint/retry helpers % | Samples | Complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 8 | 0.81% | 74.63% | 0.43 | 0.09 | 0.23 | 3225 | True |
| baseline | 60 | 84.89% | 85.87% | 2.25 | 1.51 | 0.55 | 24152 | True |
| fetchadd | 8 | 86.40% | 84.54% | 6.60 | 4.69 | 1.24 | 3220 | True |
| fetchadd | 60 | 83.43% | 86.72% | 2.05 | 1.65 | 0.52 | 24171 | True |

Symbol percentages use the sc_worker period denominator; these profiles are unscored.
