# 2026-09-20：TCLock 与上游一致性核对

**当前被测后端是 TCLock 的 Linux 6.1 移植版，并非上游 RCUHT 实验的原样构建。**
核心委托协议及 NUMA/PREFETCHING/WWJUMP 优化仍在，但编译分支、批次额度、
换栈实现、插桩和运行条件都有实质差异。现在的结果证明这一移植版在当前 VM
负载上的表现，尚不能作为论文复现成功或失败的判断。

本次仅检查源码、配置和 9/19 留存的 ELF/结果，没有编译、加载模块或重跑性能。
工作区 HEAD 为 `b4b16ca09d4b2833196b265e93bac934583fa3ef`，包含既有未提交改动。

## 来源及实际被测版本

- 本机 `/home/eric/TCLocks` 是干净工作树，HEAD 为
  `bbfb9f00a12af51dff6ca291cb9829a82960c2ef`。
- 本项目 `tclock_backend/upstream/` 四个文件与该树的 `src/kernel/rcuht/`
  文件逐字节相同，SHA256 全部符合 `UPSTREAM.json`。
- `port.patch` 的四组 hunk 均能从原文件重建当前对应文件；补丁没有漏记
  `komb.c`、`context.S` 和两个头文件的差异。provider/compat/Makefile 为额外适配文件。
- 当前上述七个实现/构建文件与 `rcuht-20260919-compare01/source/` 冻结版本
  逐字节相同。该轮 TCLock ELF SHA256 为
  `af450e547799f018cee92fe30886851240e5d9fd6bf6110251730cdf0857bcba`。

原项目本身有两种构建：内核 `kernel/locking/komb.c` 链接到 RCUHT 的同一份
`locks/komb.c`，但宏和参数不同。当前使用内核集成版的分支与默认额度，再接上
改编的 RCUHT 正文；因此“来源文件一样”不能推出“等同上游哈希表测试”。

## 会影响结果的差异

| 项目 | 上游 RCUHT / 仓库保存的配置 | 当前实际测试 |
| --- | --- | --- |
| 编译分支 | RCUHT Makefile 定义 `KERNEL_SYNCSTRESS` | 未定义，采用内核集成版轮询分支 |
| IRQ 与任务状态 | RCUHT 分支未定义 `ENABLE_IRQS_CHECK` | 已启用，排队前检查嵌套、`in_task()`、IRQ、migration；代理 unlock 保存 IRQ 状态 |
| 等待期间调度 | 节点等待宏可在 `need_resched()` 时执行 `preempt_enable(); schedule(); preempt_disable()` | 节点等待只轮询；锁外另有 `cond_resched()` |
| 批次额度 | RCUHT 默认 `262144`，正式 spinlock 脚本未覆盖；另有额度扫描脚本 | provider 默认及每场 insmod 参数均为 `1024` |
| 编译器、内核 | 保存的配置为 GCC 9.4；源码树名 `linux-5.14.16`，RCUHT 显式要求 GCC 9 | ELF 为 GCC 11.4；`6.1.159-kdclobber2` |
| UBSAN | 保存的 `.config` 未启用 | `UBSAN=y`、`UBSAN_SANITIZE_ALL=y`，ELF 确有边界检查 |
| 换栈与返回 | C 内联汇编，原慢路径手写 `retq` | 独立 `context.S`；有 ENDBR 与 `__x86_return_thunk` 返回 |
| 锁内执行计数 | 没有本项目三个 `tc_*` 计数 | 每个代理请求增加 delegated/completed，各批增加 batches |

源码定位：上游 `rcuht/Makefile:30`、`rcuht.c:87`、`locks/komb.c:45`、
`include/spinlock/komb.h:4`；本项目
[Makefile](../../../tclock_backend/Makefile)、
[分支头文件](../../../tclock_backend/include/spinlock/komb.h)、
[节点等待](../../../tclock_backend/komb.c#L37)、
[排队状态检查](../../../tclock_backend/komb.c#L958)、
[代理解锁](../../../tclock_backend/komb.c#L1230)、
[额度与计数定义](../../../tclock_backend/provider.c#L37)。

几个区别需要精确解释：

1. **IRQ 检查和纯轮询不是本项目凭空发明的算法**，它们来自上游内核集成分支，
   但不同于论文 RCUHT 的构建分支。加上锁外调度点没有恢复锁内等待的调度行为。
   不能直接打开整个 `KERNEL_SYNCSTRESS` 宏：它还依赖原头文件和等待栈/调度约定，
   应单独核对兼容性。
2. **UBSAN 插桩确实进入热函数。** 留存 ELF 的 `komb_spin_unlock+0x5a` 有数组
   边界比较，`+0x1f6` 为对应异常分支；多个 per-CPU 下标路径也有检查。
   `__ubsan_handle_out_of_bounds` 的存在不表示正常运行执行了报错函数。
   两种 workload ELF 都有相同数量的 UBSAN 引用，不能将所有插桩成本只算给 TCLock；
   但 TCLock 自身还有队列、上下文下标检查。实际净开销需控制变量测量。
3. **换栈机制保留，不代表机器码成本相同。** 六个寄存器的保存/恢复顺序与 RSP
   交接保留；慢路径用 R12 保存跨 C helper 调用的锁地址。留存 ELF 的
   `komb_context_switch` 确实跳到 return thunk，还含两个连续 ENDBR。
   两个 ENDBR 是可清理的重复，但没有证据证明它是主要瓶颈。
   两边配置均启用 frame pointer，不能把“当前有帧指针”单独当成新增原因。
   当前启用 stack protector/IBT/RETHUNK，也不能由配置直接推算百分比损失。
4. **执行计数不是零成本只读观察。** 二进制中的 `tc_delegated`、`tc_completed`
   是 per-CPU `incq %gs:...`；`tc_batches` 也是批内更新。读取发生在计时外，
   更新发生在计时内。它们用于验证真实代理，不是 hotlock 选择器。
   `WRITE_ONCE` 改为 `smp_store_release` 后，当前 x86 ELF 的完成发布仍是普通
   16 位 store，没有为此额外生成 fence，不能误归因为新增硬件屏障。
5. **1024 是上游内核版默认，不是上游 RCUHT 默认。** WWJUMP 的 counter 记录
   后继跳转，首个代理请求另计，参数不应解读为精确的“最多 1024 个完成请求”。
   四线程均值仅约 2.11 次/批，旧独立诊断也没有四线程额度退出，增大额度不是
   四线程问题的首要解法；20 线程约 808.51 次/批，额度可能限制持续批处理，
   但当前没有该哈希表负载的额度退出占比，不能量化影响。

ELF 检查使用 `objdump -dr`，反映加载前代码。IRQ flags 路径可见 `pv_ops`
重定位；加载时的 paravirt/alternatives 修补未在本次读取，不能把磁盘中的
间接调用直接当成运行中每次支付的具体指令序列。

## 核心算法检查结果

NUMA 队列选择、六条 cacheline 预取、WWJUMP 均保持启用。CAS/pending、队列交接、
combiner 执行借用栈、代理 unlock 跳往下一 waiter、返回后发布完成的主流程保留。
`next_node->next`、IRQ 节点、额度和 `need_resched()` 的批次退出条件也在上游，
不是本项目为性能实验新增的代理筛选。不能为追求吞吐一并注释掉。

当前没有在 direct API 热路径恢复 hotlock/目标地址选择器。provider 的
`target_lock` 仅用于计时外绑定和排空诊断。没有发现核心优化误关闭的证据；
源码审查及历史单锁正确性检查也不构成完整语义等价证明。

## 临界区相似，整个实验仍不同

当前保留上游 `rcuhashbash_write_lock()` 的查源节点、同桶处理、目标冲突检测、
删除/改键/重新入链的逻辑。一把全局锁、1024 桶、4096 节点、8192 键范围和
100% 写请求与上游 spinlock 脚本相符。仍有以下差异：

- 当前桶/节点固定 64 字节步长，静态预分配；上游桶带多种锁的 union，节点带
  `rcu_head`，通过 slab 分配。缓存占用、对象间距和分配位置没有原样复现。
- 当前每轮两次 xorshift64*；上游 `rcu_random` 还做读写选择。当前按用户选择
  保留四组锁外乘加，上游该写循环没有相同工作。
- 当前为用户 worker 批量 ioctl，每线程固定 100000 次；该轮 wall 时长实际为
  0.014–1.264 秒。上游是内核线程，由脚本运行 30 秒后停止。启动/收尾与争用
  稳态的比例不同，短批次波动不能直接视为锁算法差异。
- 当前只测 guest CPU 0–19，同属 guest NUMA node 0。既有宿主 affinity 记录
  没有证明物理核独占绑定，也没有复现跨物理 socket 的数据传输条件。
- 当前 baseline 是 Linux 6.1 原生锁；上游 baseline 属于其 5.14 实验环境。
  当前配置还允许 PV spinlock，实际运行选中了哪条路径没有在本次确认。

论文的 RCUHT 大收益依赖跨 socket 和很长的批处理，文中报告批量可达 50000；
第 7 节也明确讨论 2–4 核时换栈成本难以摊薄。摘要的 5.2× 出现在用户态
LevelDB 实验，不能当成当前四线程哈希表的目标倍率。
参见[论文第 6.3、6.4、7 节](https://www.usenix.org/system/files/osdi23-gupta.pdf)。
论文实现章节标注 Linux 5.14.19，而发布仓库源码树名为 5.14.16；这里分别记录，
不把它们误写成已经核实相同的论文二进制。

9/19 已有结果仍有效，但结论限于移植版：4 线程为 Linux 的 **0.876×**，
8/16/20 线程为 **1.335× / 1.564× / 1.571×**；四线程约 2.11 次/批。
这说明委托在较高争用下已有收益，不能据四线程较慢认定 TCLock 没有工作。
数据来自[已有 50 场记录](20260919-rcuht.md)，本次没有新性能成绩。

## 建议的验证顺序

先把“移植版优化”和“论文复现”分开标记。定位当前版本时，先延长测量、固定
宿主 vCPU 亲和性，再分别测额度和插桩的影响；各次只改变一个因素，保留正常
正确性验证与诊断构建，不能把关掉观察后的零计数当作已通过原验收。
若要声称复现论文，应另设固定上游版本、原工具链/RCUHT 分支和原测试程序的
基线，并记录物理 NUMA 条件。它不应直接覆盖当前 kdlock 实验内核。

本次确认了不一致项，但没有测得各项的独立贡献；不能保证改一个参数就恢复
论文倍率，也没有以猜测为由删除调度、IRQ 或协议检查。

## 本次离线证据

- [哈希、配置及历史数据核对](../../.tmp/tclock_upstream_audit/20260920/audit.json)
- [原版到实际移植代码的 diff](../../.tmp/tclock_upstream_audit/20260920/source.diff)
- [上一轮实际 TCLock ELF 反汇编](../../.tmp/tclock_upstream_audit/20260920/tclock_backend.objdump.txt)

结果：上游文件 4/4、当前与冻结实现 7/7、补丁目标 4/4 均一致；已有 50 场记录
共 49000000 次操作，数据检查和排空全部成功。本轮只更新报告及文档表述，
没有修改锁协议或测试配置，没有新增运行测试，也没有提交 Git。
