# 2026-09-21：Linux / TCLock / 当前 kdlock 三方实测

**150/150 场通过，共 147000000 次操作，全部排空。** 按用户要求只测 Linux 原生、
TCLock 和当前 kdlock；没有旧版 KD 测量臂。本轮未修改执行代码。

## 输入与测试方法

- 实现对应提交 `1b2c320`，开始时另有五份测试对象/计划文档修改；314 个跟踪文件
  的宿主/guest 哈希完全一致。当前 `kd_hotlock.c` SHA256 为
  `f415fe99263ef63dd74544167528df4b8c61dd40e51182b519ff6c701e1f3d92`。
- recovery guest，内核 `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。运行前从 monitor 确认
  `pre_static_boot_20260915` 快照，保留 voluntary/nokaslr；没有重建 guest 内核。
- 当前三方运行器：`--backends native tclock kdlock --cachelines 1 16`
  `--threads 1 4 8 16 20 --repeats 5 --iterations 100000`
  `--hotlock-mode observe --scenario plain`。共 150 场，奇数轮逆序。
- 每线程绑定 CPU 0 至 T−1，均在 NUMA node 0；不假设 vCPU 独占宿主物理核。
  每场重新加载/卸载会话，三方使用相同正文与锁外四组乘加。
- JIT 准备、单 CPU 48000 次预热和随后 2 秒静置不计时。observe 固定 KD 准入，
  保留热度统计；关闭 JIT timing，保留最小实际正文计数。TCLock 无新增代理计数。
- 主线程在统一放行前记录 `CLOCK_MONOTONIC`，最后一个 worker 的批量 ioctl
  返回后结束计时。每次完整操作含获取、锁内计数更新、解锁、锁外计算与循环；
  c16 一次更新 16 条 cacheline，仍算一次操作，不把完成数乘以 16。

## 五轮中位数

每场 `Mops/s = completed × 1000 / wall_ns`，然后按配置对五场取中位数。
`ns/op = wall_ns / completed` 是总吞吐对应的摊销时间，不是线程获取锁的延迟。
比值用未舍入的中位数计算，不取最好一轮，不按快慢剔除或补测样本。

| cacheline | 线程 | Linux Mops/s | TCLock Mops/s | KD Mops/s | KD/Linux | KD/TCLock | KD JIT 占比 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.169 | 13.767 | 6.260 | 0.365× | 0.455× | 0.00% |
| 1 | 4 | 3.584 | 2.979 | 2.008 | 0.560× | 0.674× | 51.70% |
| 1 | 8 | 3.881 | 4.286 | 3.947 | 1.017× | 0.921× | 97.62% |
| 1 | 16 | 3.785 | 5.026 | 4.928 | 1.302× | 0.980× | 99.81% |
| 1 | 20 | 4.097 | 4.986 | 4.995 | 1.219× | 1.002× | 99.83% |
| 16 | 1 | 12.893 | 10.929 | 5.976 | 0.463× | 0.547× | 0.00% |
| 16 | 4 | 2.139 | 2.231 | 1.694 | 0.792× | 0.759× | 50.59% |
| 16 | 8 | 2.283 | 3.217 | 3.913 | 1.714× | 1.217× | 98.32% |
| 16 | 16 | 2.323 | 3.467 | 4.729 | 2.036× | 1.364× | 99.81% |
| 16 | 20 | 2.409 | 3.322 | 4.760 | 1.976× | 1.433× | 99.85% |

四线程 c1/c16 的 KD 分别为 TCLock 的 0.674×/0.759×，差距仍在。
二十线程 c1 为 TCLock 的 1.002×，本批近似持平；c16 为 1.433×。
这是当前三方同期比较，没有旧版 KD 对照，不用于推断此前某项改造的增益。

## 检查与解释范围

所有场次通过业务计数、完成数、CPU 亲和性、批次 IRQ/preempt 恢复和正常排空检查。
KD 40/40 场竞争会话有实际 JIT；10 场单线程 KD 为 NO_JIT 自执行性能样本。
TCLock 代理数量为 UNMEASURED，不据此声称没有代理或已观测到代理次数。
150 份 kernel.log 无 BUG/Oops/WARNING/stall；最终 worker/daemon/provider 已排空。
源码与实际二进制哈希一致，构建/导出接口/上下文及 UBSAN 引用检查通过；仍保留
原有手写换栈 objtool 告警。

这是 observe 单锁 plain 吞吐矩阵；没有重跑 adaptive、mutex JIT、nested/early、
跨 NUMA、多锁碰撞或远端 native 强制时序，也没有新增 PMU 采样或完整单元回归。
每配置只有五轮 guest 短批次，不计算置信区间，不将微小差异视为稳定优化收益。
全部样本、最小/最大值与 JIT 比例保存在 audit.json；准备阶段不属于成绩。

## 证据与归档

Guest：`/root/kdlock-evidence/threeway-current-20260921-2253/`，正式运行结果在
`matrix/`；command.json 保存完整启动参数，host.patch 保存开始时的文档差异。
源码/ELF、运行器日志、plan/records/summary、150 份内核日志、快照输出及 audit.json
一同保留。宿主只读复核 238 个冻结源码/二进制文件及全部样本计算，不执行归档代码。

首次归档脚本在审计通过后重复复制自身，触发 SameFileError；修正该归档步骤后成功。
首次脚本与错误记录仍在归档中，没有重跑、替换或拼接任何性能样本。
顶层 detached timeout 进程未单独捕获退出码；正式汇总完整、无 failure.json，
最终审计退出码为 0，见 audit-exit.json。

[完整归档](../../.tmp/threeway_current_20260921/threeway-current-20260921-2253.tar.gz)
SHA256：`949d9e02523626e72cf441b7a51b1de1d02d5148fc882a10a9774980f79820b8`。
[宿主离线核验](../../.tmp/threeway_current_20260921/offline-audit.json)。归档后仅更新结果文档，
没有改变已测执行代码。后续继续使用 [当前三方入口](../README.md)，不运行旧版 KD 对照。
