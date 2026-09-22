# 2026-09-22：无抢占检查、无 busy 门的热表核心

> 历史实验：本方案已回退。当前实现与后续性能验收见[回归处理](20260922-performance-recovery.md)；下文保留当时源码、口径与结果。

按用户要求，热度计数允许近似误差，不再通过 busy 门处理或丢弃中断重入样本。
`kd_hotlock_access()` 不读取 preempt_count，也不调用 preempt_disable/enable。

## 改动与边界

- spin 主入口已取得获取锁所需的一次 pin，改用 `kd_hotlock_record_spin_pinned()`
  直接调用核心。通用 record/query 在外层 `kd_hotlock_access_guarded()` 按需 pin，
  供 mutex、独立调用及通用嵌套入口使用；mutex 不跨睡眠保持统计 pin。
- 删除 table.busy、逐次 busy compare-exchange、释放 busy 和重入丢样分支。
  计数及时间窗口允许中断下的误差，不关闭 IRQ，也不要求精确事件数。
- CPU1024、单锁计数大于1024、完整地址 hash 匹配和满表处理保留。首次新地址
  插入才用两个无 LOCK 前缀的 cmpxchg_local 预留有界槽并发布已初始化的链接，
  防止索引越界和链表损坏；已有锁的计数路径不执行它们。
  中断交错下不承诺每地址只有一条采样记录或完整采样历史。
- guest ELF/pahole：entry=24 B，table 从6688降至6680 B；两表加对齐尾部，
  每 CPU 仍为13376 B、64 B对齐，实际预分配大小未减少。

保留 owner、ticket、continuation、ACK 和实际锁获取/解锁抢占配对。
未修改 TCLock、guest 内核、mutex 互斥协议或 JIT wrapper。

## 验证

以 `1b2c320` 加此前未提交优化为输入，保留已有工作树改动。仅在 recovery guest
`6.1.159-kdclobber2` 构建/执行，确认 `pre_static_boot_20260915` 快照；保留
UBSAN、栈保护和缓解配置。W=1 构建通过，原有手写换栈 objtool 告警保留。

基础两个 C 检查和 hotlock sampling、spin preempt、direct unlock 三个 Python
驱动 **5/5通过**。保留阈值、窗口、碰撞/满表、地址、CPU/type 隔离和 query
只读检查；用“核心不读/修改抢占、链接有界”取代旧的重入整表不变断言。
12种错误变异被检测，包括重新给核心加入 preempt_count。19条获取路由保持
一次 acquisition pin，四类解锁来源通过。

四组功能运行均为 `--functional --backends kdlock --cachelines 1 --threads 4`
`--repeats 1 --iterations 100000`，不同模式使用独立会话：

| 场景 | 完成数 | 实际 JIT 正文 | 排空 |
| --- | ---: | ---: | --- |
| nested-observe-on | 400000 | 391029 | 通过 |
| plain-adaptive-on | 400000 | 200332 | 通过 |
| plain-observe-off | 400000 | 0 | 通过 |
| plain-observe-on | 400000 | 213405 | 通过 |

共160万次操作，业务、IRQ/preempt恢复和排空检查通过。off为零JIT原生对照，
其余三组为实际JIT正例。四个运行器退出码均为0，内核日志无BUG/Oops/WARNING/stall，
最终guest空闲。未重跑全量unit、mutex JIT、跨NUMA、强制native续跑或真实IRQ/NMI矩阵。

ELF确认 spin 专用record、clock和insert没有preempt_count/preempt_schedule引用；
专用record没有busy compare-exchange。两处本地compare-exchange均在新地址insert，
且无LOCK前缀。通用record外层保留抢占引用，符合API契约。

本轮**未测性能**，只确认移除了哪些操作。[9月21日PMU](20260921-fast-path-optimization.md)
早于本次修改，289 instructions/op等旧数字不能记为当前版本成绩。

## 证据

Guest：`/root/kdlock-evidence/hotcore-20260922/`，包含修改前文件、host.patch、
源码清单、unit.log、四组功能结果、源码/ELF、内核身份、快照、反汇编、layout.txt
及audit.json。首次审计误用性能模式的records.json，第二次误查后续构建覆盖的临时
provider路径；最终按每个功能会话的session.json及冻结ELF副本核对通过。
三个审计脚本均保留，没有重跑或替换功能结果。

[完整归档](../../.tmp/hotcore_20260922/hotcore-20260922.tar.gz)，SHA256：
`c2b1063f29dfacdd61919e78f153921a08f589963180955ba6fe812e71faf06b`。
[宿主离线复核](../../.tmp/hotcore_20260922/offline-audit.json)。
