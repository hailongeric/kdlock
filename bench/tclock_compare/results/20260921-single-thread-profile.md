# 2026-09-21：单线程执行路径与 PMU profiling

本报告是优化前冻结版本的诊断；后续改动及当前测量见
[无竞争入口优化](20260921-fast-path-optimization.md)，下列旧数据不改写为新成绩。

结论：单线程 KD 的额外成本集中在获取入口、热度/上下文查询、fast owner 路由和
调用现场；本次没有进入 MCS 排队、ticket 分配、continuation 或 JIT 正文。
三种后端均配对关闭/恢复抢占一次，不能通过删除 KD 的 acquisition pin 解决差距。

## 抢占由哪一层负责

已读取当前 guest 内核 `include/linux/spinlock_api_smp.h` 并核对 workload/provider ELF。

| 被测 API | 关闭抢占 | 恢复抢占 |
| --- | --- | --- |
| Linux `__raw_spin_lock/unlock` | 内核 `__raw_spin_lock()` 内 | 内核 `__raw_spin_unlock()` 内 |
| TCLock `komb_spin_lock/unlock` | workload 的 SC_LOCK 宏，在调用 komb 前 | workload 的 SC_UNLOCK 宏，在 komb 返回后 |
| KD clobber-v1 直接 API | `kd_spin_lock_abi()` 内 | 正常 fast owner 解锁或其他对应完成出口 |

Linux 内部的底层锁协议可以依赖外层 pin；当前 KD 显式 CALL 没有经过 Linux
`spin_lock()` 包装，调用者也没有预先 disable，因此 KD 自己负责它。
`kd_hotlock_access()` 检查到已有 preempt_count 后复用该 pin，没有再做一次
preempt_disable/enable。`in_task()` 判断执行上下文，读取 preempt_count 也不等于
修改抢占状态；这些检查与真实的 acquisition pin 应分开讨论。

## 当前单线程路径

```text
Linux：preempt_disable → 无竞争 CAS → 正文 → 原生 unlock → preempt_enable
TCLock：调用者 preempt_disable → komb 的无竞争 CAS → 正文
        → komb unlock → 调用者 preempt_enable
KD：编译器保存 clobber ABI 要求的寄存器，传 SP/IP/BP
    → clobber wrapper → kd_spin_lock_abi 建栈/局部初始化 → preempt_disable
    → 热度记录 → task/softirq/migration 检查 → native ticket 状态查询
    → current_frame 查询 → context_busy 查询 → 无竞争 CAS
    → 发布 per-CPU fast owner → 原生正文
    → unlock wrapper → fast owner 身份核对 → 释放锁字/清除 owner → preempt_enable
    → 恢复调用者寄存器 → 锁外四组乘加/循环
```

`native_active` 仍调用 ticket 查询，但本场 pool 为空，未进入 ticket 分配或等待。
这里仍有栈上的 24 B request 描述和 unlock 的 16 B ref 局部初始化，不能把
“不占用 ticket/continuation 槽”理解成没有任何 C 栈现场成本。

## 方法与有效性

沿用最近三方 benchmark 的同一组源码、provider、workload、client、daemon 和
TCLock ELF，没有构建旧版或修改生产代码。内核 `6.1.159-kdclobber2`、CPU 0、
同一 NUMA 节点、observe、plain；恢复快照和内核基线通过，固定 Python 依赖保留。
每场同样先做单 CPU 48000 次预热及静置；采集只包住正式 client。

- 三方：c1/c16 × Linux/TCLock/KD × 两轮 × stat/sample 分开 = 24 场。
- 当前 KD `spin_delegate=off`：c1/c16 × 两轮 × stat/sample = 8 场，仅诊断配置。
- 每场单线程 50000000 次；共 **32/32 场、16 亿次操作**通过业务、CPU 亲和性、
  IRQ/preempt 和正常排空检查。两个顶层运行器退出码均为 0，最终空闲，无内核错误。
- `perf stat` 分别采集 cycles:k、instructions:k、branches:k、branch-misses:k；
  全部计数运行比例至少 99%，逐场原始值保留。计数涵盖整个 client 的继承任务，
  以完成数归一化，长批次用于摊薄用户端创建/查询相关内核开销。
- `perf record -e cycles:k -F 997` 独立采样，平面 IP，无调用链；仅汇总
  sc_worker，按采样 period 加权。总 38037 个 worker 样本，无丢样。
  使用每场 kallsyms、符号大小及实际 ELF 定位，未知地址保留为 unresolved。
- KD 代理开启和关闭两组的实际 JIT 正文均为零，符合无竞争自执行；不算 JIT 正例。

## 每次完整操作的硬件计数

下表为两轮归一化计数的中位数；用于诊断，不替代五轮短批次正式吞吐。

| cacheline | 后端/设置 | cycles/op | instructions/op | branches/op | branch-misses/op |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Linux | 57.05 | 50.04 | 8.08 | 1.0003 |
| 1 | TCLock | 70.48 | 56.05 | 13.30 | 1.0003 |
| 1 | KD on | 245.62 | 343.86 | 69.88 | 1.0032 |
| 16 | Linux | 74.58 | 95.05 | 8.32 | 1.0003 |
| 16 | TCLock | 87.98 | 101.05 | 13.21 | 1.0004 |
| 16 | KD on | 263.81 | 388.88 | 69.89 | 1.0035 |
| 1 | KD off | 124.91 | 160.07 | 30.01 | 1.0006 |
| 16 | KD off | 142.07 | 205.08 | 30.01 | 1.0006 |

c1 的 KD on 指令数约为 TCLock 的 6.14 倍；branches 多约 56.6 次/op，但
branch-misses 都约 1 次/op，本批没有显示额外分支误预测是主要差距。
KD off 从约 245.62 降到 124.91 cycles/op，仍高于 TCLock 的 70.48。
该配置跳过热度及上下文准入，同时改走带 nondelegated 计数的原生获取路径，
因此差值代表这组路由的综合影响，不能称为“热表单独消耗 120.7 cycles”。
关闭代理只是诊断，未更改默认配置，也不是建议删除代理能力。

## KD 周期采样热点

两轮按原始周期权重合并，以下为 c1 / on 的独占 IP 归属：

| 符号/区域 | 权重 |
| --- | ---: |
| `kdlock_km:kd_spin_lock_abi` | 28.71% |
| `kdlock_km:kd_hotlock_access` | 17.67% |
| `spin_cacheline:sc_body_1` | 12.31% |
| `kdlock_km:kd_spin_unlock` | 10.51% |
| `spin_cacheline:sc_ioctl` | 7.63% |
| `kdlock_km:kd_exec_context_busy` | 7.10% |
| `kdlock_km:kd_exec_current_frame` | 6.91% |
| `kdlock_km:kd_entry_lookup` | 4.32% |

这些是采样事件权重，不是精确函数计时或可直接兑现的优化收益。获取入口最热偏移
之一是 CAS 后的 `+0x188`，不能把整个 28.71% 全算成建栈或抢占成本；非精确
cycles 事件存在 skid。热表热点在桶/entry 寻址与读取，不能只归咎于周期采时。
两个 context helper 都重新获取当前 CPU context 并读取 depth，空 context 也调用两次。

## ELF 揭示的固定成本与优化顺序

1. **将慢路径局部准备移出无竞争函数。** TCLock 的获取 ELF 先执行 CAS，
   成功时直接返回，`push rbp/rbx` 位于失败分支之后。`kd_spin_lock_abi()` 在 CAS 前就保存
   rbp/rbx/r12–r15、对齐栈、预留 0x30 B、写入/校验 canary、清零 24 B request。
   `kd_spin_unlock()` 也在 fast owner 判定前预留栈、清零 16 B ref 并做 canary。
   可以优先拆分实际慢路径函数，让编译器减少 fast path 的局部准备；保留全局栈
   保护配置，不通过关 canary、放宽 ABI 或删除生命周期检查获得数字。
2. **合并必要的 context 查询。** 当前 `kd_exec_current_frame()` 和
   `kd_exec_context_busy()` 分别读取同一 context 的 depth/owner。评估一次读取
   并保留全部准入语义；同时考虑 native ticket 空池查询的调用边界。
3. **精简热度记录的通用路径。** 生产 spin record 的 kind/record 是固定值，
   评估专门路径减少通用 record/query 分支与调用成本；继续保留 CPU/锁计数、
   精确地址匹配、重入保护和固定时间窗口，不能用 observe 不统计来替代。
4. **再评估调用者与 fast owner。** clobber ABI 的 caller 保存 rbx/r12–r15，
   lock/unlock 都计算 SP/IP/BP 并经过独立 wrapper；需要保留原生续跑和 JIT
   的完整 ABI。fast owner 的写入、匹配和清理是协议状态，不能直接省略。

这四项是由测量支持的优化方向，本次没有实施或声称已获得优化收益。
此前完整 MCS 后置准入实验发生竞争退化，不能从单线程热点直接推断重新排序
整个准入协议会改善四线程/高竞争；修改后仍需对应功能和三方性能检查。

## 与短批次成绩的关系

长批次 stat 的 c1 wall 约为 Linux 19.9、TCLock 24.7、KD 85.7 ns/op；此前
100000 次正式矩阵的中位数约为 58.2、72.6、159.7 ns/op。两者窗口不同，
不能将长批次计算出的 Mops 混入原 150 场表格。
旧短批次逐场 wall 与 worker CPU 时间差的中位数为 Linux 15.8、TCLock 9.4、
KD 28.1 ns/op，说明起跑/调度等非 worker CPU 时间也参与原始成绩；它不等于
纯线程创建开销。剩余短/长差异没有单独采集频率或调度轨迹，不能全部归因于 DVFS。

## 原始证据

Guest：`/root/kdlock-evidence/single-profile-20260921/`（三方）、
`/root/kdlock-evidence/single-profile-off-20260921/`（当前 KD off）；联合审计在
`/root/kdlock-evidence/single-thread-diagnosis-20260921/`。
归档保留命令/退出码、内核身份、源码与 ELF、原始 stat CSV、perf.data、kallsyms、
模块地址、平面样本及热点偏移、逐场业务与排空记录。宿主只读复算全部平面样本，
不执行归档中的代码。

[完整归档](../../.tmp/single_thread_profile_20260921/single-thread-diagnosis-20260921.tar.gz)
SHA256：`e5a1441d7a00d5d45ce4199481bea240d5b45cae81653ccfc2eeeb74e8fa8368`。
[离线核验](../../.tmp/single_thread_profile_20260921/offline-audit.json)。
本次没有新单元回归、竞争/嵌套/远端续跑验证；生产实现与已有未提交修改均保留。
