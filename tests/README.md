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
| 单锁字入口和 ticket | `spin/test_spin_direct.py`、`spin/test_spin_entry.py` |
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

spin 通知偏移仍为 64/65，request 池仍为每 CPU 9216 字节；取消独立 JIT context
池。mutex 1024 项静态映射减少 16 KiB。上述是结构布局结果，不代表吞吐收益。

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
