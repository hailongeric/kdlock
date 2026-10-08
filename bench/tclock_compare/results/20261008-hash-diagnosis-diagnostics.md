# Current-boot hash diagnostics

36 workers, three rounds per backend. These 72 diagnostic sessions are unscored.

Separate PMU invocations count the measured client and inherited workers, including waiting. Events are normalized by whole-run completed operations. No IPC is inferred across different runs.

| Kind | Event per completed operation | Native min / median / max | TCLock min / median / max | KD min / median / max |
| --- | --- | --- | --- | --- |
| spin | cycles | 53474.722 / 53876.914 / 54605.569 | 32427.630 / 32492.798 / 32511.514 | 44498.864 / 44663.326 / 44726.157 |
| spin | instructions | 3390.827 / 3410.355 / 3691.389 | 2313.625 / 2322.276 / 2326.485 | 3962.850 / 3981.290 / 3991.192 |
| spin | L1-dcache-load-misses | 21.180 / 21.327 / 21.533 | 36.828 / 36.927 / 37.018 | 36.030 / 36.538 / 36.545 |
| mutex | cycles | 33336.349 / 33541.257 / 33560.060 | 40707.515 / 40797.311 / 41077.744 | 55295.382 / 68528.564 / 72096.233 |
| mutex | instructions | 7882.134 / 7999.026 / 7999.466 | 4285.260 / 4298.049 / 4321.006 | 6558.081 / 6633.398 / 6657.536 |
| mutex | L1-dcache-load-misses | 15.935 / 16.000 / 16.087 | 46.702 / 47.003 / 47.288 | 46.136 / 47.480 / 49.577 |

Each accepted event has a positive count/runtime and at least 99.9% running time. All raw rows, per-round values and validation failures remain in the JSON.

## Flat worker cycle weights

Flat IP/TID/TIME/PERIOD records have zero lost samples. Fractions use only sc_worker samples. The generated image includes its wrapper; native body symbol boundaries differ. These are sampled event-period weights, not isolated function timings, exact wall-time shares or remote-memory latency.

| Kind / backend | Symbol | Worker weight %, min / median / max | Sampled period per completed operation, min / median / max |
| --- | --- | --- | --- |
| spin / native | `kernel:native_queued_spin_lock_slowpath` | 97.314 / 97.360 / 98.280 | 66459.868 / 67933.468 / 69526.641 |
| spin / native | `spin_cacheline:sc_body_0` | 1.293 / 1.370 / 1.506 | 882.295 / 956.575 / 1065.146 |
| spin / native | `unresolved` | 0.100 / 1.230 / 1.246 | 70.837 / 850.509 / 858.315 |
| spin / native | `spin_cacheline:sc_ioctl` | 0.011 / 0.011 / 0.016 | 7.668 / 7.858 / 11.242 |
| spin / native | `kernel:native_write_msr` | 0.003 / 0.008 / 0.017 | 1.918 / 5.627 / 11.789 |
| spin / native | `kernel:tick_sched_do_timer` | 0.005 / 0.006 / 0.011 | 3.837 / 3.933 / 7.498 |
| spin / native | `kernel:asm_sysvec_apic_timer_interrupt` | 0.000 / 0.005 / 0.008 | 0.000 / 3.836 / 5.623 |
| spin / tclock | `tclock_backend_km:__komb_spin_lock_longjmp` | 94.375 / 95.019 / 95.668 | 30882.648 / 30904.509 / 30928.927 |
| spin / tclock | `spin_cacheline:sc_body_0` | 2.139 / 2.157 / 2.238 | 691.545 / 705.827 / 727.990 |
| spin / tclock | `tclock_backend_km:komb_spin_lock` | 0.738 / 0.792 / 0.890 | 241.563 / 256.170 / 289.343 |
| spin / tclock | `unresolved` | 0.096 / 0.650 / 1.399 | 30.983 / 211.274 / 457.819 |
| spin / tclock | `tclock_backend_km:komb_spin_lock_slowpath` | 0.538 / 0.545 / 0.550 | 175.903 / 176.038 / 178.783 |
| spin / tclock | `tclock_backend_km:komb_spin_unlock` | 0.334 / 0.414 / 0.423 | 108.776 / 135.540 / 136.800 |
| spin / tclock | `tclock_backend_km:komb_context_switch` | 0.078 / 0.104 / 0.105 | 25.231 / 34.136 / 34.151 |
| spin / tclock | `tclock_backend_km:run_combiner` | 0.000 / 0.003 / 0.003 | 0.000 / 0.899 / 0.902 |
| spin / kdlock | `kdlock_km:__kd_spin_lock_longjmp` | 93.799 / 94.031 / 94.928 | 42397.189 / 42440.178 / 43098.002 |
| spin / kdlock | `generated:jit_image` | 1.807 / 2.007 / 2.075 | 817.602 / 896.302 / 951.060 |
| spin / kdlock | `kdlock_km:kd_spin_acquire_nondelegated_contended` | 0.888 / 0.941 / 1.672 | 396.820 / 425.970 / 766.239 |
| spin / kdlock | `kdlock_km:run_combiner` | 0.592 / 0.649 / 0.678 | 264.187 / 297.268 / 306.886 |
| spin / kdlock | `kdlock_km:kd_spin_lock_pinned_clobber_v1` | 0.404 / 0.458 / 0.474 | 180.280 / 207.237 / 217.268 |
| spin / kdlock | `spin_cacheline:sc_body_0` | 0.288 / 0.294 / 0.330 | 130.301 / 134.804 / 147.562 |
| spin / kdlock | `spin_cacheline:sc_ioctl` | 0.095 / 0.109 / 0.115 | 42.548 / 49.752 / 52.166 |
| mutex / native | `kernel:osq_lock` | 79.806 / 80.643 / 80.973 | 26297.465 / 26356.194 / 26502.931 |
| mutex / native | `kernel:__raw_callee_save___kvm_vcpu_is_preempted` | 12.901 / 13.188 / 13.396 | 4284.455 / 4292.563 / 4368.413 |
| mutex / native | `kernel:mutex_spin_on_owner` | 1.883 / 1.941 / 1.978 | 614.044 / 631.655 / 656.876 |
| mutex / native | `mutex_cacheline:mc_body_0` | 1.456 / 1.459 / 1.503 | 474.840 / 483.428 / 489.999 |
| mutex / native | `kernel:mutex_unlock` | 0.582 / 0.659 / 0.665 | 193.258 / 214.400 / 216.924 |
| mutex / native | `kernel:__mutex_lock.constprop.0` | 0.627 / 0.636 / 0.670 | 204.440 / 206.960 / 222.599 |
| mutex / native | `kernel:mutex_lock` | 0.580 / 0.600 / 0.602 | 192.748 / 195.412 / 196.410 |
| mutex / tclock | `tclock_mutex_backend_km:__komb_mutex_lock_slowpath` | 95.340 / 95.352 / 95.377 | 38630.470 / 38788.750 / 38945.179 |
| mutex / tclock | `mutex_cacheline:mc_body_0` | 1.590 / 1.726 / 1.754 | 646.646 / 699.158 / 716.126 |
| mutex / tclock | `tclock_mutex_backend_km:komb_mutex_lock` | 1.306 / 1.366 / 1.394 | 533.271 / 555.851 / 564.678 |
| mutex / tclock | `unresolved` | 0.636 / 0.691 / 0.778 | 257.851 / 282.312 / 316.451 |
| mutex / tclock | `tclock_mutex_backend_km:__komb_mutex_lock` | 0.325 / 0.373 / 0.374 | 132.568 / 151.347 / 151.604 |
| mutex / tclock | `tclock_mutex_backend_km:komb_mutex_unlock` | 0.229 / 0.238 / 0.243 | 93.362 / 96.358 / 98.784 |
| mutex / tclock | `tclock_mutex_backend_km:get_komb_mutex_node` | 0.077 / 0.110 / 0.119 | 31.339 / 45.084 / 48.318 |
| mutex / tclock | `tclock_mutex_backend_km:komb_context_switch` | 0.014 / 0.019 / 0.025 | 5.620 / 7.898 / 10.087 |
| mutex / tclock | `tclock_mutex_backend_km:run_combiner` | 0.003 / 0.003 / 0.006 | 1.090 / 1.121 / 2.254 |
| mutex / kdlock | `kernel:native_queued_spin_lock_slowpath` | 30.437 / 36.060 / 54.072 | 14493.337 / 18375.157 / 33989.835 |
| mutex / kdlock | `kdlock_km:__kd_mutex_lock_slowpath` | 30.703 / 31.111 / 34.245 | 14620.060 / 17450.651 / 19556.793 |
| mutex / kdlock | `kernel:osq_lock` | 7.113 / 19.057 / 27.390 | 4471.205 / 9711.139 / 13042.383 |
| mutex / kdlock | `kernel:__raw_callee_save___kvm_vcpu_is_preempted` | 1.161 / 3.256 / 4.427 | 729.554 / 1659.006 / 2107.854 |
| mutex / kdlock | `mutex_cacheline:mc_body_0` | 1.070 / 1.349 / 1.353 | 642.534 / 672.676 / 689.681 |
| mutex / kdlock | `kernel:mutex_spin_on_owner` | 0.586 / 1.150 / 1.293 | 368.112 / 547.408 / 658.810 |
| mutex / kdlock | `kdlock_km:kd_mutex_task_get` | 0.528 / 0.676 / 0.782 | 251.416 / 344.316 / 491.498 |
| mutex / kdlock | `generated:jit_image` | 0.508 / 0.520 / 0.649 | 242.115 / 264.958 / 407.908 |
| mutex / kdlock | `kdlock_km:kd_mutex_run_combiner` | 0.062 / 0.064 / 0.077 | 30.459 / 31.602 / 48.337 |

Validation: 72/72 accepted diagnostic sessions.
