# 2026-09-21：精简 KD 无竞争入口

本轮减少了单线程指令和周期开销，但尚未解决相对 TCLock 的吞吐差距。
只运行 Linux 原生、TCLock 和修改后的当前 KD，没有旧版 KD 测量臂。

## 修改与约束

基于 `1b2c320` 工作树，保留已有文档修改。实现分为三部分：

1. 把 24 B 栈上 request 移入 `kd_spin_lock_contended()`；根 CAS 成功不创建，
   失败值原样传入 helper，不增加 CAS。物理嵌套保留先预留 ticket 再 CAS。
   把解锁的 16 B ref 移入 `kd_spin_unlock_slow()`，fast owner 命中不创建。
2. 新增 `kd_exec_context_occupied()`，一次本地 context 查询替代 frame/busy
   两次调用。保留精确谓词 `depth && (owner != current || top)`。
3. 热表共享实现强制 inline，在四个固定 spin/mutex、record/query 入口消除
   类型选择和操作分支；CPU1024、单锁1025、精确地址、窗口、busy 重入和 pin 均不变。

每次真实获取仍只增加一次抢占计数。Linux 的上层 spin_lock 包装管理自己的
preempt pin；当前 KD 显式 API 绕过该包装，因此不能删除 KD 自己的配对保护。
没有修改 TCLock、guest 内核、mutex 互斥协议、JIT wrapper 或对象布局；物理 owner、
ticket/continuation、ACK 和最终退休检查保留。

最终 guest ELF 确认公共 lock/unlock 不再包含上述局部清零和 canary，慢路径仍有
canary；没有关闭编译保护。公共 lock/unlock 的主符号分别为 277/119 B。
调用者 callee-saved 寄存器与 SP/IP/BP 保存仍在，fast 路径并非无栈。
热表四个主入口的代码合计 1630 B；此前共享主函数加四个入口为 1111 B，
均不含 cold 和其他 helper。展开减少分支，但增加约 519 B 主入口代码。

## 本轮验证

仅在 recovery guest `6.1.159-kdclobber2` 构建/执行，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，保留 voluntary/nokaslr、UBSAN
及缓解配置。确认 `pre_static_boot_20260915` 快照；源码清单冻结并核对宿主/guest。
W=1 provider 与 workload 构建通过；原有手写换栈 objtool 告警保留。

基础两个 C 检查及五个定向 Python 驱动通过：preempt、hotlock sampling、
exec capacity、direct unlock、native MCS。覆盖 19 条获取路由、40 万次 MCS
恰好一次/互斥、四类解锁来源、生产 context/frame 及热表边界；11 种采样错误
变异均被检测。第一次运行有采样路径拼错和 direct fixture 未提取新 helper 两项
检查失败；修正入口后两项通过，保留初次日志，不算内核运行失败。

| 功能场景 | 完成数 | 实际 JIT 正文 | 排空 |
| --- | ---: | ---: | --- |
| early-observe-on | 400000 | 99967 | 通过 |
| nested-observe-on | 400000 | 381475 | 通过 |
| plain-adaptive-on | 400000 | 200979 | 通过 |
| plain-observe-off | 400000 | 0 | 通过 |
| plain-observe-on | 400000 | 198451 | 通过 |

五组共 200 万次操作，业务、IRQ/preempt 和退出状态通过。off 是原生对照，
其余四组为实际 JIT 正例。本轮未专项强制 native 续跑/无锁 relay、延迟 ACK、
容量耗尽或跨 NUMA，也未重跑 mutex JIT 和全量 unit。

## 当前三方吞吐

observe/plain，1/16 cacheline × 1/4/8/16/20 线程 × 三方 × 五轮；每线程
100000 次，同一节点 CPU 0..T−1，奇数轮逆序。每场相同的 48000 次预热和静置，
准备/翻译不计时；计入完整锁操作、业务更新、锁外计算及线程放行/结束开销。
`Mops/s = completed × 1000 / wall_ns`，各配置取五场中位数，不剔除慢样本。

| cacheline | 线程 | Linux Mops/s | TCLock Mops/s | KD Mops/s | KD/TCLock |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.066 | 13.747 | 6.334 | 0.461× |
| 1 | 4 | 3.670 | 2.986 | 1.976 | 0.662× |
| 1 | 8 | 3.812 | 4.312 | 4.024 | 0.933× |
| 1 | 16 | 3.851 | 4.969 | 4.964 | 0.999× |
| 1 | 20 | 4.010 | 5.038 | 5.039 | 1.000× |
| 16 | 1 | 12.848 | 10.992 | 6.372 | 0.580× |
| 16 | 4 | 2.150 | 2.211 | 1.719 | 0.778× |
| 16 | 8 | 2.256 | 3.152 | 3.985 | 1.264× |
| 16 | 16 | 2.340 | 3.467 | 4.733 | 1.365× |
| 16 | 20 | 2.441 | 3.333 | 4.813 | 1.444× |

150/150 场、1.47 亿次操作通过；40 个 KD 竞争会话均有实际 JIT，10 个 KD 单线程
会话为原生自执行。TCLock 代理计数仍为 UNMEASURED。单线程与四线程仍落后；
c1 高线程接近 TCLock，c16 高线程领先。与[此前短批次记录](20260921-threeway-current.md)
相比，c1 单线程约 6.260→6.334、c16 约 5.976→6.372 Mops/s；这是历史批次参照，
不构成同期旧/新因果对照，不把百分之一量级差异视作稳定收益。

## 同一最终 ELF 的单线程 PMU

三方 × c1/c16 × 两轮 = 12 场，每场 5000 万次，共 6 亿次操作。CPU0，observe，
perf stat 采集内核 cycles/instructions/branches/branch-misses，按完成数归一化后
取两轮中位数。事件运行比例均至少 99%；所有会话 JIT=0、业务/状态/排空通过。
本轮仅硬件计数，没有重新做热点采样；长批次 PMU 不能替代上述短批次吞吐。

| cacheline | 后端 | cycles/op | instructions/op | branches/op | branch-misses/op |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | native | 57.00 | 50.04 | 8.15 | 1.0003 |
| 1 | tclock | 70.22 | 56.05 | 13.01 | 1.0003 |
| 1 | kdlock | 202.81 | 289.13 | 60.03 | 1.0030 |
| 16 | native | 74.74 | 95.05 | 8.18 | 1.0003 |
| 16 | tclock | 87.99 | 101.05 | 13.22 | 1.0004 |
| 16 | kdlock | 227.85 | 333.97 | 60.03 | 1.0032 |

与[优化前已归档 PMU](20260921-single-thread-profile.md)相比，c1 KD 指令约
343.86→289.13（−15.9%），周期约 245.62→202.81（−17.4%）。这是同方法的历史
诊断参照，本轮没有加载旧版 KD。减少局部准备、调用和分支的效果可以在 ELF 与
计数中看到；没有独立拆分三项修改各自贡献。KD 仍承担热度、上下文、fast owner
和 clobber ABI 成本，不能声称已接近 TCLock 的单线程开销。

## 证据

Guest：`/root/kdlock-evidence/fastopt-20260921/`。保存 host.patch、源码清单、
内核身份、恢复快照、构建与单元日志、五组 functional、matrix、pmu 及审计脚本。
所有功能/矩阵/PMU 顶层退出码均为 0；167 份内核日志无 BUG/Oops/WARNING/stall，
最终 worker/daemon/provider 排空。冻结源码/二进制哈希及每场数据已复核。

归档和宿主离线核验信息见下方；归档后文档更新不改变已测执行代码。

[完整归档](../../.tmp/fastopt_20260921/fastopt-20260921.tar.gz)，SHA256：
`81bea3201778582923a869fb686cab4dc6a86951d5828326a88e449a090b1153`。
[宿主离线复核](../../.tmp/fastopt_20260921/offline-audit.json)；归档脚本的校验文件
在 guest 名为 `fastopt-20260921.tar.tar.gz.sha256`，本地按归档名整理为 `.tar.gz.sha256`。
测量数据没有因此改写或重跑。
