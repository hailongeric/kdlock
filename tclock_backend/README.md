# TCLock 原生委托后端

这个独立实验使用完整 TCLock spinlock 执行路径，经现有 `kdclobber1` 普通 spin
hook 接入同一个 `spin_cacheline` 工作负载。锁字、队列、pending、shadow 栈、
六个 callee-saved 寄存器保存、物理 RSP 切换及 WWJUMP 均来自上游 TCLocks。
不使用 kdlock 的 shadow lock、JIT、翻译注册表、寄存器包或 daemon。

来源固定为 [TCLocks](https://github.com/rs3lab/TCLocks) 的提交
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`。`upstream/` 保留四个未修改文件，
`UPSTREAM.json` 记录哈希；`port.patch` 记录移植差异。保留原 GPL-2.0 及作者声明。
四个文件均来自该提交的 `src/kernel/rcuht/` 子树；差异文件用于审查，不是直接
应用到另一内核的安装补丁。

## 移植边界

- 采用上游内核版的纯轮询路径；不启用 rcuht 的 `KERNEL_SYNCSTRESS` 分支，
  该分支会在 per-CPU shadow 栈上调用 schedule。普通入口由接口层管理 preemption。
- 保留 WWJUMP、NUMA 队列选择和六条 cacheline 预取。批次上限为上游内核默认
  1024，与当前 kdlock 一致；上游 rcuht 自定义的 262144 不用于本轮。
- 将 C 内联切栈汇编移至 `context.S`，保持六寄存器顺序和原生 CALL 续点。
  普通 C 调用可能破坏参数，故入口在 R12 保存锁地址。保留当前内核的 frame
  pointer/缓解配置及 return thunk；自定义切栈不承诺完整栈展开。
  本轮 `W=1` 构建成功但仍有 objtool 栈/帧指针告警，原始构建日志保留。
- 增加分配失败回收和 Linux 6.1 类型适配；完成通知明确使用 release store。
  两个只读 per-CPU 计数分别记录抵达代理 unlock 与离开借用栈后的完成发布，
  排空后两者须相等。`quiescent` 核对锁字及所有 CPU 的队列/上下文状态。

`provider.c` 只接管 `target_lock` 指定的普通 spinlock，其他锁调用原生实现。
这是可恢复 benchmark 的独立后端，不是任意临界区的通用透明替换：本轮负载只
访问全局计数器，没有 task/per-CPU 数据、嵌套锁、服务调用或中途调度。
原版 TCLock 的完整慢路径保留在 `komb.c`，不据本轮单锁结果声称其他场景已验证。

所有构建和运行遵循 [操作手册](../docs/AGENTS.md)，只在 recovery guest。
模块互斥安装现有 spin hook，不改内核；必须保留 source workload，直到客户端
全部退出、`quiescent=1`、delegated/completed 相等，再卸载后端，最后卸载 workload。
该已知调用者边界不是通用 hook 热卸载保证。不得强制卸载。

## 文件与验证入口

| 文件 | 用途 |
| --- | --- |
| `komb.c` | 上游排队、combiner、WWJUMP、unlock 和 shadow 栈管理 |
| `context.S` | 六寄存器保存/恢复和物理栈切换 |
| `provider.c` / `compat.h` | 实验 hook、目标锁身份、preemption 与只读计数 |
| `upstream/` / `UPSTREAM.json` / `port.patch` | 不变来源及可审核移植差异 |

真实汇编的基础验证为
[`tests/unit/spin/test_tclock_context.py`](../tests/unit/spin/test_tclock_context.py)。
三方运行方法、实际执行结果和性能解释维护在
[`bench/tclock_compare/`](../bench/tclock_compare/README.md)。
已完成的[三方实测](../bench/tclock_compare/results/20260918-native-stack.md)覆盖
180 场稳态会话；保存/恢复对照、实际代理比例、独立采样及 kdlock 并发冷晋升
失败均在该页记录。真实汇编单元验证六个寄存器、RSP 和 lock/unlock 续点，
不能据此宣称任意内核栈展开或复杂临界区已通过。
与 kdlock 的入口、L/S 协议、逐请求处理及收益抵消见
[执行路径对照](../bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)。
