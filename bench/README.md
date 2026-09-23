# Benchmarks

最新[三轮完整矩阵](tclock_compare/results/20260923-spin-three-round.md)：
84种配置各测3轮，252/252场、19440万次计时操作通过并排空；运行器22项回归通过。
报告保留每轮样本及min/median/max/spread，最大有效吞吐仍用于正式比值。
低线程波动仍明显，20线程on相对off的中位数下降5.22%–7.15%。

此前[adaptive快速三方结果](tclock_compare/results/20260922-adaptive-quick.md)：
18/18场、1500万次计时操作完成并排空，4/4竞争KD有实际JIT。
1线程KD c1/c16为8.445/6.940 Mops/s，20线程为5.048/4.818 Mops/s。
当时只测adaptive、每配置一轮；默认双模式矩阵与汇总通过运行器检查。
此前observe完整矩阵及历史版本成绩保留在[三方对照入口](tclock_compare/README.md)。

当前性能测试对象固定为 **Linux 原生、TCLock、当前 kdlock**，使用
`tclock_compare/run.py --backends native tclock kdlock`。不再将旧版 kdlock
作为测试对象；以下新旧版对照只保留为历史证据，后续结果报告三方吞吐及
当前 KD/Linux、KD/TCLock 比值。2026-09-23 用户因性能波动将默认轮次提高为
每配置三轮；三方继续使用有效最大吞吐及该会话的 ns/op 计算比值，同时展示
各配置三轮吞吐的最小值、中位数、最大值与波动范围，保留原始样本。
当前运行器默认同时测 KD observe 和 adaptive，分别保存、汇总；Linux/TCLock 每配置
每轮各测一次，供各 KD 模式及调用壳比较。cacheline 默认120场、RCUHT默认60场；
`--hotlock-mode adaptive` 可只跑自适应模式。完整1/2/3/4/8/16/20线程、双模式、
on/off调用壳矩阵共252场。功能模式仍显式使用 `--repeats 1`。
代码修改后可直接运行性能测试，使用运行器内置的正确性/JIT/排空检查；独立
单元、SELFTEST 或功能小矩阵按需选择，不作为固定前置步骤。
不足三轮有效样本须单独说明；此前单轮、两轮最大值及五轮中位数报告保留历史口径。

所有构建与测量只在 recovery guest，环境及排空遵循 [AGENTS](../docs/AGENTS.md)。
当前入口按直接 API 使用独立 Linux、TCLock、KD 对象；旧透明 hook 和双 ABI
性能运行器已删除。冻结历史报告保留原版本与归档索引，不作为当前验收。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前三后端直接调用、cacheline/RCUHT、observe/adaptive 和本地嵌套检查 |
| [spin_cacheline](spin_cacheline/README.md) | 当前运行器共用的客户端、provider 观察层、生命周期和离线汇总/汇编读取 |

[历史索引](spin_cacheline/results/HISTORY.md)汇总旧阶段报告、回退及冻结证据入口，
详细说明从固定 Git 版本读取，避免旧命令与当前运行路径混用。
后续工作统一见 [PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。
