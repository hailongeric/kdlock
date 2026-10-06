# TCLock spin and mutex backends

本目录提供独立的 x86_64 TCLock spin/mutex 外部模块。workload 显式调用
`komb_spin_lock/unlock` 或 `komb_mutex_lock/unlock`；同一目标锁的所有参与者
必须使用对应 TCLock 协议。provider 不安装全局 hook，`target_lock` 仅供计时外
绑定、排空诊断及退出前清除，不在 lock/unlock 热路径筛选。

六后端所有权比较统一见 [锁协议](../docs/design/lock_protocols.md)。对象、栈切换、
NUMA 选择、完成通知及源码路径分别见 [spin 实现](../docs/design/spin_implementation.md)
和 [mutex 实现](../docs/design/mutex_implementation.md)。本页只维护来源、构建及使用边界。

## 固定来源

来源为 [TCLocks](https://github.com/rs3lab/TCLocks) 提交
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef` 的 `src/kernel/rcuht/` 子树。
`upstream/` 保留六个未修改文件，`UPSTREAM.json` 记录 SHA256，`port.patch`
维护这六文件相对当前移植的差异。compat/provider 是独立适配文件，通过本仓库
Git 审查，不包含在该六文件 diff 中。保留上游 GPL-2.0 及作者声明；diff 用于
来源审查，不是直接应用到另一内核的安装补丁。

| 文件 | 职责 |
| --- | --- |
| [komb.c](komb.c)、[include/spinlock/komb.h](include/spinlock/komb.h) | Spin CAS/pending、节点队列、combiner、WWJUMP 和 unlock |
| [komb_mutex.c](komb_mutex.c)、[include/mutex/komb_mutex.h](include/mutex/komb_mutex.h) | 普通 mutex 队列、parking/wakeup、NUMA 和独立获取 trampoline |
| [combiner.c](combiner.c)、[include/lib/combiner.h](include/lib/combiner.h) | 六个 callee-saved GPR/RSP 交接与共用定义 |
| [provider.c](provider.c)、[compat.h](compat.h) | Spin 生命周期、初始化失败回收、诊断绑定和排空 |
| [mutex_provider.c](mutex_provider.c)、[mutex_compat.h](mutex_compat.h) | Mutex per-CPU context/栈预留、固定亲和 worker 注册、task refs、cohort 排空 |
| [upstream](upstream/)、[UPSTREAM.json](UPSTREAM.json)、[port.patch](port.patch) | 固定来源及可审核差异 |

## 构建与使用

仅在已核验的 recovery guest 构建/执行，遵守 [操作手册](../docs/AGENTS.md)。
两个模块独立选择，不能把 spin backend 当作 mutex arm：

```sh
# Guest only; runner normally builds isolated copies and matching Module.symvers.
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_MUTEX=1 TCLOCK_NUMA=1
```

输出分别为 `tclock_backend_km.ko` 与 `tclock_mutex_backend_km.ko`。
三方操作、ELF/ABI 审计和测量命令见 [运行器](../bench/tclock_compare/README.md)。
独立模块先加载 backend 再加载依赖它的 workload；退出全部 worker，检查
`quiescent=1`，清除诊断 `target_lock`，先卸载 workload 再卸载 backend。
不强制卸载。空闲快照不能替代外部停止新调用的边界。

## Spin 端口边界

Spin 调用者配对管理抢占；排队等待纯轮询，不使用显式 schedule/cond_resched。
当前 comparator 关闭 `ENABLE_IRQS_CHECK`，只接受 IRQ 开启的 task-context
单锁负载，不提供通用 IRQ/BH、trylock 混用或任意嵌套保证。
保留上游六 GPR 保存顺序、真实 RSP/CALL 续点、WWJUMP、NUMA 暂存链与
六条 caller 栈预取；不切换硬件 `current`、GS 或 per-CPU 身份。
批次不因 `need_resched()` 截断。配置值 1024 的 WWJUMP 从零计数，普通路径
可执行 1025 个正文，不等于 KD 的精确 1024 上限。

运行器显式传 `TCLOCK_NUMA=1`。虽然 Makefile 变量默认 0，当前共用
`include/lib/combiner.h` 直接定义 `NUMA_AWARE 1`，传 0 不能关闭该分支；
两个模块均包含该共用头；实际 ELF 的 `spin_numa` / `mutex_numa` 元数据用于
拒绝错误 off 标签。KD-only NUMA 消融
不意味着本端口支持匹配的 off 对照。上游内联换栈的 objtool 告警保留，
加载前审查实际机器码的寄存器与续点；没有独立 `context.S` 替代实现。
Spin 未增加实际代理计数，业务/排空通过不能给出委托比例。

## 普通 mutex 端口边界

Mutex 是实际上游普通 mutex 算法，保留 scheduling、parking/wakeup、NUMA 与
真实 waiter 栈切换；未移植无实现的 interruptible/killable/IO 或 rwsem 接口。
上游自定义 task 字段由预分配 `tc_mutex_context` 替代。每个固定单 CPU worker
在测量前注册，一个 CPU 只接收一个 worker；普通操作内部管理抢占。
context 和 task refs 必须覆盖整个 cohort 的退出与队列/栈排空。仍存活的退出
线程令 drain 返回 EBUSY，客户端计时外重试，不提前释放引用。

`parks` 是成功 parking 转换次数，`batches/delegated` 在 combiner batch 返回后
累计一次。排空后的全场差值可证明委托，不是 300 ms 峰值窗口的专属占比。
KD published mutex waiter 保持 pinned polling；TCLock 的 parking 不是 KD 当前策略。
固定亲和端口的验证不能扩展为任意 oversubscription 或通用 task-field 替代。

## 与 KD / Native 的关系和验证

TCLock spin 与 Linux qspinlock 即使锁字形状相同，也解码不同节点池；同一锁
不能混用。TCLock mutex 是 `komb_mutex`，不是原 Linux `struct mutex`。
KD spin 同样使用独立 KD 单字协议；KD mutex 则保留原 Linux mutex 和物理
owner，shadow gate 仅调度。旧文档将 KD spin 也描述成 Linux L + 私有 S 的
说法仅适用于历史 spin 版本，不能套到当前代码。

本后端和三种 workload 关闭模块 UBSAN。KD 私有 benchmark provider 默认
UBSAN off，显式 `kernel` 继承内核配置；内核运行配置保持不变。
实际换栈定向检查为 [spin context](../tests/unit/spin/test_tclock_context.py) 和
[mutex context/parking](../tests/unit/mutex/test_tclock_mutex_context.py)；这些
fixture 不替代 live scheduling/ownership 验证。当前三方结果与失败候选只在
[报告索引](../bench/tclock_compare/README.md#本次结果)维护，旧成绩通过
[历史索引](../bench/tclock_compare/results/HISTORY.md)追溯，不代表本次重跑。
