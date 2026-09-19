# 2026-09-18：spin 获取入口与原生缓存对照

普通 root 的获取顺序改为：固定 CPU、取得 gate、尝试私有 S；竞争后才建立
完整 ticket，并复用该 gate 和 pin。首次 CAS 成功保留一个 per-CPU physical
hold，解锁按原协议先释放 Linux L，再释放 S.locked，保留并发 pending/tail。
这采用 TCLock 把竞争准备工作后移的方式；kdlock 的原生 peer 互斥、source
生命周期、嵌套与 owner/ACK 仍需要各自状态，不能直接删掉。

原生站点缓存默认保留，装载时可用 `spin_native_cache=0` 关闭。相同 L/RIP/gate
键的竞争入口不再调用 `kd_get_exe()` 回填缓存；新键仍检查已发布 NORMAL/SPIN
及 source.OPEN。缓存不授权 JIT，命中仍须实际获取 Linux L。
实现见[执行路径](../EXECUTION_PATHS.md#cold)和[设计](../../../docs/design/locking.md#41-native-lock-and-private-queue)。

## 删除缓存的试验

先完成无缓存版本的 60 场交替 A/B，再据实测选择最终策略。旧侧是本轮修改前的
模块，已含上轮共享寄存器 backing；新侧同时删除缓存并提前首次 CAS。
因此这是两项改动的合并对照，不能把差值全部归因于缓存查询本身。

五轮中位数，吞吐单位 Mops/s；JIT 比例另取中位数：

| cacheline | 线程 | 原实现 | 无缓存试验版 | 变化 | 原 JIT | 无缓存 JIT |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 8.0947 | 4.2963 | −46.92% | 0 | 0 |
| 1 | 4 | 0.8527 | 0.8534 | +0.08% | 54.20% | 54.59% |
| 1 | 20 | 1.6563 | 1.6747 | +1.11% | 99.82% | 99.84% |
| 16 | 1 | 8.6460 | 4.2449 | −50.90% | 0 | 0 |
| 16 | 4 | 0.7763 | 0.7961 | +2.55% | 53.83% | 51.97% |
| 16 | 20 | 1.6114 | 1.6655 | +3.36% | 99.79% | 99.82% |

**60/60 正确并排空**，共 5000 万次完整操作。20 场单线程没有测量期 JIT，
标为 NO_JIT；其余 40 场实际 JIT 非零。单线程完整操作增加约 109/120 ns。
缓存让重复原生获取跳过目标选择、晋升/条目确认、gate 查询和 S/L 双层持有，
删除它会重新承担这些成本。竞争组改善小，16 cacheline/4 线程同时降低了 JIT
比例，不能用代理覆盖下降证明提速。这组证据不支持默认删除缓存。

## 最终默认配置

最终版本保留上述首次 CAS 顺序和独立 physical hold，恢复默认缓存，并省掉
相同键的重复回填查询。clobber 获取的注册/调度 C 调用移入冷函数，缓存命中
不再为这些调用提前保存续点参数。回归还发现队列生产者已更新 tail、尚未发布 next 时，
combiner 会过早原生交接：首次 batch 入口现在仅在非零、不同 tail 已证明后继
存在时等其 release-link。真实队尾与 NUMA 脱链列表不套用此等待。
这同样属于最终版本的改动，最终 A/B 不能解释为孤立的缓存查询开销。

第一次恢复默认缓存后，反汇编发现 S/L 释放调用使缓存原生解锁也在函数序言
保存 RBX/R12。该轮 `final-ab/` 在 40 场正确排空后主动停止，余下 20 场未跑，
不计入最终矩阵。S/L 释放现移至独立 `kd_spin_fast_release_gate()`，让它需要的
活跃指针和编译器保存留在该函数；guest 反汇编确认缓存解锁无 RBX/R12–R15
序言保存，RBP 仍按既有约定保留。该修复保留 L→S→清持有记录→unpin 顺序。

随后 `release-ab/` 的 60 场和 `release-long/` 的 20 场全部正确排空，但长批次
仍显示原生成本增加。反汇编定位到 `READ_ONCE(bool)` 的 UBSAN 诊断冷调用，
它迫使获取入口提前保存参数。最终参数改用内核标准 `bint`，装载时仍按布尔
解析，整数存储并读回 `0/1`；clobber 获取慢路径也独立成函数。
未关闭 UBSAN 或其他检查。中间版本保留用于解释成本，不计入最终样本。

最终默认配置 **60/60 正确并排空**，共 5000 万次完整操作。与本轮同样的旧
模块交替五轮，20 场单线程为 NO_JIT，40 场竞争组实际 JIT 均非零。
以下也是五轮中位数，Mops/s；JIT 比例独立取中位数：

| cacheline | 线程 | 原实现 | 最终版本 | 变化 | 原 JIT | 新 JIT |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 9.2330 | 9.2527 | +0.21% | 0.00% | 0.00% |
| 1 | 4 | 0.8280 | 0.9275 | +12.01% | 54.16% | 55.58% |
| 1 | 20 | 1.6701 | 1.6559 | -0.85% | 99.82% | 99.83% |
| 16 | 1 | 8.2271 | 8.6826 | +5.54% | 0.00% | 0.00% |
| 16 | 4 | 0.7893 | 0.7841 | -0.66% | 53.00% | 57.68% |
| 16 | 20 | 1.6295 | 1.6188 | -0.66% | 99.82% | 99.83% |

1 cacheline/4 线程有约 12% 改善，JIT 比例也略增；16 cacheline/4 线程则基本
持平，JIT 比例提高约 4.68 个百分点。两组 20 线程均约下降 0.7%–0.9%，JIT
保持约 99.8%。因此本轮没有证明高竞争吞吐改善，也没有证明普遍提速。
c1/t4 新值范围为 0.8302–1.2898 Mops/s，旧值 0.7921–0.8700；范围有重叠且
只有五次，不能把中位数的 12% 解释为每次稳定收益。
这里没有通过降低 JIT 覆盖率解释收益；同样不能把覆盖变化当作固定代理量的
服务成本比较。TCLock 与 kdlock 的其余锁侧/请求/执行差异仍然存在。

为分离短批次影响，同一最终版本另跑单线程、每场一千万次、两规模、前后
版本交替五轮，共 **20/20 正确排空、2 亿次完整操作**，均为 NO_JIT。
这是 kdlock 中的原生执行成本，不是 Linux native 臂，也不替换上面的样本。

| cacheline | 原实现 ns/次 | 最终版本 ns/次 | 增加 | 前范围 | 后范围 |
| --- | --- | --- | --- | --- | --- |
| 1 | 43.236 | 44.733 | +1.497（3.46%） | 42.381–43.540 | 44.288–45.033 |
| 16 | 49.182 | 50.056 | +0.874（1.78%） | 48.053–49.461 | 49.659–50.358 |

最终版本消除了中间版本的大部分原生退化，仍有约 0.9–1.5 ns 的完整操作代价。
装载开关判断、两类 physical hold 的解锁分支及代码布局变化未分别隔离计时；
不能把这个差值全算作某一次 load 或 spill。获取、解锁桥的额外 callee-saved
成组保存已消失，但这不等于完整调用边界没有成本。

最后显式 `spin_native_cache=0` 的 c1/t4 单场验证也正确并排空，读回参数为
`0`，测量期 400000 次操作、213658 次实际 JIT（53.4145%）。它验证最终关闭
选项可用，不是五轮性能结论；前述无缓存 60 场属于较早的独立实现版本。

## 环境与复现

recovery guest `6.1.159-kdclobber1`，Build ID
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`，40 vCPU、28 GiB、双 NUMA。
使用 node 0 的 CPU 0–19；保持 frame pointer、缓解、watchdog、nokaslr、voluntary。
两轮各用同一调用者模块、clobber ABI、1/16 cacheline、1/4/20 线程，每线程
100000 次，每组五轮交替前后版本。每个会话独立准备、测量、退休、卸载。
统一单 CPU 预热/晋升，发布后停止 daemon；这不修复已知冷并发晋升 RCU stall。

两轮属于独立冻结版本，不能把前一轮样本拼进最终轮。上述短矩阵单线程每场
只有约 10–25 ms；长批次另列，不替换短矩阵样本。虚拟 CPU 不代表独占物理核，
五次样本的小幅变化不能外推为稳定普遍提速。
本轮没有重跑 Linux/TCLock 或 legacy ABI，也没有多锁缓存抖动负载。
历史三方结果见[TCLock 对照](../../tclock_compare/results/20260918-native-stack.md)，
不能用本轮 kdlock 数值与历史 TC 数值计算新倍率。

运行器沿用 `bench/tclock_compare/run.py` 的会话与校验，仅加入冻结旧 provider
切换；最终版本还读回模块缓存参数，另提供 cacheoff 臂。脚本保存在本轮证据
目录，调用前遵循[环境与快照流程](../../../docs/AGENTS.md)：

```sh
python3 /root/kdlock-evidence/spin-entry-20260918/compare-entry.py \
  --output /root/kdlock-evidence/spin-entry-repeat \
  --abis clobber --backends before after --cachelines 1 16 --threads 1 4 20 \
  --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

长批次用相同脚本及新输出目录，改为 `--threads 1 --iterations 10000000`；
关闭选项验证改为 `--backends cacheoff --cachelines 1 --threads 4 --repeats 1`。
命令须在固定依赖 venv 中并加外层 timeout，沿用已确认的 recovery 环境变量。
`before/kdlock_km.ko` SHA256：
`8d3150c107f1ec6932d6fc9ead2ea5ab1b05e54e5e1317092619fc6b01522d9b`。
旧侧入口源码与 HEAD `d8875887eff8917e7527e986e8943c9d14ea80b1` 一致，
wrapper 则已含上轮共享 backing；不能把旧侧称为纯 HEAD 构建。

原始材料在 guest `/root/kdlock-evidence/spin-entry-20260918/`：`ab/` 是无缓存
试验，`entry-ab/` 是最终默认配置，`entry-long/` 为长批次原生成本检查，
`entry-cacheoff/` 验证最终装载关闭选项。每场保留数据/CPU/IRQ/preempt 校验、实际 JIT
计数、发布前后状态、生成物、源码与二进制哈希、退休状态和最终排空。
功能测试与失败修复记录单独见[测试记录](../../../tests/README.md#spin-entry-first-cas)。

宿主归档 `/tmp/kd-spin-entry-20260918/evidence.tar.gz`，76,145,321 字节，与 guest
归档 SHA256 一致：
`9eb69cedba80b18de16d888b6cd0602860f21596b01ae7c29fa10ffd05722f83`。
宿主只读复算核对各版本冻结源码/二进制、数据、实际 JIT、生成物、发布不变、
退出/退休和五轮中位数；最终 312 个 live 运行/测试文件匹配工作区。
三个最终性能目录各冻结 228 个源码/文档/私有 provider 文件和各自二进制；
guest 另核对三次 provider 构建只有 `.BTF` 区段不同，其余区段数据一致，
见[区段审核](/tmp/kd-spin-entry-20260918/provider-section-audit.json)。文档后续补记另计。
该审核检查字节与记录一致性，不认证日志来源，也不重新执行用例。

- [无缓存试验审核](/tmp/kd-spin-entry-20260918/audit-ab.json)：60 场，5000 万次操作。
- [最终默认配置审核](/tmp/kd-spin-entry-20260918/audit-entry-ab.json)：60 场，5000 万次操作；旧/新测量期 JIT 为 22,160,536 / 22,213,302 次。
- [最终长批次审核](/tmp/kd-spin-entry-20260918/audit-entry-long.json)：20 场，2 亿次操作，均 NO_JIT。
- [最终关闭缓存审核](/tmp/kd-spin-entry-20260918/audit-entry-cacheoff.json)：1 场，40 万次操作，实际 JIT 非零。
- [中间版本主动停止审核](/tmp/kd-spin-entry-20260918/audit-stopped.json)：40 场正确排空、20 场未执行，不计入最终矩阵。

`release-ab/`、`release-long/`、`cacheoff/` 的独立审核和原始数据也保留；它们
属于最终获取桥/bint 修正前的实现。源码、kernel notes、失败日志、汇编与完整
运行命令均在同一归档，后续文档或 Git 提交不代表重新测量。
