# 测试用例总览（当前版）

本文件汇总当前仓库中可用的测试入口与执行方式，便于按类别快速运行。  
所有 live 测试仍采用 `tests/regression.py` 的统一选择机制；`run_all.sh` 只是参数透传封装。

更新时间：2026-09-11

## 1. 统一入口

- `bash tests/run_all.sh --list`
  - 查看当前 suite/case 定义与覆盖关系。
- `bash tests/run_all.sh --suite <suite>`
  - 例如 `--suite core`、`--suite spin`、`--suite mutex-signals`。
- `bash tests/run_all.sh --case <case>`
  - 直接按单例执行某个 case（例如 `--case mode-5`、`--case parallel-drain-1`）。
- `bash tests/run_all.sh --suite <suite> --dry-run`
  - 仅显示将执行的完整命令，不改环境不运行。
- `KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite <suite>`
  - 当前 live 测试入口，先确认 recover snapshot 后运行。
- `bash tests/run_all.sh --case mode-4`
  - 每个 `--case` 独立指向一个 case；若要执行多项请重复传入多个 `--case`。

> 注意：live 运行会在每个 case 后做 dmesg/模块/drain 检查并产生日志证据，详见
> [证据流程](JIT_EXECUTION.md#执行与证据)。

## 1.1 当前使用的 Recovery Guest

当前回归使用的 Recovery Guest 是宿主机 `~/vm/qemu-scripts/run_vm.sh recovery` 启动的
同名内核环境（脚本当前目录为 `/home/eric/vm/qemu-scripts`），其关键特征是：

- 前台运行 QEMU，宿主侧与 Guest 源码同路径：`/root/host_fs/kdlock`
- Recovery 模式使用 guest 内部 ext4，非共享 9p，因此修改前要按文件 hash 比较再同步
- 40 vCPU、28 GiB、双 NUMA；内核启动参数与基线要求包含 `nokaslr`
- 动态抢占为 `(voluntary)`，按已记录基线核对 Linux 为 `6.1.159`（Build ID：
  `6f9f2e9fec382e97f620553793aa90b527a30af5`）
- Recovery 专用，不支持默认“无确认地启动快照”：必须先 `info snapshots` 确认 tag
  存在，再使用 `loadvm <tag>`（或按历史流程 `savevm <tag>`）

常用确认顺序（在宿主机）：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery

# 另开一个终端：
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
# 在 HMP 输入：
# info snapshots
# savevm pre_kdlock_test   # 或按你的已命名 tag
```

Guest 中确认并进入测试模式时，按项目约定设置：

```bash
export KDLOCK_RECOVERY_CONFIRMED=1
```

并在 case 执行前满足：

- 无并发 `daemon/klock_test` 运行者
- 无残留模块（或可安全回收）
- SSH 可达，`/tmp/qemu-serial.log` 与 monitor 可见
- `tests/run_all.sh --list` 与 `--dry-run` 的计划核对通过

## 1.2 Recovery 与 Normal 模式区别

项目当前在日常回归时默认使用 recovery 模式，主要与 normal 模式的区别如下：

- 文件系统路径
  - recovery：guest 内部为本地 ext4，路径 `/root/host_fs/kdlock`，**不会**实时反映 host 的编辑。
  - normal：使用 9p 共享，路径同样是 `/root/host_fs/kdlock`（实际来自 host 映射），改动会即时可见。
- 数据一致性
  - recovery：建议按 hash 比对后再 `scp` 同步，避免改动误差；可做快照回退。
  - normal：适合快速迭代源码与脚本验证，但不建议直接承载高风险 live 测试。
- 快照与恢复
  - recovery：支持 `savevm/loadvm` 的快照流程；执行 live case 前需确认可恢复快照，并设置
    `KDLOCK_RECOVERY_CONFIRMED=1`。
  - normal：通常不保证快照恢复流程可用，不能把 `loadvm` 替代正常启动；快照确认逻辑不作默认前置。
- 运行风险边界
  - recovery：用于高风险 live case，崩溃可按 snapshot 回退；重启不自动恢复快照，仍需确认恢复链路。
  - normal：用于更轻量检查或准备阶段（例如脚本草稿、静态命令验证），不作为复杂 JIT 的默认执行环境。
- 测试策略
  - recovery：`tests/run_all.sh` / `tests/test_*.sh` 的 live 入口默认按本模式前提准备。
  - normal：适合开发环境的快速试运行，复杂 case 建议全部在 recovery 下执行，避免污染长期状态。

一句话总结：**recovery 用于可回滚的高危验证，normal 用于开发便捷与轻量校验；内核钩子/JIT 的真实验证应优先放在 recovery。**

## 2. `regression.py` 套件定义

`tests/regression.py --list` 当前输出如下（含 64 个 suite case）：

- baseline（3）：`module`、`pipeline`、`mutex-off`
- native-controls（2）：`control-0`、`control-3`
- spin（3）：`mode-2`、`mode-7`、`mode-8`
- mutex（2）：`mode-4`、`mode-5`
- hostcall（2）：`mode-2`、`mode-5`
- registers（8）：`registers-0-1`、`registers-3-1`、`registers-1-2`、`registers-4-2`、`registers-1-3`、`registers-4-3`、`registers-8-2`、`registers-8-3`
- admission（12）：`context-spin`、`context-mutex`、`context-mixed`、`context-irqsave`、`context-bh`、`context-percpu`、`context-percpu-reg`、`context-percpu-flow`、`context-percpu-spill`、`context-percpu-implicit`、`context-percpu-rotate`、`context-percpu-cmov`
- spin-native（9）：`registers-8-2`、`registers-8-3`、`native-spin-outer-dependency`、`native-spin-acquired`、`virtual-ticket-refusal`、`shadow-capacity`、`virtual-context-refusal`、`virtual-node-refusal`、`late-spin-policy`
- mutex-native（10）：`registers-4-2`、`registers-4-3`、`native-mutex-outer-dependency`、`native-4-4`、`native-mutex-depth`、`native-mutex-stack-change`、`late-mutex-policy`、`parallel-drain-0`、`parallel-drain-1`、`parallel-node-pressure`
- spin-remote（7）：`node-physical-8-0`、`node-physical-8-1`、`node-remote-plain`、`remote-multi-b`、`remote-late-2`、`remote-late-3`、`remote-late-4`
- mutex-signals（10）：`waiter-usr1`、`waiter-kill`、`native-peer-1`、`native-peer-3`、`waiter-race-int-cancelled`、`waiter-race-int-acquired`、`waiter-race-int-either`、`waiter-race-kill-cancelled`、`waiter-race-kill-acquired`、`waiter-race-kill-either`
- protocol（4）：`mixed-spin`、`mixed-mutex`、`kernel-task-local`、`kernel-task-cross-numa`
- mutex-parallel（3）：`parallel-drain-0`、`parallel-drain-1`、`parallel-node-pressure`
- core（5）：`mode-2`、`mode-7`、`mode-8`、`mode-4`、`mode-5`
- extended（64）：覆盖除覆盖性冗余用例外的完整增强集合

### 覆盖替代关系（diagnostic覆盖）
- `mode-0` 由 `mode-2` 覆盖
- `mode-1` 由 `mode-8` 覆盖
- `mode-3` 由 `mode-5` 覆盖
- 深层 node 深度 `1/2` 的同位测试由 `8` 层位例覆盖
- `parallel-shared-cpu` 由 `parallel-node-pressure` 覆盖
- `native-1-4` 由 `virtual-ticket-refusal` 覆盖
- `native-1-3` 由 `registers-1-3` 覆盖
- `native-4-3` 由 `registers-4-3` 覆盖

## 3. case 与实现脚本映射

> 下表是当前 `CASES` 映射的可读版，便于快速从 case 追溯到执行脚本。  
> 若需要完整命令可直接执行：`python3 tests/regression.py --dry-run --case <case>`。

| Case | 脚本 | 说明 |
| --- | --- | --- |
| `module` | `test_01_module_load.sh` | 基础模块加载/卸载与 `/dev/kd_dev` |
| `pipeline` | `test_02_jit_engine.sh` | 入队-翻译-回写 pipeline（无 JIT 执行） |
| `mutex-off` | `test_05_mutex.sh` | `mutex_jit=0` 下的 mutex 兼容路径 |
| `mode-0` `mode-1` `mode-2` `mode-3` `mode-4` `mode-5` | `test_09_jit_execution_modes.sh` | spin/mutex 模式入口与 JIT 执行能力校验 |
| `mode-6` `mode-7` `mode-8` | `test_04_spinlock.sh` | spin 深度场景与多锁重入路径 |
| `registers-*` | `test_10_native_resume.sh` | CALL 续跑、寄存器恢复与 native 返程检查 |
| `native-spin-acquired` `native-spin-outer-dependency` `native-mutex-outer-dependency` `native-mutex-depth` `native-mutex-stack-change` `native-4-4` `virtual-*` `shadow-capacity` `late-*` `node-physical-*` `remote-*` `waiter-*` | `test_10_native_resume.sh` / `test_21_remote_depth.sh` | 原生续跑与拒绝边界（mode、CPU 拓扑、信号/栅栏） |
| `native-peer-1` `native-peer-3` | `test_19_mutex_signals.sh` | 原生 peer 与互斥 owner/combiner 关系 |
| `parallel-drain-0` `parallel-drain-1` `parallel-node-pressure` | `test_23_mutex_parallel_native.sh` | 并行 native 与独立队列压力 |
| `context-*` | `test_12_context_native_only.sh` | 上下文不兼容路径，必须保持 native |
| `mixed-spin` | `test_17_spin_native_protocol.sh` | spin/mutex 混合原生互斥竞争 |
| `mixed-mutex` | `test_11_mutex_native_protocol.sh` | mixed mutex 互斥竞争 |
| `kernel-task-local` `kernel-task-cross-numa` | `test_22_mutex_task_lifecycle.sh` | 真正的 task/RCU/ACK 生命周期 |

## 4. `tests/test_*.sh` 主要测试脚本

- `test_01_module_load.sh`：验证模块加载卸载和设备节点
- `test_02_jit_engine.sh`：pipeline 预检查，不执行 JIT 临界区
- `test_04_spinlock.sh`：spin 多模式验证（含翻译、续跑与边界）
- `test_05_mutex.sh`：`mutex_jit=0` 下保证走 native mutex
- `test_07_mutex_jit.sh`：mode 3 的独立高压重入/并发执行（历史优化版）
- `test_08_mutex_jit_modes.sh`：mode4/5 与信号场景，含高压验证
- `test_09_jit_execution_modes.sh`：mode0-5 的翻译入口与要求检查
- `test_10_native_resume.sh`：native 续跑与拒绝路径（多 env 组合）
- `test_11_mutex_native_protocol.sh`：native waiter/mutex 共享协议
- `test_12_context_native_only.sh`：上下文不匹配原生保持不翻译
- `test_13_spin_shadow_capacity.sh`：spin shadow 容量边界（默认不进日常）
- `test_14_spin_frame_depth.sh`：spin 嵌套帧深度（0/1/2/8）
- `test_15_spin_native_gate.sh`：spin native gate 专用回归
- `test_16_spin_entry.sh`：spin 路由/entry 计数点行为
- `test_17_spin_native_protocol.sh`：spin 与 native 共同排队边界
- `test_18_spin_routing.sh`：hook 路由 determinism
- `test_19_mutex_signals.sh`：信号取消下的 owner/combiner 协议
- `test_20_remote_outer.sh`：remote outer 自研路径与原 owner 依赖
- `test_21_remote_depth.sh`：远端深链（1–8 执行体）场景
- `test_22_mutex_task_lifecycle.sh`：task life-cycle 与 ACK 实名核验
- `test_23_mutex_parallel_native.sh`：并行 native peer 与独立队列压力

## 5. 辅助脚本（tests/*.py）

- `tests/regression.py`：case 定义与运行调度核心
- `tests/regression_evidence.py`：evidence 与快照归档
- `tests/verify_evidence.py`：离线校验（建议每次 run_all 后执行）
- `tests/*_protocol.py`：用于观察器和流程断言
  - `mutex_signal_protocol.py`
  - `native_waiter_signal_protocol.py`
  - `native_waiter_signal_race.py`
  - `mutex_parallel_protocol.py`
  - `mutex_shadow_protocol.py`
  - `spin_gate_protocol.py`
  - `spin_node_protocol.py`
  - `spin_frame_protocol.py`
  - `spin_acquired_protocol.py`
  - `native_register_protocol.py`
  - `native_ooo_protocol.py`
  - `remote_depth_protocol.py`
  - `remote_outer_protocol.py`
  - `source_depth_protocol.py`
  - `readmission_protocol.py`
  - `source_retirement.py`
  - `source_session_child.py`
  - `cpu_placement.py`
  - `audit_context_spills.py`
  - `audit_spin_native.py`

## 6. 单元测试（`tests/unit`）

### C 单测
- `test_tail_encoding`
- `test_mutex_transition`
- `test_jit_call_policy`
- `test_exec_frame`
- `test_spin_node_count`
- `test_control_call`
- `test_daemon_policy`

### Python 单测（当前默认列表）
- `test_hostcall_codegen.py`
- `test_segment_codegen.py`
- `test_jit_diagnostics.py`
- `test_context_policy.py`
- `test_spin_shadow.py`
- `test_cs_oracle.py`
- `test_text_regions.py`
- `test_spin_gate.py`
- `test_spin_entry.py`
- `test_spin_routing.py`
- `test_mutex_signal_protocol.py`
- `test_native_ooo_protocol.py`
- `test_native_after_outer.py`
- `test_hotlock_sampling.py`
- `test_mutex_outer_progress.py`
- `test_spin_outer_progress.py`
- `test_remote_outer.py`
- `test_remote_outer_protocol.py`
- `test_remote_depth_protocol.py`
- `test_remote_deferred_protocol.py`
- `test_spin_frame_protocol.py`
- `test_exec_capacity.py`
- `test_spin_node_protocol.py`
- `test_kernel_baseline.py`
- `test_native_registers.py`
- `test_jit_body_witness.py`
- `test_context_spill_audit.py`
- `test_context_memory.py`
- `test_context_guards.py`
- `test_jit_entry_scope.py`
- `test_exe_registry.py`
- `test_source_lifetime.py`
- `test_source_depth_protocol.py`
- `test_mutex_resources.py`
- `test_mutex_parallel_protocol.py`
- `test_mutex_stack_protocol.py`
- `test_regression.py`

执行方式：
```bash
make -C tests/unit run
# 或选择性执行（主机内）
make -C tests/unit run TESTS='test_exec_frame test_daemon_policy' PY_TESTS='test_spin_shadow.py'
```

## 7. 核心 workload 源文件（`tests/kernel`）

- `spin_*_workload.c` / `spin_*_selftest.c`：spin 场景工作负载与自检
- `mutex_*_workload.c` / `mutex_*_selftest.c`：mutex 关键路径工作负载与自检
- `native_register_workload.c`、`native_waiter_signal_workload.c`、`native_ooo_workload.c`：native 协议专项
- `remote_outer_workload.c`、`remote_depth_workload.c`：远端/多执行者场景
- `exec_capacity_probe.c`、`spin_gate_workload.c`、`spin_node_trace.c` 等：容量与 trace 级别观测

## 8. 一次性执行建议（顺序）

1. `bash tests/run_all.sh --list`
2. `bash tests/run_all.sh --suite baseline --dry-run`（确认 baseline case）
3. `bash tests/run_all.sh --suite core --dry-run`
4. `KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite baseline`
5. `KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite core`
6. `python3 tests/verify_evidence.py <evidence_dir>`

### 常用 case 快速入口
- spin/mutex 关键链：`--case mode-2`, `--case mode-7`, `--case mode-4`, `--case mode-5`
- native 续跑：`--case registers-4-2`, `--case native-4-4`, `--case registers-8-3`
- 信号/中断：`--case waiter-usr1`, `--case waiter-race-int-cancelled`
- 复杂并行：`--case parallel-drain-0`, `--case parallel-node-pressure`

## 9. 与仓库其他文档的关系

- `PROJECT_GUIDE.md`：项目启动与运行流程
- `JIT_EXECUTION.md`：每章中 `usage` 与执行顺序
- `AGENTS.md`：测试边界、证据与合规规则
- `VALIDATION.md`：历史证据与关键验收结果
