# 当前测试入口

构建、单元、模块和性能测试只在 recovery guest 执行，先读
[操作手册](../docs/AGENTS.md)。当前使用显式 KD 单锁字 API；普通 Linux 锁完成
不能作为 KD JIT 证据。按修改范围选择下面的单元、功能或性能入口。

## 最近验证与证据

结果按冻结源码分别记录，不能将不同阶段的通过项合并为一次当前版本全量验收。

| 批次 | 已完成 | 范围与入口 |
| --- | --- | --- |
| 节点槽按CPU排列（已拒绝） | 5组通过；W=1 SELFTEST=1/0共22条既有objtool警告；12场、16800000操作正确排空，全部实际JIT/16472076次正文 | [本轮报告与全部四组三轮](../bench/tclock_compare/results/20260924-contention-ratio.md)。c16/20中位对local提高2.15%，但c16/8仍低0.57%、对原基线低8.73%；12项输入恢复913fe2e。nested/early计划仍UNRUN，未测其他线程或三方168场 |
| 后继头部预取（已拒绝） | 基础2组及batch fixture共3组通过；生产W=1保留11条既有objtool警告；12场、16800000操作正确排空，全部实际JIT/16487415次正文 | [本轮报告与全部四组三轮](../bench/tclock_compare/results/20260924-contention-ratio.md)。20线程小幅改善，但8线程保护未解决；三个输入恢复91efe4a，未测其他线程、三方168场或nested/early |
| c16/8匹配profile与当前pct0控制 | 原基线/local各3场、各24000000操作正确排空，实际JIT23673764/23275406次；199Hz采样工具/数据/地址校验通过、零丢失；另3场pct0控制2400000操作/2328528次JIT正确排空 | [匹配分析](../bench/.tmp/ratio-20260924/profile-matched-c16-t8-observed.md)。等待样本增加不确定回退原因；当前代码门槛0没有恢复原基线。1M诊断与100k控制分开，不作为完整性能保护通过 |
| MCS/非MCS补集计数（已拒绝，恢复入口计数） | 8组及10项采样错误变体、运行器26项通过；W=1 SELFTEST=1/0保留22条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26379938次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)、[全部14组三轮](../bench/.tmp/ratio-20260924/complementary-results.md)。c16/8、c16/2中位比原基线低8.30%/10.74%，4线程收益也弱于local-access；21项输入恢复ecc515f，未运行完整三方168场或nested/early |
| 统一128次采样/比较（已拒绝，恢复512次） | 3组单元及10项采样错误变体、运行器26项通过；生产W=1保留11条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26715960次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)、[全部14组三轮](../bench/.tmp/ratio-20260924/unified128-results.md)。4线程中位比local-access低约10%，c16/8原基线保护仍失败；六项输入恢复24896bd，未运行完整三方168场或nested/early |
| 节点notification区域128字节隔离（已拒绝） | 基础2组及storage/batch/wait/shadow共6组通过，5项storage错误变体检出；W=1 SELFTEST=1/0共22条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26291925次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)。节点256字节未改善8线程且损害16/20；六项布局/fixture文件恢复d253d23/f71dc2e的128字节节点、64/65通知偏移，批次上限1024；未运行完整三方168场或nested/early |
| spin批次上限256（已拒绝，恢复1024） | 基础及直接相关fixture共4组通过；仓库runner检出early/late两项cap变体及9项既有变体；生产W=1保留11条既有objtool警告；12场、16800000操作正确排空，全部实际JIT/16498308次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)。两次直接脚本调用的导入失败原样保留，修正调用入口后通过；8/20线程各三轮，c16/8无明显收益且20线程中位降低约2.4%–2.5%，五项代码/fixture文件恢复f71dc2e；未测其他线程或完整矩阵 |
| 本地busy保护与已pin入口专化（实验检查点） | 基础2组、采样fixture/10项错误变体、抢占路径fixture通过，共4组；运行器26/26；两次W=1构建共22条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26331389次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)、[冻结benchmark机器码证据](../bench/.tmp/ratio-20260924/local-access-frozen-codegen.md)。保持全入口计数及原比例政策，局部访问去CMPXCHG，已pin入口去通用抢占分支；c16/8等保护仍失败，未运行完整三方168场、nested/early或全量功能 |
| 冷原生快速成功不计数（已拒绝） | 基础2组、采样fixture/10项错误变体、冷路由套件和1/2/3/8线程混合原生用例通过；运行器27/27；生产W=1保留11条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26372390次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)。策略mcs_entry_ratio512_cold_failed；省略冷原生首次CAS成功计数，其他入口不变；无一致收益，冻结归档后恢复f320d9f。原基线性能保护仍失败，未运行完整三方168场、nested/early或全量功能 |
| spin节点数组128字节对齐 | 基础2组及存储fixture、5项存储错误变体检出；W=1的SELFTEST=1/0构建完成，共22条既有objtool警告；42场、32400000操作正确排空，30场实际JIT/26333961次正文 | [独立报告](../bench/tclock_compare/results/20260924-node-array-alignment.md)。数组对齐提升至128，节点大小128及通知偏移64/65不变；16/20线程相对simple512恢复约8%–9%，原基线保护仍失败，未运行三方168场或全量功能 |
| 简化512次采样/比例（EXPERIMENTAL检查点） | 基础2组、采样fixture/10项错误变体、运行器26项及W=1构建通过，保留11条既有objtool警告 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)、[原始日志](../bench/.tmp/ratio-20260924/checks-simple512.log)。近似IRQ采样、两个快照、spin达到512次；simple512-fixed42场、32400000操作正确排空，30场实际JIT/26327355次正文；性能保护失败，未运行该版本三方168场 |
| 比例准入/缩短spin单锁批次（历史b83f551检查点） | 基础单元2组、采样fixture及72项错误变体检出；W=1的SELFTEST=1/0构建完成，共22条既有objtool警告；42/42场、32400000操作正确排空，30场实际JIT、26363560次正文 | [本轮报告](../bench/tclock_compare/results/20260924-contention-ratio.md)。覆盖获取/MCS原始计数、128次采样、512次比例窗口、初始两低确认、冷却/保留与spin513/12.5亿、mutex1025/25亿边界；首次测试变体编译失败及修订日志均保留。c1/c16、1/2/3/4/8/16/20线程各三轮仅KD adaptive；性能保护失败，未运行该检查点三方168场或全量功能 |
| spin诊断槽128字节区域隔离 | 定向单元5组、64项采样/4项存储错误变体检出；W=1构建完成并保留11条既有objtool警告；24/24场、21000000操作正确并排空，全部有实际JIT | [独立报告](../bench/tclock_compare/results/20260924-diagnostic-pairs.md)。ratio100/batch128、c1/c16、3/4/8/20线程各三轮；相对匹配慢候选改善，但原基线的高线程性能保护仍未完成，未重跑全量功能 |
| MCS8/CPU400万组合 | 168/168场、129600000次操作通过并排空；基础/采样单元3组、23项错误变体检出；84场KD中60场实际JIT | [历史报告](../bench/tclock_compare/results/20260923-mcs8-cpu4m.md)。该轮保留用户指定组合，spin与mutex CPU窗口分开；三方1/2/3/4/8/16/20线程各三轮，未重跑全量功能 |
| adaptive 窗口/MCS间隔诊断 | 实际196场：195场有效，1场20线程零JIT拒绝；该候选余20场未执行，全部已执行场排空；基础及参数边界检查通过 | [完整报告](../bench/tclock_compare/results/20260923-adaptive-windows.md)。6个独立候选、1个组合及前后默认基线，完整配置各三轮；所有候选均未保留，不能记为216/216通过 |
| adaptive 单锁计数阈值诊断 | 32/128/1024/恢复32共96/96场、84000000次操作通过并排空；基础和阈值定向检查通过 | [完整结果](../bench/tclock_compare/results/20260923-adaptive-threshold-sweep.md)。c1/c16、3/4/8/20线程各三轮，两个候选未满足性能保留条件，该历史轮次恢复阈值32；未重跑其他后端或全量功能 |
| 默认 heat caller 完整三轮 | 56 配置 × 3 轮，168/168 场、129600000 次操作通过并排空；84 场 KD 中 60 场实际 JIT | `39b0e7c` 加冻结工作树；包含 MCS 发布采样、通用解锁、batch 元数据精简和 continuation 错位布局。[完整报告](../bench/tclock_compare/results/20260923-spin-default-heat-full3.md)；该批未重跑单元、nested/early、RCUHT 或 PMU |
| 单线程/20线程优化 | 定向单元 3/3 组、3 项错误变体检出；1/20线程三轮性能 48/48；nested/early 双模式功能 4/4；长批次布局对照 24/24 | [调查与证据](../bench/tclock_compare/results/20260923-spin-single-hot-balance.md)。短批次单线程中位数曾比同期基线低约 5%–6%；长对照未复现一致下降，不据此声称统计等价 |
| 通用 clobber 解锁 | 基础及相关单元 6/6 组；冻结运行器 22/22 项；性能 108/108；nested/early 双模式 4/4 | [ABI 验证](../bench/tclock_compare/results/20260923-spin-generic-unlock.md)。使用删除旧 on/off 选项前的版本，冷/热均验证 SP/IP/BP 和宽 clobber |
| MCS 发布处更新 CPU 热度 | 基础及相关单元 5 组、21 项错误变体；运行器 22 项；1/2/3/20线程功能 8 场通过 | [冻结证据](../bench/.tmp/spin-mcs-entry-20260923.tar.gz)；2/3线程的实际入队与采样计数严格相等。该批未重跑性能矩阵 |
| 默认 heat caller 运行器清理 | 运行器 23/23、基础单元 2/2；KD workload 构建与导入检查通过 | [验证摘要](../bench/.tmp/spin-default-heat-20260923/verified.json)、[归档](../bench/.tmp/spin-default-heat-20260923.tar.gz)。该批未加载模块或运行 live；后续完整矩阵见上方对应行 |

原始归档位于本地忽略目录 `bench/.tmp/` 和 guest `/root/kdlock-evidence/`，
不随 Git checkout 分发。MCS-entry 归档 SHA256 为
`79f25848399ba67099b820bab68d918153a98fd8ac458208aca7d37e2a7bd271`；
default-heat 清理归档为
`961cd0b2b183f12705d0047bedf1966376fe2a58e7334d489544d81b31895b9f`。
构建警告、首次失败、源码身份和未测项保留在相应报告或归档内。

当前采样语义与 ABI 分别见 [热度与角色](../docs/JIT_EXECUTION.md#21-热度与角色)和
[寄存器约定](../docs/JIT_REGISTER_ABI.md)，本页不复制策略参数历史。
旧调用壳、队列门槛和热表候选的结果统一见
[历史索引](../bench/tclock_compare/results/HISTORY.md)。

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
| continuation 分配、容量、回收与最终恢复 | `spin/test_spin_storage.py`、`execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py` |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热表、获取/MCS计数、频率/比例窗口及准入恢复 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| 冷热调用壳与通用解锁 ABI | `spin/test_spin_cold.py`、`codegen/test_spin_paired_jit.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py`、`execution/test_jit_entry_scope.py` |
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
为外锁提前释放，仅 KD cacheline 允许后两项。固定准入功能正例要求真实 JIT；
性能中的原生完成须保留 NO_JIT 标记。少线程可经 MCS 升温，但不保证出现可代理后继；
不能只凭线程数判断是否执行 JIT。具体有效性规则见运行器文档。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 hotlock_mode=observe spin_entry_selftest=1`
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
