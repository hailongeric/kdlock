# 内核 provider 代码地图

当前 KD spin API 按普通 `raw_spin_lock` 语义：获取/解锁配对抢占，保持 IRQ/BH 状态，
代理慢路径和嵌套队列不再保存 IRQ flags 或整段关 IRQ。最终完成先退休 ticket 元数据，
读完并回收 continuation 后才解除原入口 pin；普通重试和有锁 native 续跑保留 pin。
本次未新增 irqsave/bh API；需要这些语义的调用者在外层处理。

spin 已按性能回退结果恢复入口热度/上下文判断及批量时钟；`nondelegated.inc` 提供完整原生 fast/pending/MCS，虚拟排队继续服务父 ACK。顶层 pending 免 ticket、合并 ticket guard 和 continuation 退休协议保留。详见 [当前锁协议](../docs/design/locking.md)。

当前 spin 统一分发已删除；`kd_main.c` 保留停用的 mutex hook 安装和撤销入口。直接入口位于 `kd_spinlock.c`，
调用者使用 `include/kd_spin_direct.h` 的 clobber-v1 现场约定，并在计时前调用
`kd_spin_prepare` 登记入口。公开 unlock 处理单锁字快速 owner、ticket 和 native ACK；
内部 shadow/frame 解锁保留为 `kd_spin_unlock_protocol`。保留的 mutex hook 路由当前未安装。
KD 锁字、稳定持锁记录、逻辑 frame 和来源 pin 各自承担不同职责。

默认构建要求 `kdclobber2` 的 `KD_SPIN_CLOBBER_V1` 和 `KD_MUTEX_CLOBBER_V1` 接口；缺失时编译直接报错，
不再自动降为旧内核 hook。普通 spin/mutex 使用各自 clobber 身份；同一内核上的旧 ABI 调用者
仍通过兼容 dispatcher 执行，嵌套和原生续跑需要的 FULL 状态也继续保留。
普通 mutex 的 MINIMAL/COMPLETE 借用 node 寄存器包，正常完成仅恢复 IP/SP/BP；
首次 FULL 出口为 owner ACK 的独立生命周期取得 frame 自有包。
实现约束见 [ABI 文档](../docs/JIT_REGISTER_ABI.md#mutex-clobber-assessment)。
mutex node 同时删除无消费者的 socket/IRQ 字段和合并通知别名，重新排列为
256 字节、64 字节对齐；next 与 completed/locked 分行，避免缩减字段后
引入相邻 node 共行。生产构建对大小、对齐和通知偏移做静态检查。

| 编译入口 | 保留职责 |
| --- | --- |
| [kd_main.c](kd_main.c) | 模块初始化、hook 安装/撤销、目标选择 |
| [kd_lock.c](kd_lock.c) | hook 路由、原生快路径、mutex shadow 查询 |
| [kd_spinlock.c](kd_spinlock.c) | spin 公共 lock/unlock、保存现场与返回汇编 |
| [kd_mutex.c](kd_mutex.c) | mutex 公共入口、栈切换与 owner 返回 |
| [exe.c](exe.c) | wrapper 返回包的高层执行循环 |
| [kd_exec.c](kd_exec.c) | frame 栈、上下文验证和状态事件 |
| [sys.c](sys.c) | `/dev/kd_dev` 的读取、上传、状态与 retire ioctl |
| [kd_source.c](kd_source.c) | 来源状态和 module/frame/writer pins |
| [kd_hotlock.c](kd_hotlock.c) | 每 CPU 分类型精确地址哈希计数与定时热值准入；入口注册由 `kd_lock.c` 调用执行注册表 |
| [kd_spin_entry.c](kd_spin_entry.c) | 路由准入、ticket/origin 与 native 状态 |
| [kd_mutex_tasks.c](kd_mutex_tasks.c) | mutex 在途任务/持锁记录，名称变化后的 owner 路由 |

不代理的 KD 请求同样使用 fast/pending/MCS 队列：复用每 CPU 四个节点，在本地
通知字段等待，不分配 request/frame，不切换栈。不可代理节点终止当前 combiner
批次，再由原调用者执行。`spin_delegate=0` 为显式不代理对照，默认仍为 1。

旧统一 spin 分发及 `spin_native_cache` 已删除；显式直接 API 保留现有
快速所有权、ticket、frame 和 ACK 路径。mutex 的目标进程选择仍保留。

`spin_prefetch=0/1/2` 是只读装载参数，分别关闭后继请求预取、保留 combiner
查询地址的旧策略、使用发布前准备的地址提示（默认）。它不关闭其他既有队列
返回处的栈预取。新提示只用于缓存预热，不替代寄存器包、准入或 owner/ACK；
节点为 128 字节，next 与通知字分行，continuation 继续独立存活。约束见 [DESIGN](../docs/design/frames.md#911-reuse-before-copy-contract)。

热锁使用每 CPU/type 256 桶、256 条精确地址记录，冲突按完整地址匹配，
直接增加该锁 count，无候选分数或淘汰。初始化 `alloc_percpu` 每 CPU 13376 字节，
entry/table/cpu 为 24/6688/13376 字节，CPU 对齐 64；锁路径不分配。
spin CPU 每 32 次实际 MCS 入队检查 400 亿 TSC 窗口，fast/pending 不计数；
mutex CPU 保持每 1024 次入口调用检查。入口读缓存 CPU 热值，CPU 热才查表；单锁 count 大于 1024
（第 1025 次）时检查 25 亿 TSC 窗口、刷新 hot、更新时间并清零计数。
CPU 冷却/重新变热重置计数/热值但保留映射，mutex 同次到期共享 TSC；
spin CPU/单锁在各自事件中采时。query 只读缓存，CPU 新热值由后续入口使用。
默认 adaptive 在表满时令未记录的新锁走原生；observe 固定准入。
OWNER/ticket/frame 不依赖热表，解锁不查表；有效地址与初始化/排空由调用者保证。
SELFTEST 的 `hotlock_lifetime_selftest=1 hotlock_mode=observe` 验证表满不覆盖
真实持锁记录及 mutex 等待迁移；`hotlock_role_trace=1` 输出角色，正常运行关闭。

顶层 fast/pending 自执行共用 fast owner，只有进入 MCS 分支才 reserve ticket；
嵌套调用仍先 reserve。队首正常返回已 claim/reclaim，入口不再重复确认；
claim/reclaim 与 release 各用一次 guard 完成校验和状态提交。物理释放、
代际及 native 借用退休约束见 [locking](../docs/design/locking.md#41-native-lock-and-private-queue)。

普通请求的诊断引用由入队保存、退出复用，批次也只解析一次诊断 slot；
共享 waiter 计数与身份/禁用状态分离到不同缓存行。continuation 按 64 字节对齐，
普通准入元数据位于前两条缓存行。普通批次只在最终准入处检查 readiness，
正常完成合并终态验证和解绑；复杂处理仍使用原协议。

spin 初始化按 possible CPU 一次 `vzalloc(20 KiB)`，低端 12 KiB 放最多 12 条
704 字节 continuation，高端 8 KiB 为物理 waiter 等待栈。节点直接指向记录；
只有所属 CPU 分配/收缩 top，远端执行者 pop 后仅发布退休。父子共享根寄存器包，
不维护 request users/packet_owner。普通完成先 pop 再通知；native 包括无锁 relay
在唤醒前借用根 ticket，清理/pop 后解除，原线程最后解锁等待所有执行者退休。
最终恢复汇编读完现场后才回收根记录。完整对象表与数据流见
[EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。

## 私有实现组件

下表按所属编译单元和原声明顺序列出组件；文件头说明用途和依赖。
`spin/execute.inc` 内的 `execute_cs` 处理复杂委托出口，
`spin/combiner.inc` 的 `run_combiner` 组织批次；
`kd_spin_batch_run` 在同一个 C 帧中处理新、旧及混合 ABI，编译器保护跨 wrapper
活跃值。调用边界见 [kd_jit_batch.h](../include/kd_jit_batch.h)；旧汇编外壳仅留在
[兼容测试夹具](../tests/unit/spin/legacy_batch.S)，不参与生产构建。
新 ABI 的普通 root 正常路径只捕获/回写/恢复 RIP/RSP/RBP，中途出口在进入 C
前物化完整逻辑 GPR；旧 ABI 与 FULL 续跑保留完整恢复规则。
`spin/slowpath.inc` 管理队首等待与恢复，`spin/wait.inc` 保持 IRQ 状态，先切到
每 CPU 20 KiB 区域高端的 8 KiB shadow 等待栈，再发布普通 waiter 并轮询。
spin combiner 和虚拟 waiter 的 owner/ACK 服务使用执行者 task 内核栈；
`kd_spin_cpu_state` 保存 CPU 锁账本、节点预留深度和等待栈指针；
嵌套 JIT 的 requester/depth 内嵌于稳定 continuation。旧 wrapper RSP 暂存已删除。
`execution/native.inc` 保留 physical owner，最终 unlock 由该 owner 服务并 ACK，
原线程还须等待所有 native 执行者清理/pop 后解除借用。

| 所属入口 | 组件 | 职责 |
| --- | --- | --- |
| `kd_spinlock.c` | [spin/state.inc](spin/state.inc) | Original-lock identity, per-CPU nodes, shadow state and observer declarations. |
| `kd_spinlock.c` | [spin/shadow.inc](spin/shadow.inc) | Nested lock-vector push/pop, saved combiner state and invariant checks. |
| `kd_spinlock.c` | [spin/diagnostics.inc](spin/diagnostics.inc) | Per-lock diagnostic counters, waiter observations and JIT-disable latch. |
| `kd_spinlock.c` | [spin/queue.inc](spin/queue.inc) | Tail encoding, node publication and optional NUMA successor selection. |
| `kd_spinlock.c` | [spin/nondelegated.inc](spin/nondelegated.inc) | 共用锁字和节点的原生 pending/MCS 获取，不申请 JIT 执行状态。 |
| `kd_spinlock.c` | [spin/request.inc](spin/request.inc) | CPU-local continuation top reservation and contiguous retired-top collapse; remote retirement never changes the owning CPU top. |
| `kd_spinlock.c` | [spin/prefetch.inc](spin/prefetch.inc) | Producer-prepared queue hints and off/consumer/prepared successor-prefetch policies. |
| `kd_spinlock.c` | [spin/combiner.inc](spin/combiner.inc) | 批内查找、outer release、统一 clobber 批次及队列交接。 |
| `kd_spinlock.c` | [spin/execute.inc](spin/execute.inc) | 复杂出口的 frame 绑定、dispatcher 调用、native/remote 处理；在 combiner 的原声明位置包含。 |
| `kd_spinlock.c` | [spin/wait.inc](spin/wait.inc) | IRQ-off physical shadow-stack switch before publication/polling; head RSP restoration or direct completed/native packet restoration. |
| `kd_spinlock.c` | [spin/slowpath.inc](spin/slowpath.inc) | Queue-head waiting, nested combiner restoration and native node admission. |
| `kd_spinlock.c` | [spin/lifecycle.inc](spin/lifecycle.inc) | Per-CPU allocation, partial-init rollback and drained shutdown reporting. |
| `kd_spinlock.c` | [spin/nested.inc](spin/nested.inc) | Virtual nested waiters, remote completion and out-of-order unlock results. |
| `exe.c` | [execution/hostcalls.inc](execution/hostcalls.inc) | Allowlisted native services and bounded mutex CALL stack observations. |
| `exe.c` | [execution/timing.inc](execution/timing.inc) | Optional inclusive boundary timing; disabled runs take no clock samples. |
| `exe.c` | [execution/registry_lifecycle.inc](execution/registry_lifecycle.inc) | 有界代码池与条目查找；execute_cs 传递就绪条目，dispatcher 不再查表，但重新核对发布状态和 source 准入。 |
| `exe.c` | [execution/wrapper_entry.inc](execution/wrapper_entry.inc) | wrapper 范围/镜像/ABI 核对、正文证据及批次准入；不读取 MINIMAL 未捕获的 GPR。 |
| `exe.c` | [execution/control_calls.inc](execution/control_calls.inc) | Known spin/mutex CALL handling, continuation advancement and stack checks. |
| `exe.c` | [execution/registry_publish.inc](execution/registry_publish.inc) | 已发布、同身份/后端且 source OPEN 的重复注册只读返回；新注册、冲突和退休保留串行化。注册不等于 JIT 就绪或正文执行。 |
| `kd_exec.c` | [execution/frame_lifecycle.inc](execution/frame_lifecycle.inc) | frame prepare/bind/push/pop、普通完成及退休，保留有效范围和最后使用者约束。 |
| `kd_exec.c` | [execution/remote.inc](execution/remote.inc) | Remote owner messages and ACKs; spin completion detaches and pops before publishing parent DONE. |
| `kd_exec.c` | [execution/native.inc](execution/native.inc) | NATIVE_READY routing, physical-owner ACKs and final spin root-ticket retirement wait. |
| `kd_exec.c` | [execution/lock_ledger.inc](execution/lock_ledger.inc) | Frame lock-vector mutations and completion predicates; this never acquires L. |
| `kd_mutex.c` | [mutex/queue.inc](mutex/queue.inc) | Per-CPU slot reservation, native mutex acquisition and private tail helpers. |
| `kd_mutex.c` | [mutex/combiner.inc](mutex/combiner.inc) | Delegated mutex bodies, detached outer batches and successor publication. |
| `kd_mutex.c` | [mutex/waiter.inc](mutex/waiter.inc) | Queue waiting and nested native acquisition; preserve owner/ACK semantics. |
| `kd_mutex.c` | [mutex/clobber.inc](mutex/clobber.inc) | 发布前切栈，完成后放弃旧 C 帧，按 COMPLETE/FULL 恢复。 |
| `kd_mutex.c` | [mutex/lifecycle.inc](mutex/lifecycle.inc) | Gate initialization, per-CPU stack allocation, rollback and drained teardown. |
| `kd_lock.c` | [lock/mutex_calls.inc](lock/mutex_calls.inc) | Mutex hook ownership and nested CALL admission/cleanup against real owners. |
| `kd_lock.c` | [lock/spin_calls.inc](lock/spin_calls.inc) | Nested spin CALL routing, private tickets, out-of-order release and cleanup. |

## 编译边界

`.inc` 是仅由所属 `.c` 包含的私有 C 实现，不单独生成 `.o`。保留一个编译
单元以维持 static 状态、声明顺序、内联决策、GCC 属性和栈切换汇编标签，
不增加跨对象调用或公开内部符号。Kbuild 自动跟踪 include 依赖；不要把
`.inc` 加入 `kdlock_km-objs`。跨单元接口见 [include/README.md](../include/README.md)。

自测观察仍在 `tests/kernel/`，benchmark 观察仍在 `bench/spin_cacheline/provider/`，
不会混入普通 provider。源码冻结和 provider 副本必须包含 `.inc`。
构建与实际验证只在 recovery guest 执行，入口见 [tests/README.md](../tests/README.md)。
