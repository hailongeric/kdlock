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
   活跃 caller-clobbered 值。`kd_spin_lock_abi` 记录本地热度并检查上下文和入口。
3. 快速路径获取 KD 字并保留 pinned fast owner。竞争路径使用同一个字的
   pending/tail 排队，稳定 ticket 记录 task/CPU/generation。无法代理时以 KD
   全字 CAS 自执行，尊重 pending/tail，不回退到 Linux 锁操作。
4. waiter 使用预分配节点和稳定 request/frame；节点链接可复用不代表 frame 可退休。
   等待栈、PAUSE 轮询和 caller-clobber ABI 保留。combiner 绑定逻辑 waiter，
   通过 wrapper 和生成代码执行正文，原 waiter/combiner 共用寄存器包。
5. 嵌套控制 CALL 维护锁记录和独立所有权。提前释放、乱序解锁、远端借用 ACK
   与重新获取不能重复释放 KD 字；ticket 元数据退休与唯一 release store 分开。
6. 正常 COMPLETE 回交 IP/SP/BP；中途 FULL 物化完整逻辑 GPR。已执行的正文
   不重跑，只有已支持的 CALL/PENDING 边界可受检续跑。原生 owner 最终 ACK
   后才可解除相应依赖，frame 的最后使用者结束后释放来源 pin。

具体布局与指令约定见 [ABI](JIT_REGISTER_ABI.md)，队列/所有权见
[locking](design/locking.md)，frame 和受检续跑见 [frames](design/frames.md)。
mutex 保留自己的原 mutex、调度 gate、task 记录与 native owner/ACK 协议，
本次只迁移本地热度发现和准入，没有改写其互斥算法。

### 2.1 热度与角色

spin/mutex 每 CPU 独立 16 桶、6 候选，用完整地址与槽索引链表查找。
满表 miss 才扫描六个分数，先摘旧链再替换；`score-error` 是保守有效计数。
默认 adaptive 按 CPU 速率和候选 lower-bound 阈值准入，observe 固定准入并记录。
查询仅反映本 CPU 实际热度；observe 的固定准入由 record 返回。
临时统计 pin 在返回前解除，mutex 不跨睡眠持有统计 pin；重入只丢弃统计样本。

OWNER 保存在稳定 fast owner/ticket 状态中，WAITER/COMBINER/DONE 位于 frame。
角色和所有权不依赖候选是否仍在表中。SELFTEST 可输出按锁地址关联的角色，
普通构建不逐请求打印。最终统计仅在 provider 排空后输出，不能倒推全程状态。

## 3. 验证选择与判定

[tests](../tests/README.md)是当前测试选择的唯一入口。旧全局 hook 场景及对应的
运行命令已删除，其历史通过不构成当前接受标准。保留的日志 oracle 只验证证据
字段关系，生产 C fixture 只覆盖替代原语下的状态转移，均不能替代真实 JIT。

当前直接运行器验证发布条目、冻结镜像、真实正文、业务数据、IRQ/preempt、队列
与退休。`nested` 检查 A→B→释放 B→释放 A；`early` 检查持 B 提前释放 A。
这两项本地双锁证据不能推广为所有远端 native/JIT 组合已验证。

SELFTEST 的持锁淘汰、mutex CPU 迁移和 entry ACK 是独立 JIT=0 证据。
模块加载/卸载检查也不执行 JIT。性能有效、实际 JIT、原生/拒绝及失败记录分开报告，
没有正文的竞争 observe 场次不得算通过。环境、快照和卸载约束见
[AGENTS](AGENTS.md)。
