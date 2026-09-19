# 内核 provider 代码地图

先读 `kd_main.c` 的 hook 安装，再读 `kd_lock.c` 的路由，随后进入对应后端。
原生锁、私有队列、逻辑 frame 和来源 pin 各自承担不同职责。

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
| [kd_hotlock.c](kd_hotlock.c) | 按锁地址统计频率并决定晋升；入口注册由 `kd_lock.c` 调用执行注册表 |
| [kd_spin_gate.c](kd_spin_gate.c) | 私有 gate、真实 owner 与原锁引用；`origin` release/acquire 发布，已有条目无锁查找，创建仍串行化 |
| [kd_spin_entry.c](kd_spin_entry.c) | 路由准入、ticket/origin 与 native 状态 |
| [kd_mutex_tasks.c](kd_mutex_tasks.c) | mutex 在途任务/持锁记录，名称变化后的 owner 路由 |

普通 spin 的 `spin_native_cache` 装载参数默认开启；设为 `0` 可关闭原生站点
缓存做对照，会话中不可切换。使用内核 `bint` 解析，sysfs 读回 `0/1`。
缓存 miss 后 root 先尝试私有 S，竞争后才分配 ticket；
成功的 S/L root 保留独立 physical hold。缓存键不变时不重复查询翻译表回填。
具体锁与生命周期约束见 [DESIGN 4.1](../docs/DESIGN.md#41-native-lock-and-private-queue)，
实测取舍见 [入口对照](../bench/spin_cacheline/results/20260918-spin-entry.md)。

`spin_prefetch=0/1/2` 是只读装载参数，分别关闭后继请求预取、保留 combiner
查询地址的旧策略、使用发布前准备的地址提示（默认）。它不关闭其他既有队列
返回处的栈预取。新提示只用于缓存预热，不替代寄存器包、准入或 owner/ACK；
节点为 64 字节，request 继续独立存活。约束见 [DESIGN](../docs/DESIGN.md#911-reuse-before-copy-contract)。

热锁检测仍使用 `INIT → CHECKING → DELEGATE/IGNORE` 和固定采样窗口。
普通 clobber 入口在已晋升后跳过 `kd_hotlock_record()`；IGNORE 仍会更新计数，
没有自动降级或按收益选择执行方式。现有行为见
[热锁检测](../docs/DESIGN.md#hotlock-monitoring)，改进属于[待办](../docs/TODO.md#hotlock-monitoring-and-adaptive-admission)。

普通请求的诊断引用由入队保存、退出复用，批次也只解析一次诊断 slot；
共享 waiter 计数与身份/禁用状态分离到不同缓存行。request 按 64 字节对齐，
普通准入元数据位于前两条缓存行。普通批次只在最终准入处检查 readiness，
正常完成合并终态验证和解绑；复杂处理仍使用原协议。

## 私有实现组件

下表按所属编译单元和原声明顺序列出组件；文件头说明用途和依赖。
`spin/combiner.inc` 内的 `execute_cs` 处理复杂委托出口，`run_combiner` 组织批次；
`kd_spin_batch_run` 在同一个 C 帧中处理新、旧及混合 ABI，编译器保护跨 wrapper
活跃值。调用边界见 [kd_jit_batch.h](../include/kd_jit_batch.h)；旧汇编外壳仅留在
[兼容测试夹具](../tests/unit/spin/legacy_batch.S)，不参与生产构建。
新 ABI 的普通 root 正常路径只捕获/回写/恢复 RIP/RSP/RBP，中途出口在进入 C
前物化完整逻辑 GPR；旧 ABI 和 mutex 保留原调用规则。
`spin/slowpath.inc` 管理队首等待与恢复，`spin/wait.inc` 在关 IRQ 后先切到
每 CPU 预分配的 8KB shadow 等待栈，再发布普通 waiter 并轮询。
spin combiner 和虚拟 waiter 的 owner/ACK 服务使用执行者 task 内核栈；
`shadow` 锁地址账本和 wrapper RSP 暂存仍是元数据。`execution/native.inc` 的原生续跑
保留 physical owner，最终 unlock 仍由该 owner 服务并 ACK。

| 所属入口 | 组件 | 职责 |
| --- | --- | --- |
| `kd_spinlock.c` | [spin/state.inc](spin/state.inc) | Original-lock identity, per-CPU nodes, shadow state and observer declarations. |
| `kd_spinlock.c` | [spin/shadow.inc](spin/shadow.inc) | Nested lock-vector push/pop, saved combiner state and invariant checks. |
| `kd_spinlock.c` | [spin/diagnostics.inc](spin/diagnostics.inc) | Per-lock diagnostic counters, waiter observations and JIT-disable latch. |
| `kd_spinlock.c` | [spin/queue.inc](spin/queue.inc) | Tail encoding, node publication and optional NUMA successor selection. |
| `kd_spinlock.c` | [spin/request.inc](spin/request.inc) | Preallocated shared request reservation and final-user release, including remote root-packet references. |
| `kd_spinlock.c` | [spin/prefetch.inc](spin/prefetch.inc) | Producer-prepared queue hints and off/consumer/prepared successor-prefetch policies. |
| `kd_spinlock.c` | [spin/combiner.inc](spin/combiner.inc) | Delegated body execution, outer release and bounded combiner batches. |
| `kd_spinlock.c` | [spin/wait.inc](spin/wait.inc) | IRQ-off physical shadow-stack switch before publication/polling; head RSP restoration or direct completed/native packet restoration. |
| `kd_spinlock.c` | [spin/slowpath.inc](spin/slowpath.inc) | Queue-head waiting, nested combiner restoration and native node admission. |
| `kd_spinlock.c` | [spin/lifecycle.inc](spin/lifecycle.inc) | Per-CPU allocation, partial-init rollback and drained shutdown reporting. |
| `kd_spinlock.c` | [spin/nested.inc](spin/nested.inc) | Virtual nested waiters, remote completion and out-of-order unlock results. |
| `exe.c` | [execution/hostcalls.inc](execution/hostcalls.inc) | Allowlisted native services and bounded mutex CALL stack observations. |
| `exe.c` | [execution/timing.inc](execution/timing.inc) | Optional inclusive boundary timing; disabled runs take no clock samples. |
| `exe.c` | [execution/registry_lifecycle.inc](execution/registry_lifecycle.inc) | 有界代码池与条目查找；execute_cs 传递就绪条目，dispatcher 不再查表，但重新核对发布状态和 source 准入。 |
| `exe.c` | [execution/control_calls.inc](execution/control_calls.inc) | Known spin/mutex CALL handling, continuation advancement and stack checks. |
| `exe.c` | [execution/registry_publish.inc](execution/registry_publish.inc) | 已发布、同身份/后端且 source OPEN 的重复注册只读返回；新注册、冲突和退休保留串行化。注册不等于 JIT 就绪或正文执行。 |
| `kd_exec.c` | [execution/remote.inc](execution/remote.inc) | Remote frame requests and release/acquire ACKs between physical executors. |
| `kd_exec.c` | [execution/native.inc](execution/native.inc) | Original-waiter native continuation and owner-serviced final unlock ACKs. |
| `kd_exec.c` | [execution/lock_ledger.inc](execution/lock_ledger.inc) | Frame lock-vector mutations and completion predicates; this never acquires L. |
| `kd_mutex.c` | [mutex/queue.inc](mutex/queue.inc) | Per-CPU slot reservation, native mutex acquisition and private tail helpers. |
| `kd_mutex.c` | [mutex/combiner.inc](mutex/combiner.inc) | Delegated mutex bodies, detached outer batches and successor publication. |
| `kd_mutex.c` | [mutex/waiter.inc](mutex/waiter.inc) | Queue waiting and nested native acquisition; preserve owner/ACK semantics. |
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
