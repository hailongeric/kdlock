# 当前 JIT 执行流

本页描述显式 KD spin API 及保留的执行引擎。全局 spin 分发已删除，mutex hook
安装仍停用；普通 Linux 锁调用不会因加载模块自动代理。运行步骤见
[PROJECT_GUIDE](PROJECT_GUIDE.md)，验证入口见 [tests](../tests/README.md)。

## 1. 准入范围

目标为 x86_64，要求匹配 kdclobber2 接口。KD、Linux、TCLock 对象使用各自协议。
翻译器保留现有 GS/逻辑 task、静态 per-CPU 范围、上下文敏感操作及 CALL 筛选；
细节见 [admission](design/admission.md)。访问时 guard 和不可变 JIT 版本仍未实现。
热度不等于安全准入，也不代表入口已经发布或正文已经执行。

## 2. 执行流

1. 调用者拥有 `kd_spinlock_t` 对象，并用 `kd_spin_prepare` 登记锁后续点及 ABI。
   daemon 经设备取得登记条目，读取内核正文、翻译、组装、上传并发布 NORMAL。
   直接 benchmark 在单 CPU 预热前完成准备，测量时停止 daemon。
2. clobber v1 调用保存 pre-CALL RSP、post-CALL RIP 和 caller RBP，编译器保存
   活跃 caller-clobbered 值。`kd_spin_lock_abi` 首先关闭抢占，代理开启时合并记录/
   判断热度并筛选上下文，再尝试 fast/pending；统计和原生回退复用已有 pin。
   关闭代理时公共入口跳过统计，直接走完整原生获取。
3. 快速路径获取 KD 字并保留 pinned fast owner。竞争路径使用同一个字的
   pending/tail 排队，普通根仅在 queue 分支占 ticket，再检查翻译就绪。拒绝走
   完整 KD 原生 fast/pending/MCS，已有 ticket 保留，节点不带 continuation/frame；发布后的拒绝或续跑仍须
   完成既有 continuation 生命周期。只有真正节点耗尽才轮询锁字，不回退到 Linux
   锁操作。对象大小、分配位置及与 TCLock 的数据流对照见
   [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。
4. 每 CPU 预分配 20 KiB：低端 12 KiB 为最多 12 条 continuation，高端 8 KiB
   为 waiter 等待栈；记录按栈顶占用，退休后只收缩连续已退休的栈顶。
   节点直接指向 continuation/frame，节点复用不会销毁现场。
   等待栈、PAUSE 轮询和 caller-clobber ABI 保留。combiner 绑定逻辑 waiter，
   通过 wrapper 和生成代码执行正文，原 waiter/combiner 共用寄存器包。
5. 嵌套控制 CALL 维护锁记录和独立所有权。提前释放、乱序解锁、远端借用 ACK
   与重新获取不能重复释放 KD 字；ticket 元数据退休与唯一 release store 分开。
6. 正常 COMPLETE 回交 IP/SP/BP；中途 FULL 物化完整逻辑 GPR。已执行的正文
   不重跑，只有已支持的 CALL/PENDING 边界可受检续跑。普通完成必须先 pop 子 frame 再发布完成。
   NATIVE_READY 与最终退休分开：所有 native 执行者（含无锁 relay）先借用根
   ticket，清理/pop 后解除借用；最终解锁等待借用清空，才回收现场及解除抢占。
   无剩余锁的续跑在恢复前等退休；恢复汇编读完全部现场后才回收根记录。

具体布局与指令约定见 [ABI](JIT_REGISTER_ABI.md)，队列/所有权见
[locking](design/locking.md)，frame 和受检续跑见 [frames](design/frames.md)。
mutex 保留自己的原 mutex、调度 gate、task 记录与 native owner/ACK 协议，
本次只迁移本地热度发现和准入，没有改写其互斥算法。

### 2.1 热度与角色

spin/mutex 每 CPU 独立 256 桶、256 条预分配记录，哈希冲突用完整地址和槽索引
链表区分。没有候选/分数/淘汰，命中只给该锁 count 加一；满表不覆盖已有记录。
初始化建立 CPU 时间；CPU/type 每 1024 次检查 400 亿 TSC 窗口，热 CPU 才查表。
单锁 count 大于 1024（第 1025 次）才检查 25 亿 TSC 窗口并更新 hot/时间、清零计数。
同次到期共享采时，CPU 持续热保留单锁批次，冷却/重新变热清零计数/热值但保留映射。
adaptive 要求 CPU/锁缓存热值同时成立，未收录且表满的锁走原生；observe 固定准入。
query 不计数/采时/插入；有效地址及表生命周期由调用者保证，关闭代理时不记录。
虚拟嵌套先按热值分流；热路径占独立 ticket 后 CAS/排队，冷路径走原生 bridge。
已发布的虚拟等待继续服务父 frame 的远端 ACK。MCS 后置准入和逐次时间检查
已因竞争性能回退撤回，见 [调查](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)。
统计复用调用者已有的抢占保护；仅尚未关闭抢占的独立调用临时 pin 并在返回前
解除。mutex 不跨睡眠持有统计 pin；重入只丢弃统计样本。

OWNER 保存在稳定 fast owner/ticket 状态中，WAITER/COMBINER/DONE 位于 frame。
角色和所有权不依赖热表是否有空槽或锁的热值。SELFTEST 可输出按锁地址关联的角色，
普通构建不逐请求打印。最终统计仅在 provider 排空后输出，不能倒推全程状态。

## 3. 验证选择与判定

[tests](../tests/README.md)是当前测试选择的唯一入口。旧全局 hook 场景及对应的
运行命令已删除，其历史通过不构成当前接受标准。保留的日志 oracle 只验证证据
字段关系，生产 C fixture 只覆盖替代原语下的状态转移，均不能替代真实 JIT。

当前直接运行器验证发布条目、冻结镜像、真实正文、业务数据、IRQ/preempt、队列
与退休。`nested` 检查 A→B→释放 B→释放 A；`early` 检查持 B 提前释放 A。
这两项本地双锁证据不能推广为所有远端 native/JIT 组合已验证。

SELFTEST 的满表持锁记录保留、mutex CPU 迁移和 entry ACK 是独立 JIT=0 证据。
模块加载/卸载检查也不执行 JIT。性能有效、实际 JIT、原生/拒绝及失败记录分开报告，
没有正文的竞争 observe 场次不得算通过。环境、快照和卸载约束见
[AGENTS](AGENTS.md)。
