# Cacheline / RCUHT 临界区模块

| 文件 | 职责 |
| --- | --- |
| [api.h](api.h) | 布局、计数、批量 RUN 的 ioctl ABI，与客户端共享 |
| [payload.h](payload.h) | 对齐的原锁/数据，以及五种规模的固定展开正文 |
| [hash_payload.h](hash_payload.h) | 上游哈希表写入逻辑、预分配节点和计时外完整性检查 |
| [direct.h](direct.h) | 编译期选择三种直接锁 API；kdlock 保留必要 clobber 调用现场 |
| [post_work.h](post_work.h) | 正文返回后的 4 组寄存器乘加，给下一次申请留出短间隔 |
| [module.c](module.c) | 原子准入门、排空快照、一次 ioctl 的完整循环与设备注册 |

所有线程争用同一把 spinlock。默认 cacheline 正文只读改写有效槽中的 64 位计数器，循环中
不计时、不主动调度、不添加等待；每次正文返回后，在锁外执行相同的 4 组局部
乘加。结果没有业务用途，用 volatile asm 保留，不能保证公平交接；原子控制门
在循环外。`SC_BACKEND=native|tclock|kdlock` 选择直接后端；后两种构建
通过后端 `Module.symvers` 链接，需先加载后端。原生组无后端符号依赖。
三种 `SC_BACKEND` 直接对比构建均以 `UBSAN_SANITIZE := n` 关闭模块插桩，
不指定 `SC_BACKEND` 的普通测试构建仍继承内核配置；运行内核本身没有改动。
`SC_PREPARE` 在模块加载后、计时前显式登记选定入口；`SC_RUN` 不进行登记。
各批次核对 IRQ/preempt 状态，三种后端保持相同检查。直接三方运行见
[bench/tclock_compare](../../bench/tclock_compare/README.md)。运行方法、临界区伪代码和性能结果统一维护在
[bench/spin_cacheline/README.md](../../bench/spin_cacheline/README.md)。

`SC_WORKLOAD=rcuht` 构建哈希表正文，`SC_PREPARE`/`SC_RUN` 使用内部编号 0。
哈希表循环同样不主动调度，原 `hash_resched` 参数已删除。
当前三种后端统一用 `__hlist_del()` 摘链后立即重新插入，省去中间两次
`LIST_POISON` 写入；搬移计数在修改节点之前、同一锁内更新。操作结果和
链表终态与原写法一致，但指令序列有别于上游的 `hlist_del()`。等价性测试
见 `tests/unit/spin/test_hash_relink.py`，实际 JIT 和性能仍由 guest 样例验收。
桶/节点参数、随机键、统计口径和运行方式统一见
[哈希表三方对比](../../bench/tclock_compare/README.md#本次结果)。layout ABI 为 v2；
哈希表模式的 SC_COUNTS 成功返回前会验证完整表结构，并返回累计操作分类。
