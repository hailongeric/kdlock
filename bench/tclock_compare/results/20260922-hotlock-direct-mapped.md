# 2026-09-22：热表改为 1024 槽直接映射

> 历史实验：本方案已回退。当前实现与后续性能验收见[回归处理](20260922-performance-recovery.md)；下文保留当时源码、口径与结果。

每 CPU 的 spin/mutex 共享热表由 buckets/冲突链改为 `entries[1024]`。
`hash_long(address, 10)` 直接选一个槽；完整地址不同就替换，清零旧 count/hot，
借用最近 CPU 时间作为起点，再计入新样本。不探测其他槽，不分配空槽，不继承
旧地址热度。反复冲突可使两地址一直保持冷值，在 adaptive 下不代理。
query 地址不匹配只返回冷，不替换、不计数、不采时；observe 仍是固定准入诊断模式。

删除 buckets、next、used、find/insert 遍历及槽预留/链接发布的两次本地 CAS。
CPU1024 / 单锁1025批次、spin/mutex共享统计及无核心抢占检查/busy门保持不变。
近似采样不保证中断嵌套下的精确计数；owner、ticket、continuation 与热表独立。

| guest ELF 对象 | 前序共享链表 | 本轮直接映射 |
| --- | ---: | ---: |
| entry | 24 B | 24 B |
| table | 6680 B | 24592 B |
| 每 CPU 对象（64 B 对齐） | 6720 B | 24640 B |
| 记录数 | 256 | 1024 |

模块初始化 `alloc_percpu` 一次预分配；每 CPU 请求大小增加17920 B，锁路径不分配。
冷却/重新变热时现在遍历1024槽重置计数/热值/起点，地址保留。这是存储和周期
重置成本的增加；本轮没有性能测量，不声明吞吐提升。完整数据流与流程图见
[EXECUTION_PATHS](../../spin_cacheline/EXECUTION_PATHS.md#51-准备热度与快速获取)。

## 本轮验证

基于 Git `1b2c320` 的已有未提交工作树，保留此前改动，仅在 recovery guest
`6.1.159-kdclobber2` 构建和执行。未修改 TCLock 或 guest 内核。
普通/SELFTEST 构建通过；普通和 SELFTEST ELF 均用 pahole 核对上述布局。
反汇编确认无 hotlock find/insert，所有采样/查询函数及 clock 无 cmpxchg，
spin 已 pin 核心及 clock 无抢占引用；通用外层仍按需 pin。

`make -C tests/unit run` 加
`PY_TESTS="infrastructure/test_hotlock_sampling.py spin/test_spin_preempt.py spin/test_spin_direct.py"`
共5/5通过；14种错误变异均被检测。覆盖冲突替换清除旧 count/hot/时间、query
不替换、交替冲突保持冷值、全部1024槽占用后仍替换、其他槽不受影响、共享API/
CPU隔离、批次时钟边界及19条获取路由的抢占配对。

实际 JIT 使用 `bench/tclock_compare/run.py --functional --backends kdlock`
`--cachelines 1 --threads 4 --repeats 1 --iterations 100000`：

| 场景 | 完成数 | 实际 JIT 正文 | 排空 |
| --- | ---: | ---: | --- |
| nested-observe-on | 400000 | 395840 | 通过 |
| plain-adaptive-on | 400000 | 198252 | 通过 |
| plain-observe-on | 400000 | 201417 | 通过 |

共120万次操作，业务、IRQ/preempt恢复和排空通过。独立 SELFTEST 以
`hotlock_lifetime_selftest=1 hotlock_mode=observe hotlock_stats=1 mutex_jit=0` 加载：
通过 mutex 采样API替换真实持有的 spin 锁热表槽，确认旧热值消失、新地址冷，
实际 owner 保留且解锁后 word=0；原生 mutex 等待从 CPU1 迁移到 CPU2，
抢占配对正常。该探针不是 mutex JIT 正例。

全部运行退出0，内核日志无 BUG/Oops/WARNING/stall，最终 guest 空闲。
源码与冻结 ELF 哈希一致；宿主离线再次核对归档。未运行性能 benchmark、PMU、
全量 unit、mutex JIT、跨 NUMA 或强制 native 续跑矩阵；不扩大本轮覆盖范围。

## 证据

Guest：`/root/kdlock-evidence/hotdirect-20260922/`。包含源码备份、host.patch、
源码清单、单元/构建日志、三个功能会话、SELFTEST、内核身份、快照确认、
普通/SELFTEST ELF和布局、反汇编及audit.json。

[完整归档](../../.tmp/hotdirect_20260922/hotdirect-20260922.tar.gz)，SHA256：
`881e70add4caa4e632b487a5d1eac9a9e748e2ef072cf06567f192b02785be42`。
[宿主离线复核](../../.tmp/hotdirect_20260922/offline-audit.json)。前序
[共享链表报告](20260922-hotlock-shared-table.md)保留历史布局/成绩，不是本轮结果。
