# Original-body syscall comparison

Source `f7a84065e84474380faa37eeadfdf534abd72a68`; kernel recipe `8446f4ecb08816380a4c233197a8ce5e4d333aac`; boot `2e0ea0fa-ff34-4416-9175-b4b0ede3f63b`.

Retained 126/126 aggregate sessions; 126 valid, 0 invalid and 0 absent planned points.
Identity checks: passed. Campaign completion: True. Performance accepted: **false**.

Native and KD are paired at each case/worker count. Values use whole joined two-second intervals; one measured round per coordinate.
Raw deltas remain descriptive when identity or point validation fails. Every negative value and failed/missing coordinate is retained.
JIT returned-body proof belongs to the separate six-session functional run. Timed sessions do not observe JIT execution.
Setfd counts F_SETFD plus F_GETFD per operation; each pipe operation is one syscall. No TCLock or extracted-body result is included.
Host endpoint assessment, outstanding nano losses and final mmap1 acceptance remain separate.

| Case | Workers | Native ops/s | KD ops/s | KD delta | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| setfd | 1 | 2,026,713.266 | 1,981,458.172 | -2.233% | loss |
| setfd | 2 | 3,109,685.014 | 3,085,477.243 | -0.778% | loss |
| setfd | 3 | 4,245,648.236 | 4,111,018.418 | -3.171% | loss |
| setfd | 4 | 3,206,991.243 | 3,524,212.696 | 9.892% | gain |
| setfd | 5 | 3,166,390.960 | 3,368,155.023 | 6.372% | gain |
| setfd | 6 | 3,233,991.706 | 3,619,674.298 | 11.926% | gain |
| setfd | 7 | 3,305,925.592 | 3,422,874.491 | 3.538% | gain |
| setfd | 8 | 3,595,273.975 | 3,814,875.059 | 6.108% | gain |
| setfd | 12 | 3,543,413.432 | 4,987,967.042 | 40.767% | gain |
| setfd | 16 | 3,285,627.807 | 5,162,884.214 | 57.135% | gain |
| setfd | 20 | 3,388,391.253 | 5,185,314.935 | 53.032% | gain |
| setfd | 24 | 3,458,977.038 | 5,207,962.268 | 50.564% | gain |
| setfd | 28 | 3,388,304.525 | 5,176,421.135 | 52.773% | gain |
| setfd | 32 | 3,475,976.522 | 5,193,479.527 | 49.411% | gain |
| setfd | 36 | 2,684,280.795 | 4,833,446.865 | 80.065% | gain |
| setfd | 40 | 2,101,298.389 | 4,839,660.394 | 130.318% | gain |
| setfd | 44 | 2,095,959.608 | 4,876,490.884 | 132.661% | gain |
| setfd | 48 | 1,971,277.759 | 4,909,659.120 | 149.060% | gain |
| setfd | 52 | 1,938,450.206 | 4,912,434.048 | 153.421% | gain |
| setfd | 56 | 1,936,121.849 | 4,942,230.997 | 155.264% | gain |
| setfd | 60 | 1,939,708.088 | 4,915,669.069 | 153.423% | gain |
| pipebytes | 1 | 3,340,028.997 | 3,301,281.488 | -1.160% | loss |
| pipebytes | 2 | 5,249,593.354 | 5,382,216.927 | 2.526% | gain |
| pipebytes | 3 | 7,771,094.151 | 8,029,432.105 | 3.324% | gain |
| pipebytes | 4 | 3,186,502.028 | 4,574,631.791 | 43.563% | gain |
| pipebytes | 5 | 3,441,686.762 | 1,882,850.343 | -45.293% | loss |
| pipebytes | 6 | 3,410,898.032 | 2,142,080.922 | -37.199% | loss |
| pipebytes | 7 | 3,350,530.175 | 2,242,390.035 | -33.074% | loss |
| pipebytes | 8 | 3,288,786.604 | 2,202,286.731 | -33.036% | loss |
| pipebytes | 12 | 3,467,610.800 | 2,305,372.656 | -33.517% | loss |
| pipebytes | 16 | 3,446,648.866 | 2,290,687.889 | -33.539% | loss |
| pipebytes | 20 | 3,292,181.990 | 2,302,196.812 | -30.071% | loss |
| pipebytes | 24 | 3,390,087.813 | 2,275,123.701 | -32.889% | loss |
| pipebytes | 28 | 3,333,034.563 | 2,292,203.700 | -31.228% | loss |
| pipebytes | 32 | 3,409,166.088 | 2,283,922.020 | -33.006% | loss |
| pipebytes | 36 | 2,687,346.680 | 2,224,867.119 | -17.210% | loss |
| pipebytes | 40 | 2,269,010.359 | 2,236,090.364 | -1.451% | loss |
| pipebytes | 44 | 2,288,654.893 | 2,265,389.150 | -1.017% | loss |
| pipebytes | 48 | 2,196,291.086 | 2,248,133.031 | 2.360% | gain |
| pipebytes | 52 | 2,187,744.040 | 2,247,979.144 | 2.753% | gain |
| pipebytes | 56 | 2,166,449.872 | 2,233,456.030 | 3.093% | gain |
| pipebytes | 60 | 2,142,987.514 | 2,222,155.278 | 3.694% | gain |
| pipecap | 1 | 3,789,559.250 | 3,722,039.997 | -1.782% | loss |
| pipecap | 2 | 5,904,268.967 | 4,594,353.874 | -22.186% | loss |
| pipecap | 3 | 8,063,184.098 | 7,141,429.102 | -11.432% | loss |
| pipecap | 4 | 3,474,191.207 | 5,143,436.967 | 48.047% | gain |
| pipecap | 5 | 3,255,486.086 | 3,150,280.635 | -3.232% | loss |
| pipecap | 6 | 3,607,279.268 | 2,721,691.338 | -24.550% | loss |
| pipecap | 7 | 3,693,667.862 | 3,293,287.616 | -10.840% | loss |
| pipecap | 8 | 3,701,176.670 | 3,734,315.246 | 0.895% | gain |
| pipecap | 12 | 3,484,895.343 | 4,172,656.594 | 19.735% | gain |
| pipecap | 16 | 3,238,904.017 | 4,277,987.483 | 32.081% | gain |
| pipecap | 20 | 3,575,341.429 | 4,198,061.364 | 17.417% | gain |
| pipecap | 24 | 3,412,258.693 | 4,219,126.711 | 23.646% | gain |
| pipecap | 28 | 3,549,303.185 | 4,207,939.124 | 18.557% | gain |
| pipecap | 32 | 3,594,657.361 | 4,147,681.136 | 15.385% | gain |
| pipecap | 36 | 2,672,549.480 | 3,957,513.713 | 48.080% | gain |
| pipecap | 40 | 2,400,775.706 | 3,909,398.217 | 62.839% | gain |
| pipecap | 44 | 2,342,697.424 | 4,039,675.557 | 72.437% | gain |
| pipecap | 48 | 2,227,737.242 | 4,091,168.397 | 83.647% | gain |
| pipecap | 52 | 2,173,961.134 | 4,066,908.679 | 87.074% | gain |
| pipecap | 56 | 2,126,740.306 | 3,929,844.100 | 84.783% | gain |
| pipecap | 60 | 2,057,984.737 | 4,030,801.710 | 95.862% | gain |

All issues and exact functional counters are retained in `summary.json`; per-point failures and raw rates are in `points.csv` and `pairs.csv`.
