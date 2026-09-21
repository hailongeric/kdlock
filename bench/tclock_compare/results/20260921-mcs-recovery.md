# 2026-09-21：竞争性能回退调查与恢复

MCS 后置准入版的高竞争回退在同期交错测量中复现。两个定向候选均未消除回退，
因此按用户授权恢复 **包含 ticket 优化的旧版 A**，保留 continuation、抢占配对、
嵌套/提前释放、原生 MCS、owner/ACK/source lease 和 native 借用退休协议。
这次没有把 Git HEAD `644f231` 当作旧版，也没有修改 TCLock、mutex 互斥协议或内核。

## 冻结版本与改动

| 版本 | 内容 | 用途 |
| --- | --- | --- |
| A | MCS 准入调整前，已包含未提交的 ticket 优化 | 同期恢复目标 |
| B | MCS 准入及固定参数内联，尚未迁移统计时钟 | 复现历史 17.9%–19.9% 回退 |
| C | 本次开始时工作树：B 加 MCS admit 更新时间域 | 本次待修复版本 |
| D | C 加 busy word 先读，避免明显会失败的初始 CAS | 独立候选，未保留 |
| E | C 加 observe 在完成时钟/过期更新后跳过重复候选查询 | 独立候选，未保留；adaptive 不变 |
| R | 最终恢复版，生产源码与 A 完全一致 | 当前交付 |

开始前保存工作树全部非忽略文件、哈希和完整 diff。A/B 从已有冻结生产源码重建，
不执行旧归档中的运行器；本次脚本复用当前 `BackendSession` 的准备、实际 JIT、
业务结果、IRQ/preempt 和排空检查。所有版本独立构建、冻结，每场前后核对输入。
KD 各臂共用同一个 workload ELF；TCLock 控制始终使用同一 backend/workload ELF。

R 精确恢复 `include/kd_hotlock.h`、`kernel_module/kd_hotlock.c`、`kd_spinlock.c`、
`lock/spin_calls.inc`、`spin/{nested,nondelegated,slowpath}.inc` 七个生产文件。
已有 `kd_spin_entry.c` 优化不动。对应 fixture 恢复 A 的接口和路径断言；19 条入口
路径保留 pending race、独立嵌套 ticket、一次 pin，以及 pending 不占 ticket 的检查。
continuation/ACK/退休的检测未删除。

保留的 ticket 优化是：顶层 pending 使用 fast owner；claim/reclaim 和 release
各在一次 guard 内检查并提交；slowpath 返回不再重复 claim，容量回退自己完成 claim。
当前再次采用入口热度/上下文判断及合并 `record_*`，首次及每 10240 个样本读取时钟。
公共入口 off 跳过统计；缓存热值可保留到下次批量检查。撤回了“只在 MCS 判断代理”
和“每次 admit 更新过期”的实验，不将这些行为继续写成当前契约。
完整流程、对象创建与数据流见 [EXECUTION_PATHS](../../spin_cacheline/EXECUTION_PATHS.md)。

## 同期复现与两个候选

1/16 cacheline、20 线程、每线程 100000 次、五轮；每轮按版本正反交错，每场新建
会话。observe、代理开启、批次上限 1024、JIT timing 关闭。准备/翻译及单 CPU
48000 次预热不计时，测量前 daemon 退出；只保留最小 JIT 完成计数。
吞吐是完整操作的 Mops/s，不是单独获取锁延迟。

第一组 **40/40** 场业务/上下文正确并排空；百分比相对同组 A：

| cacheline | A | B | B / A 变化 | C | C / A 变化 | TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4.9994 | 4.0172 | −19.65% | 4.0404 | −19.18% | 4.9836 |
| 16 | 4.7928 | 3.9288 | −18.03% | 3.9411 | −17.77% | 3.3419 |

第二组 **50/50** 场正确并排空；D、E 分别从 C 派生，没有叠加。A/C 作为同期控制：

| cacheline | A | C | D | D / A 变化 | E | E / A 变化 | TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5.0031 | 4.0607 | 4.0416 | −19.22% | 4.0628 | −18.79% | 4.9988 |
| 16 | 4.7657 | 3.9491 | 3.9803 | −16.48% | 3.9779 | −16.53% | 3.3251 |

两组所有竞争 KD 均执行了实际 JIT，20 线程 JIT 比例约 99.8%。C 的时钟迁移没有
恢复 B 的下降。D/E 没有达到 A 的 95% 恢复门槛，因此未并入当前源码。
不能将 E 在 c16 的小幅变化归因为整个问题已解决。

D 在 guest 通过原生互斥/抢占 fixture，并额外检查读空后被抢、读忙后释放、
CAS 失败进入 pending，以及保留 peer tail；E 通过采样/窗口及变异检查。
候选功能通过与性能失败分别记录，不能仅凭减少 CAS 或一次查询宣称收益。

## 独立采样能说明什么

A/B/C × c1/c16 各一场、20 线程、每线程 1000000 次；已有 guest perf 6.1.159
使用 `cycles:k -F 199`，只记录 IP/TID/TIME/PERIOD，不记录 callchain。六场均有
实际 JIT、业务正确、排空，丢样数为零。**这些场次不进入吞吐表。**

下表为 sc_worker 样本 period 加权占比，并非每函数独立延迟：

| cacheline | 版本 | 等待 longjmp | run_combiner | diag_find | 热度 access / admit |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A | 84.75% | 1.44% | 0.16% | 0.47% |
| 1 | B | 85.76% | 2.63% | 1.96% | 0.04% |
| 1 | C | 84.30% | 2.65% | 1.54% | 0.55% |
| 16 | A | 85.09% | 1.60% | 0.16% | 0.40% |
| 16 | B | 86.13% | 2.46% | 1.41% | 0.05% |
| 16 | C | 84.79% | 2.53% | 1.36% | 0.55% |

A 用合并 access，B/C 表中只列 admit；B/C note 另约 0.16%–0.21%，不能将表中
最后一列当成三版完全相同的工作。`__kd_spin_lock_longjmp+0x3e1` 主要是本地
等待轮询；多 CPU 等一个 combiner 时，等待样本会占主体，不能直接当作可消除成本。

额外的样本集中在 `kd_spin_diag_find+0x55`（读取 slot 地址之后）和
`run_combiner+0x6fb`（读取 `batch.diag->jit_disabled` 之后）附近。入口还在
初始 lock cmpxchg 附近有集中样本。B 的 admit 本身仅约 0.05%，而回退已经存在，
因此“多调用一个函数”或 C 新增读时钟都不足以单独解释完整下降。

已证明的是**这一组入口/采样路径改动导致可重复的高竞争回退**；执行端诊断读取、
缓存状态及代码布局相互作用是后续调查方向。平坦周期采样有 skid，未采集 HITM/
缓存行转移，不能把上述采样地址当作精确 load 延迟，也未证明唯一的指令级根因。
对象大小不变，JIT 仍实际执行；历史批次长度变化也不是完整因果解释。

## 最终恢复验收

最终 A/R/TCLock × 1/16 cacheline × 1/4/20 线程 × 五轮，**90/90** 场正确排空，
每线程 100000 次，正反交错；其中竞争 KD **40/40** 场都有实际 JIT。
R 六组中位数均达到同期 A 的 95%，20 线程恢复至旧版水平。

| cacheline | 线程 | A | R | R / A 变化 | TCLock | R / TCLock |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 6.2197 | 6.0119 | -3.34% | 13.6378 | 0.441× |
| 1 | 4 | 1.9912 | 2.0568 | +3.29% | 2.9849 | 0.689× |
| 1 | 20 | 5.0075 | 5.0091 | +0.03% | 4.9756 | 1.007× |
| 16 | 1 | 6.0228 | 6.0469 | +0.40% | 12.1605 | 0.497× |
| 16 | 4 | 1.7320 | 1.7035 | -1.64% | 2.2554 | 0.755× |
| 16 | 20 | 4.7734 | 4.7729 | -0.01% | 3.3387 | 1.430× |

A/R 的生产源码完全相同，ELF `.text`、`.rodata`、`.data`、`.rela.text` 哈希相同；
最终各行差异是重复测量波动，不能将四线程 c1 的 +3.29% 称为新优化收益。
c1 单线程 A/R 五次范围分别为 5.9586–6.2819 / 5.7740–6.4549 Mops/s；
本轮没有为缩小波动删除慢样本或追加测量。回退也放弃了 B/C 的单线程路径收益。

两个基础程序加七个相关驱动 **9/9** 通过；plain/nested/early/off/adaptive 五场
功能各完成 400000 次并排空，实际 JIT 为 **189142 / 385281 / 99941 / 0 / 162702**。
off 明确为 DISABLED_CONTROL，adaptive 自然变热。详细检测范围及首次命令错误
见 [测试记录](../../../tests/README.md#mcs-recovery-validation)。

guest 正常生产和观察 provider 的 W=1 构建通过，保留已有换栈 objtool 告警。
最终观察 ELF 核对 node **128 B / align 64**、通知偏移 **64/65**，continuation
**768 B / align 64**、存储栈 **9280 B**、frame **648 B**、ticket **48 B**、
栈上 request **24 B**、fast CPU 状态 **24 B**；20 KiB 预留区和 12 槽限制未变。
恢复汇编读取 SP/IP/BP 的偏移仍为 `0x100/0xe8/0x88`，退休收缩步长 `0x300`；
最后现场读取后才允许回收。真实恢复汇编 fixture 的普通、retry、native 和 MINIMAL
路径继续通过；没有把对象布局一致当作所有运行时序正确的证明。


## 环境与证据

全部构建、单元及运行在 recovery/ext4 guest 完成。`6.1.159-kdclobber2`、40 vCPU，
使用 CPU 0..19，同 NUMA node 0；voluntary、nokaslr，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。实际通过 monitor 确认恢复快照
`pre_static_boot_20260915`；没有修改 guest 内核。miasm/future/pyparsing/pyelftools
版本为 0.1.5/1.0.0/2.4.7/0.27。宿主 CPU 非独占，短时单线程测量仍有环境噪声。

原始证据位于 guest `/root/kdlock-evidence/mcs-recovery-20260921/`：

- `before.tar.gz`、`before-sha256.json`、`before.patch`：开始时完整工作树；
  `rollback-from-C.patch`：从本次开始版本到交付版的最小生产/fixture 回退差异。
- `versions/{A,B,C,D,E,R}`：独立源码、观察 provider、ELF、反汇编、构建日志和哈希；
  `D.tar`、`E.tar`：两个候选的生产/fixture 修改；`shared/`：共用 workload 与 TCLock ELF。
- `diagnosis/`、`candidates/`、`final/`：计划、环境、全部 records/summary 和逐场日志。
  每轮保留五次全部样本，不剔除较慢的有效结果。
- `profiles/`：原始 perf.data、报告、样本、实际符号范围及热点汇总；
  `build.py`、`compare.py`、`profile.py`、`finalize.py`：本次独立实验脚本。
- `unit-rollback-final.log`、`functional-{plain,nested,early,off,adaptive}/`：当前功能；
  `unit-rollback.log` 保留首个命令中误写不存在驱动导致的失败，之后完整定向重跑。
- `final-layout/`、`final-audit.json`：最终 ELF 布局、恢复汇编、源码和排空审计。

191 份逐场 `kernel.log` 未发现 BUG/Oops/WARNING/stall，最终空闲检查通过。
完整归档已取回宿主 `bench/.tmp/mcs_recovery_20260921/mcs-recovery-20260921.tar.gz`，
SHA256：`02b77411517b2ed2a67d2054ea133ab1589033b4d6b807735f6d3d6cba6bb5b1`。
宿主只做离线校验：归档哈希、六版冻结源码与 ELF 哈希、最终审计均匹配。
未在宿主编译或执行测试/benchmark。

这次未运行全量回归、8/16 线程、跨 NUMA、多锁性能或 mutex live。远端 native、
无锁 relay、真实资源同时耗尽的强制内核时序未新增 live 验证；相应生产代码
fixture 的覆盖不等价于真实 JIT 并发。四线程仍低于 TCLock，回退解决的是新增
性能下降，没有宣称消除了 KD/JIT 固有开销或已完成所有低竞争优化。
