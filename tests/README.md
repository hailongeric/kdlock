# 当前测试入口

构建和运行只在 recovery guest，先读 [操作手册](../docs/AGENTS.md)。当前版本是
显式 KD 单锁字 API；全局 spin 分发已删除、mutex hook 安装停用。旧 hook live
套件、gate 容量测试及其专用 workload 已删除，不能以普通 Linux 锁完成冒充 JIT。

## 单元检查

```sh
make -C tests/unit run
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py spin/test_spin_entry.py infrastructure/test_hotlock_sampling.py'
```

默认只执行两个基础 C 程序，按修改选择直接相关驱动；`run-all` 仅在明确要求时使用。
`python3 tests/unit/run.py --list` 列出现存驱动，无隐式执行。

| 修改范围 | 相关驱动（位于 tests/unit） |
| --- | --- |
| 原生 pending/MCS 与 owner 配对 | `spin/test_spin_nondelegated.py`、`spin/test_spin_shadow.py` |
| 单锁字入口和 ticket | `spin/test_spin_direct.py`、`spin/test_spin_entry.py` |
| 入口抢占配对 | `spin/test_spin_preempt.py`、`infrastructure/test_hotlock_sampling.py` |
| continuation 容量、回收与最终恢复 | `execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py` |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热锁哈希和窗口 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py` |
| 范围选择与离线证据 | `infrastructure/test_regression.py` |

共享源码读取/头文件过滤位于 `unit/infrastructure/source_text.py`，不再依赖旧 gate
测试。保留的 mutex/remote 等日志 oracle 检查身份、owner、ACK、顺序和最终副作用；
合成日志通过不表示当前 live 覆盖。生产代码 fixture 同样不证明真实内核并发。

## Live 检查

`tests/run_all.sh` 无参数只列出现存范围；`--case module --dry-run` 只预览。
当前唯一基础 case 为 provider/device 生命周期，不加载旧 `klock_module`，JIT=0：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 timeout 240 tests/run_all.sh \
  --case module --output /root/kdlock-evidence/module-current
```

输出目录必须新建在仓库外；变量只在 monitor 已确认真实快照后设置。
运行器核对依赖、冻结源码、检测内核错误及残留调用者，失败保留证据并停止。
`tests/verify_evidence.py` 对这类已有归档做离线一致性校验，不执行归档代码。

实际 JIT 与业务互斥使用 [直接运行器](../bench/tclock_compare/README.md)。
`--scenario plain` 为普通单锁；`--scenario nested` 为 A/B 嵌套；`--scenario early`
为外锁提前释放，仅 KD cacheline 允许后两项。observe 竞争正例要求真实 JIT；
adaptive NO_JIT 只可作为明确标记的性能样本。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 hotlock_mode=observe spin_entry_selftest=1`
检查真实持锁候选淘汰、mutex 等待 CPU 迁移及 owner ACK；这不执行 JIT。
构建方式及控制参数见 [provider](../kernel_module/README.md)。保持 normal 与
SELFTEST 构建分开，不替换加载中的模块，完成后必须排空和正常卸载。

## 结果与边界

[2026-09-20 联合报告](../bench/tclock_compare/results/20260920-local-hash.md)记录
单锁字/哈希、nested/early、淘汰/迁移、ACK 和完整矩阵，以及首次失败和性能回退。
更广远端 native/JIT live 组合未在该版本重跑。历史证据入口为
[VALIDATION](../docs/VALIDATION.md)，删除的脚本及操作细节可从整理前提交
`1b9191256f64785f8e844ada914356a69d4f70f0` 取回，需使用匹配版本，不能套用到当前 provider。

## 2026-09-20 当前版本整理验证

以 `1b91912` 为整理基线，删除不再适用的 hook/gate live 入口和工作负载，保留
有效生产代码与协议 oracle。公共源码提取移出 gate 测试；寄存器探针移入 fixture。
修正 request/frame 替身、5400 字节 context oracle、观察 patch 清单及绑定参数权限。
初次发现的旧布局、旧脚本参数检查和观察层失配均保留记录，未放宽协议断言。

全部在 kdclobber2 recovery guest：分批执行两个基础程序及 13 个直接相关驱动，
修复后均通过；客户端/观察层 15 项、汇编归档 7 项、直接运行器 7 项通过。
normal provider W=1 和顶层默认 native workload 构建通过；module case 装卸、
retire 和离线证据校验通过（JIT=0）。单场 c1/t4/observe smoke 完成 400000 次
操作，其中实际 JIT 正文 220828 次，数据正确且排空。未运行全量套件或性能矩阵。
Python/脚本语法、当前入口预览、文档本地链接及 `git diff --check` 通过。

证据目录：guest `/root/kdlock-evidence/tidy-20260920/`。其中 `unit.log`、
`depth2/3.log`、`affected-final.log` 和 `bench-unit.log` 保留首次问题；
`frame-node-final.log`、`bench-unit2.log`、`direct-final.log`、`module/`、
`module-offline.json` 和 `direct-smoke/` 保留最终验证。各阶段冻结源码与哈希
定义其输入；最后仅有文档、注释及未使用的旧上传 Packet 声明清理，未改锁算法。
归档为 guest `/root/kdlock-evidence/tidy-20260920.tar.gz`，SHA256：
`127c52f50eecbd7b11b26fe75e70ca3cb15aa072b2b911f3ae190cb590cc8aa2`。
大型归档和构建产物不提交。


## 2026-09-20 结构体整理验证

以 `1686fbc` 为基线，删除无消费者的字段及参数，把 spin 节点预留计数移至
CPU 状态，把嵌套 requester/depth 内嵌到稳定 request；复用 outer release 状态和
mutex 原锁地址，mutex 编码 tail 改为 `u32`。寄存器引用、锁账本计数和角色状态机
未重写。当前布局及生命周期边界见 [frames](../docs/design/frames.md#911-reuse-before-copy-contract)。

本次 guest ELF 的 `pahole` 布局：

| 对象 | 原大小 → 当前大小（字节） |
| --- | --- |
| `kd_combiner_state` | 112 → 88 |
| `kd_exec_frame` | 672 → 648 |
| `kd_exec_context` | 5400 → 5208 |
| spin CPU 状态（非 NUMA） | 96 → 80 |
| `kd_spin_exec_request` / `kd_spin_node` | 768 / 128，均未改变 |
| `kd_mutex` / mutex shadow 条目 | 40 / 48 → 32 / 32 |

此结构体整理阶段的 spin 通知偏移为 64/65，旧 request 池为每 CPU 9216 字节；取消独立 JIT context
池。mutex 1024 项静态映射减少 16 KiB。上述为该阶段布局，不代表吞吐收益；
后续 continuation 栈取代旧池，当前尺寸与退休规则见[新验证记录](#continuation-validation)。

全部构建和运行均在 kdclobber2 recovery guest。本次分批执行两个基础程序及
10 个相关驱动：`spin/{test_spin_wait,test_spin_outer_progress,test_spin_shadow,
test_spin_batch,test_spin_frame_protocol}.py`、
`execution/{test_exec_capacity,test_remote_deferred_protocol,test_remote_depth_protocol}.py`、
`mutex/{test_mutex_resources,test_mutex_outer_progress}.py`，最终均通过。
覆盖生产代码的队列/取消/重入、节点复用、frame 退休、outer release、remote ACK；
等待栈与寄存器恢复实际执行通过。shadow 的 9 个变异均被断言拒绝，NUMA 开关
两种 fixture 通过；观察层隔离和 wrapper 返回后正文计数两个测试通过。
这些确定性 fixture/oracle 不等于真实内核并发覆盖。

普通 provider 和 SELFTEST + NUMA 的 `W=1` 构建通过；保留原有手写栈切换的
objtool 警告。直接运行器使用 c1/t4、observe、100000 iterations、单次重复：

| 场景 | 完成操作 | 实际 JIT 正文 | 业务检查 / 排空 |
| --- | --- | --- | --- |
| plain | 400000 | 234846 | PASS / PASS |
| nested | 400000 | 389888 | PASS / PASS |
| early | 400000 | 53995 | PASS / PASS |

各场都核对入口/锁身份、IRQ/preempt、数据、内核错误及 source retire，最终
frames/modules/writers 均为 0。未跑全量套件、性能矩阵、mutex JIT live 或更广
remote/native live 组合；后两者本轮仅有相关 fixture/oracle 覆盖，不能记为 live PASS。

证据目录为 guest `/root/kdlock-evidence/structs-20260920/`。初次 fixture 类型/布局
失配、SELFTEST 声明顺序/旧成员引用以及 plain 观察 patch 上下文失配均保留。
`unit-fix2.log`、`related.log`、`shadow-mutations.log`、`observation-final.log`、
`build-normal-final.log`、`build-selftest-numa-final2.log` 和
`plain-final/`、`nested/`、`early/` 为对应最终结果；`unit-fix1.log` 保留真实等待栈通过项。
每场源码、ELF、内核身份和哈希已冻结；最终源码仅补充注释和文档，不改变协议。
大型证据和构建产物不提交。

归档：guest `/root/kdlock-evidence/structs-20260920.tar.gz`，SHA256：
`56a766d7220247d898c328e3397ca4528ef987de4c6503fe7dbd41dc9b0347a4`。
归档使用 guest 已有冻结材料；补充的宿主机完整 diff 留在 `/tmp/kd-struct-final.patch`，
未上传到 guest。最终空闲检查通过。


## 2026-09-20 不代理 MCS 验证

KD 原生拒绝/冷锁路径改为共用 pending/MCS 节点，不申请 execution request/frame。
原生 owner、混合队列、嵌套及提前释放检查和性能边界统一见
[本轮报告](../bench/tclock_compare/results/20260920-native-mcs.md)。
`spin_delegate=0` 为明确的零 JIT 对照，默认开启代理时的 observe 竞争正例仍须
有真实 JIT。基础与相关单测、正常及 SELFTEST + NUMA 构建通过；未运行全套。

<a id="mcs-recovery-validation"></a>

## 2026-09-21 性能回退后的恢复验证

当前恢复包含 ticket 优化的旧版 A；MCS 后置准入和 admit 时钟实验已经撤回。
七个生产文件精确恢复，`kd_spin_entry.c` 的 guard 合并及 continuation 退休协议保留。
对应测试恢复旧版接口，未删除节点复用、frame 退休、根包共享或 ACK 检测。
源码、阶段差异、同期性能与未覆盖边界见
[回退报告](../bench/tclock_compare/results/20260921-mcs-recovery.md)。

guest `6.1.159-kdclobber2` 内两个基础程序及以下七个定向驱动，**9 项全部通过**：

```sh
make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py spin/test_spin_preempt.py spin/test_spin_nondelegated.py spin/test_spin_entry.py spin/test_spin_shadow.py spin/test_spin_outer_progress.py spin/test_spin_wait.py'
```

覆盖 19 条入口抢占/owner 路径（含 pending-only、tail 竞争和 foreign pending）、
原生 MCS 400000 次互斥/恰好一次操作、混合节点边界、ticket guard/代际、
continuation 容量与栈顶回收、生产者/节点先复用、共享包、提前释放/重获取、
延迟 ACK 和退休顺序。真实汇编 waiter/最终恢复检查继续通过；普通完成、retry、
native 保留/退休及 MINIMAL complete/retry 各 32 次。fixture 的 CPU、peer/JIT
替身限制仍保留，不等同于完整内核并发验证。
首个命令误列不存在的 `test_spin_queue_return.py`，运行器明确失败；改用
实际等待路径驱动后重跑整组通过，首轮失败日志保留。

最终 `--functional`：c1/t4、每线程 100000 次，各场 **400000 次**，全部业务、
CPU 亲和性、IRQ/preempt、内核错误和排空检查通过；功能入口不生成性能比较。

| 场景 | 实际 JIT 正文 | 验收 |
| --- | ---: | --- |
| observe / plain | 189142 | PASS |
| observe / nested | 385281 | PASS |
| observe / early | 99941 | PASS |
| off / plain | 0 | DISABLED_CONTROL |
| adaptive / plain | 162702 | PASS，自然积累热度 |

证据在 guest `/root/kdlock-evidence/mcs-recovery-20260921/` 的
`unit-rollback-final.log`、`functional-{plain,nested,early,off,adaptive}/`。
本次没有全量回归、mutex live、跨 NUMA 或强制远端 native/无锁 relay 时序。
性能与 ELF 审计及归档身份统一维护在上述回退报告。

<a id="admission-clock-validation"></a>

以下为已撤回实验的冻结验证；当前版本见 [回退验证](#mcs-recovery-validation)。

## 2026-09-21 热度时间域移至准入

生产 spin 的 note 只累计配额/候选分数，不读取 TSC、不初始化或重置时间窗口。
MCS admit 才读取时间、更新速率和冷却候选；observe 也更新时间域。
CPU 配额在 10240 饱和，第一次准入开始计时；未满配额也检查过期和时钟回退。
关闭代理仅计数；query 保持只读快照。mutex/组件合并 record 的批量时钟保持原样。

Guest `6.1.159-kdclobber2` 的基础两个 C 程序加
`infrastructure/test_hotlock_sampling.py`、`spin/test_spin_preempt.py`，4 项通过。
验证 note 超过配额仍无 TSC、首次准入不能将未计时样本当频率、准入不增加样本、
低于配额仍清除过期热值、时钟回退、observe、重入和抢占配对。新增“note 读时钟”
及“未满配额跳过过期检查”变异均被检测，原有哈希/窗口/配对变异继续通过。
生产 `W=1` 构建通过，保留既有换栈 objtool 告警。

实际 `--functional`：c1/t4，每线程 100000 次，三场各完成 400000 次并排空。

| 场景 | JIT 正文 | 验收 |
| --- | ---: | --- |
| adaptive / plain | 158471 | 自然变热，真实 JIT |
| observe / nested | 377697 | 嵌套真实 JIT |
| spin_delegate=off / plain | 0 | DISABLED_CONTROL |

业务、CPU 亲和性、IRQ/preempt、内核错误与排空检查通过。证据在 guest
`/root/kdlock-evidence/admission-clock-20260921/` 的 `unit.log`、`build.log` 和
`functional-{adaptive,nested,off}/`。本轮只调整统计时间域，没有修改锁、frame 或
ACK 协议；没有性能 benchmark、全量回归、early/native 强制时序或 mutex live。
上一轮性能报告对应时钟调整前的冻结源码，不能当作当前性能测量。
归档 `admission-clock-20260921.tar.gz` 已取回宿主 `bench/.tmp/admission_clock_20260921/`，
SHA256：`540f67016dcb14a6548d05f051eb9334191aff8d7abab0ec94890cd1ca237232`。

<a id="mcs-admission-validation"></a>

以下为已撤回实验的冻结验证；当前版本见 [回退验证](#mcs-recovery-validation)。

## 2026-09-21 MCS 边界代理准入验证

普通及 JIT 虚拟入口先记录一次热度并尝试 fast/pending，失败后才判断代理。
`spin_delegate=0` 保留统计。根准入拒绝不占 ticket，虚拟请求保留独立 ticket；
虚拟 pending/native MCS 等待仍服务父 frame mailbox。

在 `6.1.159-kdclobber2` recovery guest 运行两个基础 C 程序及
`infrastructure/test_hotlock_sampling.py`、
`spin/{test_spin_preempt,test_spin_nondelegated,test_spin_entry,test_spin_direct,
test_spin_shadow,test_spin_outer_progress}.py`，9 项最终全部通过。
入口 fixture 的 38 条路径检查每次记录一次、fast/pending 不准入、不查 JIT/context、
拒绝不重复 CAS，以及一次 pin 和独立 native owner。采样 fixture 验证 admit 不推进
窗口/计数，observe busy 仍允许，原有阈值/重入变异检测保留。
原生 MCS pthread fixture 完成 400000 次互斥且恰好一次操作，并用回调释放阻塞锁
验证虚拟 pending 和原生 MCS 队首等待确实服务 mailbox。
虚拟 producer 新增 8 个 fast/MCS × off/cold/not-ready/continuation 满的案例，
检查 root 翻译身份、独立 ticket、未发布 frame 和寄存器未改变。
节点/混合队列、容量、根包共享、借用退休、节点先复用和提前释放/重获取的原有
生产 fixture 与变异检查继续通过；硬件/peer 模拟边界保持显式。

第一次组合回归有两个 fixture 失败：函数抽取签名未跟随共享 helper，以及翻译
身份断言仍假设查询只在 combiner 内。修正后重跑通过。新增虚拟案例另修正了
不模拟 pin 的 fixture 预期；旧生命周期断言未删除。日志保留首次失败与最后通过。

实际 `--functional` 为 c1/t4，每线程 100000 次，每场完成 400000 次并排空：
plain / nested / early 的真实 JIT 正文分别为 **216338 / 376065 / 99522**；
关闭代理控制为 **0**，标记 `DISABLED_CONTROL`。业务、CPU 亲和性、IRQ/preempt、
内核错误及排空检查通过。默认 provider 保留 `mutex_jit=1`，本轮负载只有 spin。
生产 `W=1` 构建通过，保留既有换栈 objtool 告警。

证据在 guest `/root/kdlock-evidence/mcs-admission-20260921/`：
`unit.log`、`unit-fix.log`、`unit-virtual-final.log`、`unit-inline.log`、
`build-inline.log` 和 `final-functional-{plain,nested,early,native}/`。首版
`functional-*` 是内联调整前的独立结果；最终版重跑采样、入口及四场 live。性能与冻结文件见
[MCS 准入报告](../bench/tclock_compare/results/20260921-mcs-admission.md)。
本轮没有全量回归、mutex live、跨 NUMA、adaptive live 性能，或强制远端 native
并发时序；ACK/容量 fixture 不等于所有这些实际内核时序的覆盖。

<a id="four-thread-ticket-validation"></a>
## 2026-09-21 四线程 ticket 路径优化验证

顶层 pending 复用 fast owner，MCS 队首正常返回不重复 claim；claim/reclaim 与
release 各合并为一次 guard，保留 CPU/task/generation、状态与借用检查。
节点/continuation 容量回退在返回前完成 claim，原入口抢占 pin 仍只配对一次。
执行协议见 [locking](../docs/design/locking.md#41-native-lock-and-private-queue)，
性能与证据见 [四线程报告](../bench/tclock_compare/results/20260921-four-thread-ticket.md)。

在 recovery guest 运行基础两个 C 程序及
`spin/{test_spin_preempt,test_spin_entry,test_spin_direct,test_spin_nondelegated,
test_spin_shadow,test_spin_outer_progress}.py`，8 项全部通过。入口 fixture 覆盖
19 条分支，明确检查顶层 pending 不 reserve ticket、嵌套/排队保留 ticket、
竞争发布时只清除自己设置的 pending 位。已有生产 fixture 继续检查代际拒绝、
借用退休、原生 MCS 互斥/恰好一次、NUMA 开关及提前释放/重新获取；变异检测通过。

实际 `--functional`：c1/t4，每线程 100000 次，各场完成 400000 次并排空。
plain/nested/early 的真实 JIT 正文数分别为 197977 / 387267 / 99945；
`spin_delegate=off` 为零 JIT 原生对照。业务、IRQ/preempt、内核错误及排空检查通过。
provider 使用默认 `mutex_jit=1`，负载只有 spin；未重跑 mutex JIT、远端 native
强制并发时序、跨 NUMA live 或全量回归，不把组件 fixture 记作这些路径的 live 验证。
本轮未修改 guest 内核或 TCLock。证据：guest
`/root/kdlock-evidence/four-thread-20260921/unit.log` 与 `functional-{plain,nested,early,native}/`。

<a id="continuation-validation"></a>
## 2026-09-20 continuation 交接验证

保留本轮开始时的热度/抢占配对和文档修改。先在旧池上改变退休顺序，再改为每 CPU
20 KiB 单次预分配：12 KiB continuation 区与 8 KiB 等待栈。普通完成先 pop 再通知；
NATIVE_READY 与物理解锁 ACK、最终退休分开。每个 native 执行者（含无锁 relay）
在唤醒原线程前登记根 ticket 借用，pop 后才解除，最后解锁等待全部退休。

guest `6.1.159-kdclobber2`，recovery/ext4、40 CPU、voluntary、nokaslr；未修改或
构建 guest 内核、TCLock 参考实现或 mutex 互斥协议。normal 和 SELFTEST+NUMA
均通过 `W=1` 构建；现有手写换栈的 objtool 警告仍存在。

两个基础程序与以下 14 个相关驱动全部通过（`make -C tests/unit run PY_TESTS=...`）：
`spin/{test_spin_entry,test_spin_wait,test_spin_preempt,test_spin_nondelegated,
test_spin_shadow,test_spin_batch,test_spin_outer_progress,test_spin_node_protocol}.py`、
`execution/{test_exec_capacity,test_remote_outer,test_remote_depth_protocol,
test_remote_outer_protocol,test_remote_deferred_protocol}.py`、
`infrastructure/test_hotlock_sampling.py`。另外，shadow 的 9 个变异、退休探针重跑及
功能运行器 9 项检查通过。未执行完整单元套件。

生产 fixture 覆盖 12 条容量、活记录下方空洞不可复用、远端仅标退休/本 CPU 收缩
栈顶、共享根包、节点先复用、延迟 ACK、2–8 层 native 正序/逆序释放与无锁 relay。
192 次真实 x86 恢复涵盖完整/最小包、重试、native、已退休的无锁 native 及栈顶收缩。
原生 MCS fixture 完成 400000 次恰好一次操作；14 条入口路由保留单次抢占 pin。
旧 waiter-exit 探针改为 pop 前 task 仍存活、packet/context 不变、pop 后验证拒绝；
日志 oracle 同步要求退休早于最终 ACK 返回，保留缺失、重复、损坏及顺序变异。
这些 fixture/oracle 不是实际内核远端 native 并发的证据。

最终 guest ELF：node 128 字节、64 字节对齐，通知偏移 64/65；continuation
768 字节、64 字节对齐，frame 偏移 32、寄存器包偏移 104；存储栈 9280 字节，
records 偏移 64，位于 12 KiB 区内。恢复反汇编核对 SP/IP/BP 偏移
256/232/136、retired 偏移 24、storage 偏移 8、回收步长 768；现场读取先于退休写入。

实际 JIT 采用直接 API 的 `--functional` 入口，仅 KD、c1/t4、单次重复，每线程
100000 次。最终结果记录在 `plain-final/`、`nested-final/`、`early-final/`，
原生对照记录在 `native-control/`；各场核对正文、业务数据、IRQ/preempt、错误日志及
排空。原始证据以各目录 `functional.json` 为准：

| 场景 | 完成操作 | 实际 JIT 正文 | 业务/上下文/排空 |
| --- | --- | --- | --- |
| plain | 400000 | 240426 | PASS |
| nested | 400000 | 389816 | PASS |
| early | 400000 | 99947 | PASS |
| 原生对照（代理关闭） | 400000 | 0，DISABLED_CONTROL | PASS |

provider 已卸载，最终无 workload/daemon/provider 在途；各场 source retirement
检查 frames/modules/writers 为零，没有本轮 kernel BUG/Oops/WARNING。
未运行 mutex JIT 负载。

证据目录：guest `/root/kdlock-evidence/continuation-20260920/`。
`stage1-build.log`、`stage1-retirement-final3.log` 保留旧池阶段；
`final-unit.log`、`probe-final.log`、`shadow-mutations.log`、
`build-{normal,selftest}-final.log`、`*-layout.txt`、`restore-assembly.txt` 为最终检查。
首次 fixture 类型/状态迁移失败也保留；没有把编译失败计为变异检出。
各实际 JIT 场次冻结源码、ELF、内核身份、哈希与 dmesg。
归档基于 Git `e25c55151fa7f98b07c516cb613c6198c1c12910` 的工作树；
`staged-diffs/00-user-preserved.patch` 保留原有修改，`01-retirement.patch` 为旧池
退休顺序阶段，`02-continuation.patch` 为存储迁移及相关测试/文档阶段。
`staged-diffs/final-files-sha256.json` 记录验证时文件哈希，`final-idle.json`
确认源码哈希一致、四场功能检查通过及模块/翻译者排空。

完整证据归档为 guest `/root/kdlock-evidence/continuation-20260920.tar.gz`，SHA256：

```text
cc8c2f4d8c8404b66cc8fc0a8579bf2e37a93a08db33ee28ab1277b626759a49
```

本次提交汇总上述实现及原有抢占配对修改；归档之后仅补正文档术语、证据索引和
提交说明，未改动已验证的实现与测试。提交前只读复核归档哈希与排空记录，
没有重新运行上述构建或功能检查，归档内文档保持验证时版本。

上述功能交付阶段未运行性能测量，只确认减少独立预分配、空闲引用计数扫描和
`users`/`packet_owner` 更新。提交 `644f231` 后另行完成
[150 场三方性能矩阵](../bench/tclock_compare/results/20260920-continuation.md)，
不将后续性能运行混入本节功能归档，也不从历史差异推导单项改造收益。
未重跑 mutex JIT、真实内核多 CPU
远端 native/无锁 relay 强制时序、极端容量/取消组合；这些边界不能记为 live PASS。
