# 2026-09-22：当前版本完整三方单轮基线

按用户要求测量提交 `1928434`：Linux 原生、TCLock、当前 KD，完整矩阵每配置一轮。
30/30 场有效，计时区间完成 2940 万次操作，所有会话正常排空，运行器退出码 0。
本轮没有修改生产代码、TCLock 或 guest 内核；报告及 README 在测量结束后更新。

## 配置与口径

- cacheline 负载，`plain`、`observe`、`spin_delegate=on`。
- 1/16 cacheline × 1/4/8/16/20 线程 × 三种后端，共 30 场；每线程 100000 次。
- 每场先进行单 CPU 48000 次预热；入口登记、JIT 翻译、预热均在计时外。
- 每配置仅一个有效样本，不追加重复；`best_*` 兼容字段即该唯一会话。
- 吞吐和 ns/op 包含完整获取、正文、解锁、锁外四组乘加及循环；ns/op 为摊销时间。
- guest 为 `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，ext4、nokaslr、voluntary。
- 运行前后确认同一 QEMU 的 40 个 vCPU 逐一绑定宿主 CPU0..39；测量使用 CPU0..T−1，
  前 20 个位于宿主 NUMA0。monitor 确认恢复快照 `pre_static_boot_20260915` 存在。
- 宿主与 guest 的 325 个跟踪文件 SHA256 全部一致，无需同步；固定 Python 依赖核验通过。

## 实测结果

各后端数值均为 **Mops/s / ns/op**；比值按未舍入吞吐计算。

| cacheline | 线程 | Linux | TCLock | KD | KD/Linux | KD/TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.903 / 59.16 | 13.702 / 72.98 | 6.369 / 157.00 | 0.377× | 0.465× |
| 1 | 4 | 3.487 / 286.79 | 2.921 / 342.32 | 1.901 / 526.07 | 0.545× | 0.651× |
| 1 | 8 | 3.831 / 261.00 | 4.442 / 225.10 | 4.125 / 242.42 | 1.077× | 0.929× |
| 1 | 16 | 3.754 / 266.40 | 5.011 / 199.57 | 4.905 / 203.87 | 1.307× | 0.979× |
| 1 | 20 | 4.256 / 234.97 | 5.027 / 198.93 | 4.974 / 201.05 | 1.169× | 0.989× |
| 16 | 1 | 14.122 / 70.81 | 10.966 / 91.19 | 5.779 / 173.03 | 0.409× | 0.527× |
| 16 | 4 | 2.114 / 472.97 | 2.114 / 473.11 | 1.637 / 610.91 | 0.774× | 0.774× |
| 16 | 8 | 2.319 / 431.24 | 3.094 / 323.22 | 3.920 / 255.13 | 1.690× | 1.267× |
| 16 | 16 | 2.361 / 423.46 | 3.296 / 303.44 | 4.684 / 213.48 | 1.984× | 1.421× |
| 16 | 20 | 2.427 / 412.04 | 3.275 / 305.37 | 4.760 / 210.10 | 1.961× | 1.453× |

单线程 KD 为 TCLock 的 0.465×/0.527×；四线程为 0.651×/0.774×，低竞争差距仍在。
20 线程时，c1 接近 TCLock，c16 为 TCLock 的 1.453×、Linux 的 1.961×。
这是本轮唯一有效样本的结果，不据此声称稳定分布，也不与历史两轮最大值混算。

## 验证与边界

业务数据、每个 worker 的完成数与 CPU 亲和性、批次 IRQ/preempt 状态、内核日志及排空检查通过。
2 场单线程 KD 均为 `NO_JIT` 自执行；8 场竞争 KD 均为实际 JIT `PASS`。
KD 实际代理比例在四线程为 59.37%/58.75%，八线程为 97.79%/98.08%，
16/20 线程均超过 99.69%。TCLock 未启用额外代理计数，其代理次数和比例保持 `UNMEASURED`。

10 场 KD 均完成 source retirement，10 场 TCLock 均通过 quiescent 检查；运行结束无
worker、daemon、KD/TCLock provider 或 workload 残留，未发现内核错误，冻结输入保持一致。
本轮实际加载了所需 benchmark 模块；KD 参数 `mutex_jit=1` 沿用默认值，但负载仅使用 spin。
未执行独立单元、SELFTEST、nested/early、mutex 负载或 PMU profiling。

## 命令与证据

在已验证的 recovery guest 中，使用固定 venv 的 PATH，并设置
`KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 LC_ALL=C`：

```sh
timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 16 \
  --threads 1 4 8 16 20 --repeats 1 --iterations 100000 \
  --scenario plain --hotlock-mode observe --spin-delegate on \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spinbench-baseline-20260922T082523Z
```

SSH 外层另设 3660 秒超时。完整 guest 目录为
`/root/kdlock-evidence/spinbench-baseline-20260922T082523Z/`。

- [汇总 CSV](../../.tmp/spinbench-baseline-20260922T082523Z/summary.csv)
- [全部会话记录](../../.tmp/spinbench-baseline-20260922T082523Z/records.json)
- [运行后审计](../../.tmp/spinbench-baseline-20260922T082523Z/post-run-audit.json)
- [完整归档](../../.tmp/spinbench-baseline-20260922T082523Z/spinbench-baseline-20260922T082523Z.tar.gz)
- [归档 SHA256 校验](../../.tmp/spinbench-baseline-20260922T082523Z/archive-audit.json)

归档 SHA256：`24e9ef5d788cec1ce3d8deab270ec067f97da0a2f2dbd7a8681b31ecde97a206`。
宿主已逐项校验归档内 245 个冻结源文件及 8 个二进制的哈希，并核对其中 176 个
跟踪源文件与测量前的宿主清单一致。归档保存在忽略目录，新 checkout 不自带原始数据。
