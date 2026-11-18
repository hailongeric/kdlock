# Original main mutex nano on 380G10

All three mutex backends passed functional checks with 1, 8 and 36 workers on guest boot `895858e5-a434-4a8e-8dbe-6f677f28a80d`. The tables below cover 27 timed measurements from the same boot. Every worker advanced and the protected data matched the completed operation count. All benchmark modules and devices were released at the end of the run.

## Workload and results

Each worker wrote one shared, 64-byte-padded counter with 256 rounds of post-lock work. Each cell contains three 2-second timing runs. Workers used CPUs 0 through N−1, and the collector used CPU 39. CPUs 0–19 and 20–39 belong to different guest NUMA nodes. Host vCPUs had one-to-one pinning and 2.5 GHz policy limits before and after timing. Each backend used the original bulk ioctl. The backend order rotated across rounds. The table gives median whole-run throughput and the range over three rounds, in millions of operations per second. Event counts and operations are sums across those same three runs.

| Workers | Backend | Median Mops/s | Range | Operations | KD selected | KD completed | KD handback | TCLock delegated | TCLock batches | TCLock parks |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Native | 2.3828 | 2.3824–2.3835 | 14,373,376 | — | — | — | — | — | — |
| 1 | KD | 1.4342 | 1.4332–1.4348 | 8,649,728 | 0 | 0 | 0 | — | — | — |
| 1 | TCLock | 2.3919 | 2.3905–2.3921 | 14,424,576 | — | — | — | 0 | 0 | 0 |
| 8 | Native | 4.2252 | 4.2155–4.2593 | 25,537,792 | — | — | — | — | — | — |
| 8 | KD | 0.1243 | 0.1237–0.1243 | 749,568 | 705,243 | 705,243 | 44,129 | — | — | — |
| 8 | TCLock | 3.4718 | 3.4359–3.5470 | 20,976,384 | — | — | — | 18,385,972 | 879,437 | 15 |
| 36 | Native | 1.4158 | 1.3933–1.4663 | 8,600,832 | — | — | — | — | — | — |
| 36 | KD | 0.0859 | 0.0837–0.0859 | 525,824 | 494,307 | 494,307 | 31,091 | — | — | — |
| 36 | TCLock | 4.4543 | 4.3785–4.5096 | 26,828,544 | — | — | — | 26,764,280 | 27,403 | 273 |

KD's request recorder was enabled in every KD timing run. Its completed count requires an episode executed by a foreign task through the typed unlock. Selections and generated entries both equaled completions at every worker count. The handback column counts `KD_OBS_FORWARD` events returning execution to the origin, including paths that can forward before generated execution. These events cannot be interpreted as failed completions by subtracting them from proxy selections. Native has no proxy or handback. TCLock counts delegated bodies in returned batches and provides no per-instruction handback count.

With eight workers KD completed 94.1% of operations by proxy, and achieved 2.94% of Native throughput. With 36 workers it completed 94.0% by proxy and achieved 6.07% of Native throughput. The measurements include KD recorder overhead. Its separate cost was not measured. At 36 workers TCLock achieved 3.15 times Native throughput.

## Source and kernel

The original main worktree contains spin optimization `69c489f5` and benchmark runner `6a1ddf07`. A plain spin waiter already selected for local execution can observe that selection with an acquire load and skip another locked compare-exchange. The offered state still arbitrates between local and proxy execution with compare-exchange. The change is guarded by the plain-spin request flag. This mutex workload does not measure a spinlock speedup or a before/after mutex change. Ten focused source checks passed in the VM, including the new spin test.

The guest built and booted `7.0.0-38-kdorigmain1` with GCC 15.2.0, binutils 2.46 and pahole 1.31. Its live GNU build ID was `c66c442a321d6d1ae11842f7822cdf3a54cb3ad7`. The starting kernel16 configuration had SHA-256 `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`. The candidate configuration had SHA-256 `6c55eef73efe02b58e759f077e3a752178c0194ba39fcfb5cabe32a8e0b674bf`. Local tool availability affected Rust and its dependent driver, user-link-dependent sample options and optional OpenSSL signature capabilities. The candidate retained the original KD integration, NUMA, dynamic preemption, BTF, RSA and SHA-512 module signing. The exact config diff is in the archive. The original kernel16 symbol generator processed candidate DWARF using its retained libraries. Two exported signatures produced distinct CRCs that matched the original environment.

All four signed modules were built for this running kernel. Their external symbol versions and the TCLock provider dependency were checked before loading. Each functional run checked 256 operations per worker. After timing the guest had no pending systemd jobs, its only loaded module was `nls_iso8859_1`, its taint value was 4096 (out-of-tree module), and the postflight check found no kernel fault or lockup messages. The existing two-disk recovery snapshot was checked before the runs.

[Per-round rates and counts](runs.csv) · [Environment and source checks](environment.json) · [Kernel, module, functional and timing receipts](receipts.tar.gz)

The SHA-256 of the receipt archive is `c895134e027c34425e4f972441413a9d50e78f2dd0b121678a1ce57c91a2053e`.
