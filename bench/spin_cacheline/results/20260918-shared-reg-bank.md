# 2026-09-18：共享 JIT 寄存器 backing 的定向对照

本轮让 `Stack_R11`–`Stack_R15`、`Stack_RSP`、`Stack_RBP` 直接使用请求的
`pt_regs` 字段，删除 wrapper 入/出口重复搬运。物理 R11 固定作包基址，原
block 计数移至独立栈槽。CPU 中的当前逻辑值仍须物化，队列、准入、owner/ACK
和原生恢复协议不变。实现见 [ABI](../../../docs/JIT_REGISTER_ABI.md#3-pt_regs-输入输出约定)，
功能验收见 [测试记录](../../../tests/README.md#shared-register-bank)。

## 吞吐与实际 JIT

新旧各 12 场，**24/24 正确并排空**；共 9,600,000 次完整操作，旧/新版本分别
有 2,682,215 / 2,665,885 次测量期返回后的 JIT 正文。所有会话 JIT 非零，生成物
ABI、发布状态、全部 cacheline 数据、worker CPU/完成数和最终退休状态均通过。

以下为三轮中位数，吞吐单位 Mops/s；JIT 比例也独立取中位数。

| cacheline | caller ABI | 改造前 | 改造后 | 变化 | 前 JIT | 后 JIT |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | legacy | 0.8099 | 0.8305 | +2.55% | 52.22% | 55.09% |
| 1 | clobber | 0.7747 | 0.9047 | +16.78% | 58.17% | 56.13% |
| 16 | legacy | 0.7468 | 0.7434 | −0.45% | 56.61% | 52.88% |
| 16 | clobber | 0.7240 | 0.7245 | +0.08% | 58.14% | 57.20% |

1 cacheline 的 clobber 新版本单次结果为 0.8302–1.0509 Mops/s，波动明显。
旧版本整批先跑，新版本整批后跑，每组仅三次；只有组内两个 caller ABI 的
顺序交替，**没有交替切换新旧实现**。JIT 比例也未固定，不能把第一组的上涨
归因为减少拷贝，更不能通过代理覆盖下降宣称提速。16 cacheline 两种 ABI
均基本持平，本轮没有证明稳定、普遍的吞吐收益。

## 汇编结构

guest 使用各自冻结的 `wrapper.S`/`asm_head.h` 编译相同最小正文，开启
`KD_GENERATED_ENTRY_ABI=1`，保留 `objdump -dr -Mintel` 输出。下表是各标签段
的静态指令数，不是完整操作的动态指令数或周期：

| 标签段 | 前 | 后 | 原因 |
| --- | --- | --- | --- |
| `load_packet` | 39 | 25 | 去掉七组内存复制及无用物理 R11 导入，新增包基址 |
| `clobber_body` | 24 | 23 | 去掉 SP/BP 到独立槽的两个保存，新增包基址 |
| `legacy_exit` | 30 | 22 | 去掉 R12–R15 backing 的四组复制 |
| `full_exit` | 33 | 25 | 不再从七个独立槽弹出到 `pt_regs` |

正常 clobber 路径原本已没有整包导入，新入口仅少一条指令；这项优化主要减少
旧入口和完整出口的搬运。新 block 计数需要访问内存，请求包也直接承载执行中
的 spill，这些是潜在抵消成本，尚未独立计时。TCLock 的物理栈切换本来就没有
这一层虚拟 GPR backing 复制；消除复制不会同时消除 kdlock 的分派、地址重写、
逐请求管理和校验。既有 [TCLock 成本对照](../EXECUTION_PATHS.md#tclock-cost-comparison)
仍适用，不能用本轮结果推算与 TCLock 的新差距。

## 环境、范围与证据

recovery guest 内核 `6.1.159-kdclobber1`，Build ID
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`；同一启动、配置、工具链和固定 Python
依赖，保留 frame pointer、缓解、watchdog、voluntary、nokaslr。使用 NUMA0 的
CPU 0–3；每线程 100000 次、4 线程、1/16 cacheline，两种 caller ABI。
两边都统一在 CPU 0 准备/晋升，避免混入此前已知的冷并发晋升问题。
本轮只复测 kdlock，没有重跑 Linux/TCLock、单线程、20 线程或完整矩阵。

在各自源码版本的 guest 中运行同一命令，`--output` 分别选新建的 `before` /
`after` 目录；必须沿用 [环境与快照确认流程](../../../docs/AGENTS.md)：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C PYTHONNOUSERSITE=1 timeout 840 python3 bench/tclock_compare/run.py \
  --output /root/kdlock-evidence/shared-reg-bank-repeat \
  --cachelines 1 16 --threads 4 --repeats 3 --backends kdlock --abis legacy clobber \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

旧运行源码匹配 Git `d8875887eff8917e7527e986e8943c9d14ea80b1` 的对应运行文件；
新版本为其上的本轮工作区改动。每侧保留 226 个源码/文档/私有 provider 文件、
6 个二进制、12 个完整会话、有效 JIT 生成物及计数。宿主离线审核逐文件哈希、
每场副作用/ABI/发布/退休记录，并独立重算四组中位数；312 个 live 冻结源码
也匹配当前运行/测试文件。文档后续补记不算重跑。

guest 原始目录为 `/root/kdlock-evidence/shared-reg-bank-20260918/`。宿主归档
`/tmp/kd-shared-reg-bank-20260918/evidence.tar.gz`（13,308,197 字节），SHA256 与
guest 一致：`72e00c01134ba5522ad1c3ac45054f73e5ab9aff8892bcd85424ee130f66358e`。
宿主 [audit.json](/tmp/kd-shared-reg-bank-20260918/audit.json) 保留范围、计数、单次
极值和汇编段计数。该审核只验证冻结材料与记录一致，不认证日志来源或重新执行。
