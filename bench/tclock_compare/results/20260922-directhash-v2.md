# 2026-09-22：分类型热表改用直接映射槽

> 已撤回：用户因性能下降要求恢复 `bf16b10` 的256桶/256记录实现。下文保留该实验当时的结果；[恢复后的验证](20260922-directhash-v2-rollback.md)单独记录。

按用户再次提出的直接索引要求，在 `bf16b10` 上只改变热表存储与相应验证：
每 CPU 的 spin/mutex 表各从 256 条精确地址链记录改为 512 个直接映射槽。
类型隔离、busy 门、已有 pin 复用、CPU1024/锁1025阈值和时钟窗口保持不变。
不恢复前次共享类型表或删除 busy/pin 检查的实验；前次回退性能不算本版成绩。

一次 hash 定位 `entries[hash_long(address, 9)]`。地址一致直接计数；地址不同则
替换地址、清零旧 count/hot，并借用最近 CPU 时间起点，再把本次访问计为 1。
没有 buckets、next、used、冲突链遍历、空闲槽查找或容量拒绝。query 不替换、
不计数、不采时，地址不符返回冷；反复碰撞可使双方始终无法晋升，adaptive 保持原生。
observe 仍是显式的固定准入诊断模式，不用它证明自适应热度已成立。

记录24 B、类型表12312 B、每CPU对象24640 B并按64 B对齐。初始化一次
`alloc_percpu`，运行时不分配。当前guest内核 `mm/percpu.c` 限制单次分配最多
32 KiB；每类型1024槽会使两表合计49216 B超限，因此选每类型512槽。
CPU冷热切换时扫描512槽重置统计；不再有只遍历used记录的捷径。

替换仅丢弃统计，不能退休已有ticket、frame或改变物理owner；解锁不查热表。
当前流程图、对象和数据流见[执行路径](../../spin_cacheline/EXECUTION_PATHS.md)。

## 验证

仅在 recovery guest `6.1.159-kdclobber2` 构建执行，未修改内核或TCLock。
基础2项及hotlock sampling、spin preempt共4/4驱动通过，14个错误变体全部检出。
覆盖512槽、同槽交替碰撞、旧计数/热度/时间不继承、query不替换、CPU/type隔离、
CPU1024/锁1025边界、共用TSC、冷却、倒退/零时间及已有pin复用的19条获取路由。
首次新增错误变体的源码匹配断言失败，修正测试匹配后全部通过；原日志保留。

普通功能 provider 和 SELFTEST 构建通过；guest ELF 复核 entry/table/cpu 为
24/12312/24640 B，continuation仍704 B、存储栈8512 B、节点128 B。
构建保留已有手写恢复汇编的objtool及locale警告，不是无警告构建。
真实探针确认 `replaced=1`，替换后原owner仍在、解锁后word=0；mutex从CPU1
迁移到CPU2且抢占配对正确，探针排空。该探针设置mutex_jit=0，不算mutex JIT。

| 功能场景 | 策略 | 完整操作 | 实际 JIT 正文 | 结果 |
| --- | --- | ---: | ---: | --- |
| plain / c1 / t4 | adaptive | 400000 | 226453 | 通过、排空 |
| nested / c1 / t4 | observe | 400000 | 396343 | 通过、排空 |
| early / c1 / t4 | observe | 400000 | 99915 | 通过、排空 |

三项均使用 `--functional --repeats 1 --iterations 100000`；业务、IRQ/preempt
及排空检查通过，无新增内核错误。运行结束后无worker/daemon/provider残留。
没有运行性能benchmark，不输出或比较吞吐，不将减少链表操作宣称为性能提升。
本轮没有覆盖真实mutex JIT、强制native续跑、IRQ/NMI压力及多锁碰撞的live性能。

命令、输入哈希、ELF布局、日志及功能JSON在guest
`/root/kdlock-evidence/directhash-v2-20260922/`；本地证据归档位于
`bench/.tmp/directhash_v2_20260922/`（忽略目录，不纳入Git）。

后续按用户要求完成[三方性能矩阵](20260922-directhash-v2-performance.md)，与本文功能阶段分开记录。
