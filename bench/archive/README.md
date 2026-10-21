# Historical analysis tools

[`full_compare_20261011.py`](full_compare_20261011.py) retains the exact offline
exporter from `d2a2304`, formerly in `bench/full_compare/` and then
`bench/archive/full_compare_20261011/`. It audits the historical 1,584- and
3,960-session matrices with 22 counts through 64 workers and the temporary
66-vCPU placement. It does not support the current 21-count matrix or shared
collector metadata. Do not use its defaults to define new runs.

For a matching extracted historical archive:

```sh
python3 bench/archive/full_compare_20261011.py \
  --input /path/to/historical-matrix --output /path/to/new-report --no-plots
```

[`requirements.txt`](requirements.txt) retains the historical plotting packages.
The exporter recomputes peaks, validates saved source/image hashes, worker
placement and drain, and preserves failures and interrupted attempts. It executes
no benchmark code. Its bytes and dependency list are unchanged by the folder
consolidation; frozen records retain their original paths.

The former launcher and narrowly scoped resume helper are retired; their exact
source remains in
[Git history](https://github.com/hailongeric/kdlock/tree/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/tools/vm).
Use [current runners](../README.md) for new measurements. Failed candidates and
numeric evidence belong under [results](../results/README.md), indexed by
physical machine and run, rather than in this tools directory.
