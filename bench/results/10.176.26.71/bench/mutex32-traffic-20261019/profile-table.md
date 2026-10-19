| Arm | Workers | Profile returned JIT | Plain returned JIT | Ref acquire % | Ref put % | Hint/retry helpers % | Samples | Complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 8 | 0.81% | 74.63% | 0.43 | 0.09 | 0.23 | 3225 | True |
| baseline | 60 | 84.89% | 85.87% | 2.25 | 1.51 | 0.55 | 24152 | True |
| fetchadd | 8 | 86.40% | 84.54% | 6.60 | 4.69 | 1.24 | 3220 | True |
| fetchadd | 60 | 83.43% | 86.72% | 2.05 | 1.65 | 0.52 | 24171 | True |
| old256 | 8 | 91.62% | 96.83% | 0.00 | 0.00 | 0.00 | 3223 | True |
| old256 | 60 | 94.51% | 94.98% | 0.00 | 0.00 | 0.00 | 24178 | True |
| hint | 8 | 83.16% | 83.98% | 6.19 | 4.02 | 4.94 | 3223 | True |
| hint | 60 | 85.18% | 86.73% | 1.80 | 1.49 | 1.29 | 24186 | True |
| inline | 8 | 79.59% | 87.88% | 6.29 | 4.46 | 2.70 | 3232 | True |
| inline | 60 | 85.30% | 87.33% | 2.18 | 1.44 | 0.45 | 24180 | True |

Symbol percentages use the sc_worker period denominator; these profiles are unscored.
