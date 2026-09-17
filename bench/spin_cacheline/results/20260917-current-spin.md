# 2026-09-17：当前 spin 实现的完整性能扫描

**30 个配置、120/120 个会话通过，未测得一致的整体提速。** 8–20 线程的
kdlock 最佳吞吐为 **0.880–0.940 Mops/s**，相当于原生中位数的
**27.3%–47.3%**。与最近一次共享 request 的四点结果相比，本轮对应点变化为
**+3.8%、−1.8%、−1.3%、+0.4%**；两个样本不能证明小幅变化具有统计显著性。

测量时使用 `6fc6e73` 加嵌套锁记录直写、虚拟 waiter 邮箱预检查的工作区版本；
本结果页与对应实现、定向测试一并提交，精确运行输入由归档哈希标识。
它包含物理 waiter 的 shadow 等待栈；[上次共享 request 测量](20260917-tclock-shared.md)
冻结在恢复该等待栈之前。这不是只切换两项嵌套优化的消融实验。
本 benchmark 每次仅持有一把锁，不触发嵌套 child 或虚拟 waiter，因而不能
用它判断这两项优化在嵌套工作负载中的收益。相关功能证据见
[定向验证](../../../tests/README.md#spin-nested-state-validation)。

负载、CPU 放置和测量参数与此前完整扫描一致：1/2/4/8/16 条 cacheline，
1/4/8/12/16/20 线程，每线程 100,000 次，每配置两对原生/kdlock 会话，
按原生→kdlock、kdlock→原生交替。CPU 0–19 全部位于 NUMA 节点 0；未测
24 线程或跨 NUMA。每次正文后保留四组锁外乘加，`bench_quiet=1 jit_timing=0`。

表中单位为所有线程合计的百万次完整操作/秒（Mops/s），包含锁外计算。
口径沿用 **kdlock 最高有效吞吐 / 原生有效吞吐中位数**；JIT 占比取同一个
最佳会话。原始 CSV 另保留全部样本、中位数和配对比值。

| cacheline | 线程 | 原生中位 Mops/s | kdlock 最佳 Mops/s | best/median | 最佳会话 JIT 占比/状态 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 10.867 | 9.542 | 0.8781 | 0.00% / NO_JIT |
| 1 | 4 | 3.184 | 0.702 | 0.2206 | 53.91% / JIT |
| 1 | 8 | 3.307 | 0.903 | 0.2729 | 98.53% / JIT |
| 1 | 12 | 3.127 | 0.909 | 0.2907 | 99.53% / JIT |
| 1 | 16 | 3.270 | 0.900 | 0.2752 | 99.79% / JIT |
| 1 | 20 | 3.187 | 0.888 | 0.2788 | 99.77% / JIT |
| 2 | 1 | 11.270 | 8.368 | 0.7425 | 0.00% / NO_JIT |
| 2 | 4 | 2.588 | 0.634 | 0.2451 | 57.02% / JIT |
| 2 | 8 | 2.735 | 0.897 | 0.3280 | 99.00% / JIT |
| 2 | 12 | 2.724 | 0.911 | 0.3346 | 99.69% / JIT |
| 2 | 16 | 2.880 | 0.898 | 0.3116 | 99.73% / JIT |
| 2 | 20 | 2.782 | 0.898 | 0.3226 | 99.86% / JIT |
| 4 | 1 | 12.273 | 9.212 | 0.7506 | 0.00% / NO_JIT |
| 4 | 4 | 2.461 | 0.828 | 0.3366 | 55.53% / JIT |
| 4 | 8 | 2.624 | 0.940 | 0.3582 | 99.07% / JIT |
| 4 | 12 | 2.543 | 0.914 | 0.3595 | 99.53% / JIT |
| 4 | 16 | 2.650 | 0.896 | 0.3380 | 99.83% / JIT |
| 4 | 20 | 2.608 | 0.905 | 0.3470 | 99.81% / JIT |
| 8 | 1 | 11.596 | 8.424 | 0.7265 | 0.00% / NO_JIT |
| 8 | 4 | 2.305 | 0.649 | 0.2817 | 56.08% / JIT |
| 8 | 8 | 2.292 | 0.894 | 0.3899 | 99.29% / JIT |
| 8 | 12 | 2.288 | 0.886 | 0.3874 | 99.73% / JIT |
| 8 | 16 | 2.414 | 0.895 | 0.3708 | 99.80% / JIT |
| 8 | 20 | 2.303 | 0.902 | 0.3917 | 99.86% / JIT |
| 16 | 1 | 9.998 | 8.981 | 0.8982 | 0.00% / NO_JIT |
| 16 | 4 | 2.099 | 0.619 | 0.2949 | 57.85% / JIT |
| 16 | 8 | 1.874 | 0.880 | 0.4693 | 99.31% / JIT |
| 16 | 12 | 1.930 | 0.913 | 0.4729 | 99.68% / JIT |
| 16 | 16 | 1.918 | 0.894 | 0.4662 | 99.82% / JIT |
| 16 | 20 | 1.985 | 0.909 | 0.4578 | 99.84% / JIT |

与[上次共享 request 四点复测](20260917-tclock-shared.md)的对应比较：

| cacheline | 线程 | 上次 kdlock 最佳 Mops/s | 本次 kdlock 最佳 Mops/s | 变化 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 0.677 | 0.702 | +3.8% |
| 1 | 20 | 0.905 | 0.888 | -1.8% |
| 16 | 4 | 0.627 | 0.619 | -1.3% |
| 16 | 20 | 0.905 | 0.909 | +0.4% |

上述比较的工作负载源码哈希相同，内核仍为 `6.1.159-kdstatic2`，Build ID
为 `460d77502af4709a0cca794b322cedc20c2cc478`，voluntary、nokaslr。
没有改动内核、watchdog、锁算法或 benchmark 观测补丁。虚拟机的宿主物理核
独占和频率未控制，未作函数级采样，不能从这些吞吐差异归因到某个字段或分支。

共完成 **122,000,000 次操作**：60 个原生会话、10 个单线程 NO_JIT 会话、
50 个多线程实际 JIT 会话。测量期 JIT 正文合计 **58,054,349 次**；最长测量
批次 **2.281 秒**。逐会话验证计数器、线程 CPU、生成/发布和退休，最终检查
确认源码、四个二进制、boot ID 未变，模块/测试进程排空，无内核 fault。
`watchdog_thresh=10`、`soft_watchdog=1` 保持原值。

宿主离线复核了 190 个冻结输入、4 个二进制、150 个 JIT 映像哈希、全部会话
计数/CPU/吞吐和配对比值；其中 127 个非生成输入与运行结束时宿主源码一致。
本轮只重跑 benchmark，功能验证引用上述独立记录，不标记为再次执行。

```sh
# 在恢复 guest 执行；已从宿主 monitor 确认实际存在的快照。
cd /root/host_fs/kdlock
LC_ALL=C KDIR=/root/linux-6.1.159-kdstatic2 KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout --kill-after=10s 3900s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 2 4 8 16 --threads 1 4 8 12 16 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /root/kdlock-evidence/spin-current-20260917
```

- [汇总 CSV](/tmp/kdlock-spin-current-20260917.NDIlms/evidence/spin-current-20260917/summary.csv)、[逐会话 CSV](/tmp/kdlock-spin-current-20260917.NDIlms/evidence/spin-current-20260917/raw.csv)、[逐对 CSV](/tmp/kdlock-spin-current-20260917.NDIlms/evidence/spin-current-20260917/pairs.csv)。
- [独立复算](/tmp/kdlock-spin-current-20260917.NDIlms/audit.json)、[最终身份与排空](/tmp/kdlock-spin-current-20260917.NDIlms/evidence/spin-current-20260917/postflight.json)。
- [命令、工作区差异和完整运行日志](/tmp/kdlock-spin-current-20260917.NDIlms/)。
- [完整归档](/tmp/kdlock-spin-current-20260917.NDIlms/evidence.tar.gz)，SHA256：
  `f65bc552d854c1b755dfef83a8c0858e63da9c26738940d06152f526dda9980a`。

报告在测量后生成；运行时文档与源文件以冻结归档为准。
