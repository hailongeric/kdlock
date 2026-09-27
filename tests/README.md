# 当前测试入口

构建、单元、模块和性能测试只在 recovery guest 执行，先读
[操作手册](../docs/AGENTS.md)。当前使用显式 KD 单锁字 API；普通 Linux 锁完成
不能作为 KD JIT 证据。按修改范围选择下面的单元、功能或性能入口。

## 最近验证与证据

结果按冻结源码分别记录，不合并为当前版本全量验收。

| 批次 | 已完成与范围 |
| --- | --- |
| [hash JIT/预取优化](../bench/tclock_compare/results/20260927-hash-optimization.md) | 基础及直接相关codegen/frame/batch检查、runner39项、NORMAL构建和hash分阶段/完整矩阵；首次fixture失败及修正保留，默认配置和nested/early验收范围见报告；未跑全量或mutex live |
| [hash连续计时与三方比较](../bench/tclock_compare/results/20260927-hash-peak.md) | 基础2组、runner36项、peak8项及135场timed hash通过；独立业务/结构/峰值/JIT/排空审计通过，未跑全量或mutex负载 |
| [MCS1024窗口调优](../bench/tclock_compare/results/20260927-ratio-window.md) | 五阶段144场定向比较及最终15线程点三方135场通过；NORMAL构建、基础及相关4组和runner35项通过；保留单锁512目标，未跑全量/nested/early/mutex live |
| [MCS右移/清零比例窗口](#spin-ratio-reset-validation) | NORMAL/观测provider构建、基础及采样/原生MCS共4组、runner35项通过；默认门槛下8/36线程plain实际JIT及排空通过，未重跑性能 |
| [KD实现文件拆分](#2026-09-27-kd实现文件拆分) | NORMAL provider构建、基础及相关11组、observer路径适配单项通过；C展开/ Python AST核对及ELF对比，未加载模块或重跑性能 |
| [显式IRQ/BH spin接口](kernel/spin/irq_api/README.md#2026-09-27-验证) | 基础及相关7组最终通过，NORMAL provider/consumer构建、跨两node四CPU混合变体40,000次及排空通过；JIT=0，初次fixture/日志收集失败保留，未测性能或全量 |
| [全链路复查与重复操作精简](../bench/tclock_compare/results/20260927-followup.md) | JIT阶段基础/相关5组、18场和36线程native续跑；最终基础/相关11组、三方135场、36线程native/early各360万操作及NORMAL构建通过；没有全量或mutex live重跑 |
| [全链路优化与无锁ticket](../bench/tclock_compare/results/20260927-flow.md) | 第一阶段90场及相关测试单列；最终原子ticket版基础/entry/outer_progress/remote_outer共5组、两种构建、CPU0/20真实ticket selftest、完整135场及36线程nested原生续跑/early各360万操作通过，未跑全量 |
| [spin清理与内联验证](../bench/tclock_compare/results/20260926-cleanup.md) | 基础/entry/shadow/outer共5组，普通及SELFTEST构建、81场性能、36线程nested/early各180万操作及归档审计通过；未跑全量 |
| [最新c1复测至36线程](../bench/tclock_compare/results/20260926-c1-through36.md) | aef982b完整135场通过；runner34项、源码/ELF/峰值及排空审计通过，本次未重跑nested/early或全量 |
| [c1跨node有界批次优化](../bench/tclock_compare/results/20260926-cross-node.md) | 08497ab完整126场、32线程nested/early各160万操作；基础/shadow三组、runner34项、源码/ELF/峰值审计通过，未跑全量 |
| [前版c1预取/诊断/CPU热值优化](../bench/tclock_compare/results/20260926-prefetch-unlock.md) | 77eb9a2完整126场、32线程nested/early各160万操作；相关生产fixture、runner34项、源码/ELF/峰值离线审计通过，未跑全量 |
| [前版c1 NUMA-on优化](../bench/tclock_compare/results/20260926-numa-followup.md) | d439df8完整126场、32线程nested/early各160万操作通过；相关queue/native/entry-scope、runner33项、源码/ELF/峰值离线审计通过；各阶段范围单列 |
| [首轮c1 NUMA/有界批次](../bench/tclock_compare/results/20260926-numa.md) | 完整126场、32线程nested/early各160万操作通过；相关queue/batch/storage/clobber及runner检查通过，预取候选和fixture失败/修正保留在报告中 |
| [前版1/8 cacheline复测](../bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md) | 126场业务/context/排空通过；42场KD中18场实际JIT。基础2组、runner32项及CLI矩阵核对通过；没有新增复杂功能或mutex测试 |
| [捕获队尾准入](../bench/tclock_compare/results/20260924-warmed-peak.md#captured-tail五后继三方90场完成) | 基础及采样/原生MCS共4组、runner32项、SELFTEST两种构建和90场性能通过；20线程nested/early各200万操作，实际JIT1997259/640480次，独立排空及归档审计通过 |
| [per-CPU waiter诊断](../bench/tclock_compare/results/20260924-warmed-peak.md#per-cpu-waiter观察保留) | 基础及batch/storage共4组、两种SELFTEST构建、30场性能通过；保留live近似和即时下溢信号移除的限制 |

原始归档在本地忽略目录`bench/.tmp/`和guest `/root/kdlock-evidence/`，不随Git分发。
构建警告、失败、源码身份及未测项保留在对应报告或归档内。旧模式、被拒绝的
性能候选和旧fixture验收表统一从[历史索引](../bench/tclock_compare/results/HISTORY.md)追溯。
当前采样及ABI分别见[执行流](../docs/JIT_EXECUTION.md#21-热度与角色)和
[寄存器约定](../docs/JIT_REGISTER_ABI.md)。

<a id="spin-ratio-reset-validation"></a>
### 2026-09-27 MCS右移/清零比例窗口

在`8e3d52e`基础上复用现有per-CPU获取/MCS计数；MCS达到512时比较
`(spin_entries >> 9) < 2`，随后清零两计数并采一次CPU时钟。
删除快照、差值和首次比例豁免；新参数及完整规则见
[执行流](../docs/JIT_EXECUTION.md#21-热度与角色)。

guest `6.1.159-kdclobber2`核对捕获基线和空闲状态后，NORMAL provider构建通过，
保留原有objtool换栈/返回告警。执行
`make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py spin/test_spin_nondelegated.py'`，
基础两组及两个相关驱动共4组通过。覆盖511/512触发、1023通过/1024拒绝、首批拒绝与恢复、
比较后两计数清零、busy跳过后重试、CPU隔离及原有mutex窗口；13项错误策略变异均被检测。
原生pending/MCS在1/2/3/8线程下分别完成50,000/100,000/150,000/400,000次，pin及所有权检查通过。
`python3 bench/tclock_compare/test_direct.py`的35项通过，包含新参数与历史百分比记录分组。

monitor确认`pre_static_boot_20260915`快照后，直接运行器执行
`--functional --backends kdlock --cachelines 1 --threads 8 36 --repeats 1 --iterations 100000`，
保持默认`spin_entry_ratio_limit=2`、NUMA-on、KD批上限512和prefetch=2；没有用比例绕过来获得JIT。
8线程完成800,000次、实际JIT正文797,542次；36线程跨guest两node完成3,600,000次、
实际JIT正文3,590,196次。两场业务、IRQ/preempt、retirement及排空通过。
运行器加载独立观测provider并使用daemon；`mutex_jit=1`为已记录的provider默认值，
本次负载仅执行spin，没有mutex live、nested/early、全量测试或三方性能矩阵。

NORMAL ELF离线检查确认删除16字节per-CPU快照对象；由于对齐填充，整个per-CPU section大小未变。
比例计算替换为右移/比较及两次GS清零写入；原生直接获取、直接解锁和clobber解锁的指令/relocation未变。
这不是性能无回退证明；此前百分比策略的历史成绩不能当作本次复测。

命令、日志、冻结源码、NORMAL与观测模块和排空证据在本地忽略目录
`bench/.tmp/ratio-shift-20260927/`；guest保留
`/root/kdlock-evidence/ratio-shift-20260927/`与`/root/kdlock-evidence/ratio-shift-live-20260927/`。
NORMAL模块SHA256：`5e704915875726728b103495785607816a5c49c10761aeba1b4899b023a17807`。
构建/unit归档SHA256：`881501666ec1292a162f7276e5dec7f47efbb0f8f8ded580aef2d0985d4e7d10`；
live归档SHA256：`06c0f27d07aaa165293f810b2c7c10822d7936785f94215466a4e52c2546a242`。

### 2026-09-27 KD实现文件拆分

从`61a24ea`整理KD kernel和JIT实现，文件职责与阅读顺序见[代码地图](../docs/CODE_MAP.md)。
测试、benchmark和TCLock没有拆分；五个生产源码读取驱动改用已有`read_source`展开
私有`.inc`，observer补丁及其路径断言跟随被移动的KD代码。

guest `6.1.159-kdclobber2`核对捕获基线后，NORMAL provider构建通过，保留原有
objtool换栈/返回告警。基础两组及`spin/test_spin_cold.py`、`test_spin_direct.py`、
`test_spin_entry.py`、`test_spin_nondelegated.py`、`test_spin_preempt.py`共七组通过；
ticket检查380项，原生pending/MCS在1/2/3/8线程下分别完成50,000/100,000/150,000/400,000次。
translator四组`admission/test_context_policy.py`、`test_context_guards.py`、
`codegen/test_jit_diagnostics.py`、`test_jit_body_witness.py`共160项通过。
observer只运行`CachelineTests.test_provider_isolation_and_incompatible_source`，通过。

两个kernel编译入口递归展开后，非注释token与旧版一致；九个迁移、六个保留的Python
定义以及16条抽出的汇编生成语句保持AST一致。前后NORMAL模块的5个可执行section
共91,922字节、320个函数的地址/大小/指令及4,208个代码relocation的实际目标均相同。
差异限于新文件名、诊断行号、相同字符串的地址偏移及build身份，不据此宣称本次实测吞吐。
完整命令/输出、源码核对及ELF证据在
本地忽略目录`bench/.tmp/organize-20260927/`，guest冻结源码和前后NORMAL模块在
`/root/kdlock-evidence/organize-20260927/`。本次没有加载模块、运行daemon、修改内核、
启用mutex JIT或执行性能矩阵；没有把历史live/性能结果当作本次重跑。

最终清理新`.inc`末尾多余空行后再次构建，整ELF相同的预期未成立；逐section检查
确认仅非装载`.BTF`元数据改变，所有其他section相同，前述代码/relocation核对仍适用。
两次模块及检查记录均保留，没有因这一格式调整重复unit或live。
NORMAL最终模块SHA256：`f1a8232df997816fcc1f4809a084c261c0decbdc5e54f45d71b499e7f236272b`。
最终guest归档SHA256：`f7507566cfc171e36642d158f5663f564ba81c637dbb59fd93c85ee220e42e59`。

## 单元检查

代码修改后可直接运行[默认三轮性能测试](../bench/tclock_compare/README.md#准备与运行)，
使用其内置业务、IRQ/preempt、JIT 和排空检查。独立单元、SELFTEST、`--functional`
及小矩阵按需选择，不作为性能测试的固定前置步骤。2026-09-23 用户提高性能测试
轮次用于观察波动；功能模式仍显式使用 `--repeats 1`，已有单轮证据保留原口径。

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
| 显式irqsave/irq/bh接口、flags类型及上下文拒绝 | `spin/test_spin_irq.py`、`spin/test_spin_cold.py`、`admission/test_context_policy.py`；真实内核检查见[IRQ/BH消费者](kernel/spin/irq_api/README.md) |
| continuation 分配、容量、回收与最终恢复 | `spin/test_spin_storage.py`、`execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `spin/test_spin_entry.py`检查实际ticket CAS；`execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py`检查路由/ACK |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热表、获取/MCS计数、频率/比例窗口及准入恢复 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| 冷热调用壳与通用解锁 ABI | `spin/test_spin_cold.py`、`codegen/test_spin_paired_jit.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py`、`execution/test_jit_entry_scope.py` |
| CALL/hostcall的SP、源返回字和公共完成出口 | `codegen/test_jit_body_witness.py`、`codegen/test_spin_paired_jit.py`、`codegen/test_clobber_abi.py`；本轮范围见[重复操作精简](../bench/tclock_compare/results/20260927-followup.md) |
| 范围选择与离线证据 | `infrastructure/test_regression.py` |

共享源码读取/头文件过滤位于 `unit/infrastructure/source_text.py`，不再依赖旧 gate
测试。保留的 mutex/remote 等日志 oracle 检查身份、owner、ACK、顺序和最终副作用；
合成日志通过不表示当前 live 覆盖。生产代码 fixture 同样不证明真实内核并发。

## Live 检查

IRQ/BH 变体使用[专用消费者模块](kernel/spin/irq_api/README.md)，检查本CPU上下文
和同锁混合原生竞争，JIT=0；它不是下面的基础生命周期 case 或实际 JIT 验收。

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
为外锁提前释放，仅 KD cacheline 允许后两项。当前只保留adaptive，功能正例可显式使用
`--spin-entry-ratio-limit 0`关闭比例过滤，但原生队头资格及CPU/单锁热度仍生效，实际JIT检查不放宽；
未重跑的功能场景不记为通过。
性能中的原生完成须保留 NO_JIT 标记。少线程可经 MCS 升温，但不保证出现可代理后继；
不能只凭线程数判断是否执行 JIT。具体有效性规则见运行器文档。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 spin_entry_selftest=1`
检查热表碰撞及满容量时既有身份和真实 owner 仍保留、mutex 等待 CPU 迁移及 owner ACK；这不执行 JIT。
构建方式及控制参数见 [provider](../kernel_module/README.md)。保持 normal 与
SELFTEST 构建分开，不替换加载中的模块，完成后必须排空和正常卸载。

## 历史验证与尚未覆盖边界

各批实测范围以本页链接报告的冻结源码和原始结果为准。continuation 容量、最终恢复汇编、
节点先复用、共享根包及延迟 ACK 的历史 fixture 通过，不等于当前真实内核多 CPU
远端 native/无锁 relay 强制时序已覆盖。mutex JIT、极端容量/取消组合及访问时
动态 guard 的剩余限制见 [TODO](../docs/TODO.md)。

| 历史阶段 | 冻结记录 |
| --- | --- |
| continuation 交接、ELF 布局和退休检测 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#continuation-validation) |
| 四线程 ticket 和抢占配对 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#four-thread-ticket-validation) |
| 已撤回的 MCS 边界准入实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-admission-validation) |
| 已撤回的准入时间域实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#admission-clock-validation) |
| 回退后的单元与 plain/nested/early 功能 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-recovery-validation) |

[性能阶段索引](../bench/spin_cacheline/results/HISTORY.md)保留原始报告入口；
更早测试见 [VALIDATION](../docs/VALIDATION.md)。旧 hook/gate 脚本只适用于匹配的
历史 checkout；历史操作命令不作为当前运行指令。
