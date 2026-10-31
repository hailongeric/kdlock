# Four-worker mutex c01 observation

The complete recovery/promoted comparison reports -18.50182484% whole-window
and -18.36024847% qualified peak throughput at this point. Every worker completed
and occupied almost all its measured interval. The aggregate worker CPU time
divided by four times the whole collection wall interval is approximately 99.49%
in both runs. The original collection wall interval includes the collector's
last roughly 10 milliseconds.

Five inspected mutex functions have identical unrelocated ELF body bytes,
section offsets and sizes in the two archived modules. This is static evidence
about those functions, not proof that all generated/runtime execution or all
physical placement was identical. The production source change restores only
reader entry; the mutex provider source is unchanged.

The retained counters show 6,092 returned-JIT bodies for 7,980,288 operations in
the promoted run, and 15,018 for 6,503,936 in recovery. These counters describe
execution differences; they do not establish which difference caused the loss.

Large additional off-CPU time is not supported by the worker CPU totals.
No timed park/unpark or scheduling-event trace was collected, so these totals
do not establish that parking never occurred or exclude associated cache costs.
One round provides no variance estimate. Keep the point in the failed gate;
there is no measurement rerun or new exception for it.
