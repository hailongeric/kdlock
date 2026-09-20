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
