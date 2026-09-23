# 2026-09-22：普通 spin 保持 IRQ/BH 状态

> 保留普通spin IRQ/BH与wrapper修复的验证证据及首次失败。本报告属于当时冻结版本，不代表当前版本已重跑全部边界；最新测量见[完整三轮矩阵](20260923-spin-default-heat-full3.md)。

当前 KD spin 按普通 `raw_spin_lock` 语义获取与释放：保留抢占配对，
不默认保存、关闭或恢复 IRQ/BH。本次未新增 irqsave/bh API，未修改 TCLock
或 guest 内核，保留此前未提交的热表和两轮取最大值改动。

## 实现

- 删除 spin 代理慢路径、嵌套队列的整段 IRQ 屏蔽及 continuation 的 `irq_flags`；
  仅 task context 使用的 ticket guard 改用普通 raw spin 获取/释放。
- 每 CPU 节点用单指令计数占用/归还。combiner 借出节点前保存独立信息，
  批次返回后先重新占用再写回；生产者读完节点后才归还。
- `kd_spin_entry_end_pinned()` 先退休 ticket 元数据，保留获取 pin。
  恢复汇编读完全部现场后退休 continuation，再在已恢复任务栈上调用保留
  GPR 的 helper 执行 `preempt_enable()`；重试和有锁 native 续跑保留 pin。
- 修复 wrapper FULL 出口提前抬高 RSP、随后继续读取私有元数据的问题：
  全部元数据读完后才释放栈。物理栈仍在执行者栈上，逻辑 SP 模型不变。

普通/SELFTEST guest ELF 均核对：continuation 704 B、64 B 对齐，存储栈
8512 B（64 B 头部和12条记录）；每 CPU 总预分配仍为20 KiB。native input
40 B；节点128 B、64 B对齐，通知位偏移64/65。frame/regs 偏移仍为32/104，
queued_at_ns 为696。wrapper固定物理栈区仍176 B，原有偏移未变。
反汇编确认 spin 慢路径、恢复函数和 ticket 最终退休函数无 CLI/STI/PUSHF/POPF；
最终 unpin 使用内核抢占计数和调度 thunk。

## 验证

基于 `1b2c320` 的未提交工作树，只在 recovery guest `6.1.159-kdclobber2`
构建/执行。内核 Build ID 为 `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，
nokaslr、voluntary，4线程绑定本地CPU。普通和SELFTEST构建通过。

`make -C tests/unit run` 加以下直接相关 PY_TESTS，共12/12通过：

```text
spin/test_spin_entry.py spin/test_spin_wait.py spin/test_spin_shadow.py
spin/test_spin_outer_progress.py spin/test_spin_batch.py spin/test_spin_preempt.py
spin/test_spin_direct.py execution/test_exec_capacity.py
codegen/test_clobber_abi.py spin/test_spin_wwjump.py
```

恢复夹具覆盖192种结果/寄存器组合，最终解除抢占时覆盖已退休包，证明后续
不再读取它。wrapper 回归模拟中断覆盖当前 RSP 下方空间，覆盖 spin/mutex ABI
与混合返回，并确认重新引入提前释放栈的错误会被检出。节点9个错误变体均检出。

实际 JIT 使用 `bench/tclock_compare/run.py --functional --backends kdlock`
`--cachelines 1 --threads 4 --repeats 1 --iterations 100000`：

| 场景 | 完成数 | 实际 JIT 正文 | 排空 |
| --- | ---: | ---: | --- |
| plain-observe-on | 400000 | 170999 | 通过 |
| nested-observe-on | 400000 | 299123 | 通过 |
| early-observe-on | 400000 | 99438 | 通过 |
| plain-adaptive-on | 400000 | 159057 | 通过 |

共160万次操作，业务、IRQ/preempt 恢复和排空正常，最终 guest 空闲。
生命周期探针确认热表替换不破坏实际 owner、最终锁字为0，原生 mutex 从CPU1
迁移至CPU2且抢占配对正常；`spin_entry_selftest=1`，`mutex_jit=0`。
最终批次内核日志无 BUG/Oops/WARNING/stall。源码/冻结ELF哈希一致，宿主离线
复核1052个文件。没有运行性能测试、全量单元、mutex 实际JIT、强制native续跑
或IRQ/NMI竞争矩阵；模拟栈覆盖不等于覆盖任意中断上下文。

## 首次失败与修复

首次批次 plain 完成，但 nested 在 wrapper FULL 出口发生 NULL dereference。
故障现场的描述指针变成 `0x246`，对应已释放栈区被中断现场覆盖。保存串口后
重启同一 guest，修复栈释放顺序并从单元到四项功能完整重跑，未拼接首次通过项。
新夹具第一次编译缺少直接调用类型声明，修正后12项通过；失败日志亦保留。

## 证据

Guest 最终批次：`/root/kdlock-evidence/plainspin-irqfix-20260922/`。
[完整归档](../../.tmp/plainspin_irqfix_20260922/plainspin-irqfix-20260922.tar.gz)，SHA256：
`a6abafa03f89eff112cc68abf09442fc41d7ce6d5b0931ef5132b7bfbd389c1d`。
[离线复核](../../.tmp/plainspin_irqfix_20260922/offline-audit.json)。

[首次失败归档](../../.tmp/plainspin_irqfix_20260922/plainspin-20260922-failed.tar.gz)，SHA256：
`5d71ac16af4eb08e0fb196f0f994fc212f8795a5c47c29cea736852a4db16d8e`。
包含当时源码、ELF、功能日志和重启前串口；该批次未排空，不计为通过。
