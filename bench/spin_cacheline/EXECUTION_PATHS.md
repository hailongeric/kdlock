# 当前直接调用路径

三臂使用同一负载源码，按后端分别编译；不是同一 ELF。完整操作包含获取、正文、
释放、锁外乘加与循环，不将 ns/op 当作单独获取锁延迟。

| 后端 | 入口与执行 |
| --- | --- |
| Linux | `__raw_spin_lock/unlock`，独立 Linux 对象 |
| TCLock | `komb_spin_lock/unlock`，调用者管理抢占，原生栈切换执行正文 |
| KD | caller-clobber v1、本地热度、安全/就绪准入、单锁字 fast/pending/MCS、JIT 或 KD 自执行 |

KD 不再包含 spin 统一分发、gate 映射、独立 S、Linux L 二次获取或站点缓存。
无法代理也必须遵循 KD 协议；fast owner、ticket、request/frame、等待栈和 ACK 保留。
observe 记录热度但固定准入；adaptive 把各 CPU 自然升温和冷却纳入完整操作成本。

真实 JIT 用 wrapper 返回后的正文计数判断，发布 NORMAL 不等于执行。TCLock
当前只验证业务数据和排空，没有实际委托计数，不能把剩余调用数当成委托比例。
当前矩阵与回退见 [联合报告](../tclock_compare/results/20260920-local-hash.md)。
