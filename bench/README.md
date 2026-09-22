# Benchmarks

最新[adaptive快速三方结果](tclock_compare/results/20260922-adaptive-quick.md)：
18/18场、1500万次计时操作完成并排空，4/4竞争KD有实际JIT。
1线程KD c1/c16为8.445/6.940 Mops/s，20线程为5.048/4.818 Mops/s。
本轮只测adaptive、每配置一轮；默认双模式矩阵与汇总通过运行器检查。
此前observe完整矩阵及历史版本成绩保留在[三方对照入口](tclock_compare/README.md)。

当前性能测试对象固定为 **Linux 原生、TCLock、当前 kdlock**，使用
`tclock_compare/run.py --backends native tclock kdlock`。不再将旧版 kdlock
作为测试对象；以下新旧版对照只保留为历史证据，后续结果报告三方吞吐及
当前 KD/Linux、KD/TCLock 比值。2026-09-22 用户最新要求：每配置只测一轮，
三方使用各自这一次有效会话的吞吐和 ns/op 计算比值，不自动追加轮次。
当前运行器默认同时测 KD observe 和 adaptive，分别保存、汇总；Linux/TCLock 每配置
各测一次。cacheline 默认40场、RCUHT默认20场；`--hotlock-mode adaptive` 可只跑自适应模式。
代码修改后可直接运行性能测试，使用运行器内置的正确性/JIT/排空检查；独立
单元、SELFTEST 或功能小矩阵按需选择，不作为固定前置步骤。
原始样本留存；此前两轮最大值及五轮中位数报告保留历史口径。

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
