# 2026-09-22：1024 槽直接映射热表的三方性能

> 历史实验：本方案已回退。当前实现与后续性能验收见[回归处理](20260922-performance-recovery.md)；下文保留当时源码、口径与结果。

150/150 场通过，147000000 次完整操作全部完成并排空。测试对象为 Linux 原生、
TCLock 和当前 kdlock，没有旧版 kdlock 测量臂。本轮没有修改执行代码。

## 输入与方法

当前为 Git `1b2c320` 加已有未提交改动，包含 fast 路径优化、删除热表核心抢占检查/
busy、spin/mutex 共享表及1024槽直接映射。完整输入见 host.patch 与源码清单。
宿主与 guest 的 320 个输入文件哈希一致；`kd_hotlock.c` SHA256：
`bec257168bb51291e35d6e00f653f70cb1c4312670920991ef954e36606f6e07`。

仅在 recovery guest `6.1.159-kdclobber2` 构建和运行，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。运行前确认可恢复快照
`pre_static_boot_20260915`；保留 voluntary/nokaslr，未重建 guest 内核。

命令采用 `bench/tclock_compare/run.py --backends native tclock kdlock`
`--cachelines 1 16 --threads 1 4 8 16 20 --repeats 5 --iterations 100000`
`--hotlock-mode observe --scenario plain`。同组后端奇数轮逆序。
每线程绑定 CPU0 至 T−1，均在 NUMA node0，不假设 vCPU 独占宿主物理核。

三方使用相同临界区正文、锁外四组乘加与循环，分别编译各自锁 API。
每场建立新模块会话；JIT准备、单CPU48000次预热和2秒静置不计时。
observe 固定热度准入但保留采样；因此本批包含新采样器开销，不能衡量
adaptive 的热锁发现/碰撞拒绝效果。TCLock 未增加代理计数，KD保留最小正文计数。

## 五轮中位数

每场 `Mops/s = completed × 1000 / wall_ns`，五轮取中位数；
`wall_ns` 从统一放行前的单调时钟开始，到最后一个 worker 返回结束。
每次完整操作包含加锁、锁内更新、解锁、锁外计算和循环；c16一次更新16条
cacheline仍只计一次操作。`ns/op = wall_ns / completed` 是总吞吐对应的
摊销时间，不是获取锁延迟。保留全部样本，不取最佳轮次、不按快慢删样。

| cacheline | 线程 | Linux Mops/s | TCLock Mops/s | KD Mops/s | KD/Linux | KD/TCLock | KD JIT占比 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.269 | 13.895 | 7.277 | 0.421× | 0.524× | 0.00% |
| 1 | 4 | 3.610 | 2.990 | 1.895 | 0.525× | 0.634× | 52.03% |
| 1 | 8 | 3.872 | 4.360 | 3.122 | 0.806× | 0.716× | 94.58% |
| 1 | 16 | 3.838 | 4.973 | 3.875 | 1.010× | 0.779× | 99.78% |
| 1 | 20 | 4.090 | 4.979 | 4.008 | 0.980× | 0.805× | 99.83% |
| 16 | 1 | 13.193 | 12.318 | 6.403 | 0.485× | 0.520× | 0.00% |
| 16 | 4 | 2.088 | 2.236 | 1.623 | 0.777× | 0.726× | 53.16% |
| 16 | 8 | 2.312 | 3.193 | 3.146 | 1.361× | 0.985× | 96.08% |
| 16 | 16 | 2.322 | 3.448 | 3.820 | 1.645× | 1.108× | 99.80% |
| 16 | 20 | 2.432 | 3.320 | 3.865 | 1.589× | 1.164× | 99.82% |

1线程 c1/c16 的 KD 分别为 TCLock 的 0.524×/0.520×。
4线程 c1/c16 的 KD 分别为 TCLock 的 0.634×/0.726×。
20线程 c1/c16 的 KD 分别为 TCLock 的 0.805×/1.164×。

本批为当前三方同期比较，没有修改前 KD 同期对照，不能将历史成绩差异单独
归因于直接映射。每组仅五轮短批次，不将微小差异解释为稳定优化收益。
完整五轮样本和范围保存在 audit.json，未增加 PMU 采样。

## 有效性与范围

150场均通过业务数据、完成数、CPU亲和性、IRQ/preempt恢复及排空检查；
40/40场竞争KD有实际JIT正文，10场单线程KD为NO_JIT自执行样本。
TCLock代理数量为UNMEASURED，不把未知写成零。150份kernel.log无
BUG/Oops/WARNING/stall，最终worker、daemon及锁模块已排空。
构建、导出API与上下文检查通过；未改变原有编译/UBSAN配置。
运行器和审计退出码均为0，源码/冻结ELF哈希及所有吞吐中位数已复核。

本轮是 observe 单锁 plain 吞吐矩阵，未测 adaptive、mutex JIT、nested/early、
跨NUMA、多锁冲突压力或强制native续跑，也未重跑全量单元测试。
前一轮[直接映射功能验证](20260922-hotlock-direct-mapped.md)单独保留，不记为本轮重跑。

## 证据

Guest：`/root/kdlock-evidence/directperf-20260922/`，正式矩阵在 `matrix/`。
包含启动命令、源码清单/patch、构建与运行日志、源码/ELF冻结副本、内核身份、
快照确认、全部plan/records/summary、150份内核日志、退出码和审计。

[完整归档](../../.tmp/directperf_20260922/directperf-20260922.tar.gz)，SHA256：
`5ddf8bc91757e3188d72cd4448c99a2d4c7d8ead32473a12cc20d65f4ac034e1`。
[宿主离线复核](../../.tmp/directperf_20260922/offline-audit.json)核对244个源码/二进制文件及150场计算。
