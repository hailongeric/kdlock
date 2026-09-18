# 2026-09-18：统一 combiner 现场后的 spinlock 性能

本轮完成 **120/120 会话**，测量期共 100,000,000 次完整操作，实际返回 JIT 正文
44,207,367 次；数据、工作线程退出、退休和排空全部通过。新 clobber ABI 在
20 线程、1/16 cacheline 下为 **1.6294 / 1.6370 Mops/s**，与统一循环前基本持平，
仍低于对应原生的 **2.9487 / 1.8030 Mops/s**。此次没有测到新代理路径的一致提速。

## 版本、环境与方法

生产代码为提交 `73a1eb6c88715189ebbd03b2b96bd5a3d2391626`：新旧及混合 ABI
共享 combiner C 循环，编译器管理活跃 C 值，旧的成组保存外壳仅留作测试夹具。
现场保存/恢复与 TCLock 的对照见[寄存器 ABI](../../../docs/JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比)。
本轮只修复 benchmark 观测补丁和测试夹具与新循环的兼容性，没有修改生产锁实现。

全部构建及运行在 recovery guest，沿用 `6.1.159-kdclobber1`，运行 Build ID
`db937d722ee2f2668acb12dc6f105aeea33b7c5c`。基线核验通过：19 个源码文件、
9 个构建文件、5 个 bundle 文件及配置。40 vCPU、28 GiB、双 NUMA，工作线程
固定在 guest node 0 的 CPU 0–19；voluntary preemption、nokaslr、ext4、watchdog=1。
保留 frame pointer 和原有缓解配置，没有重建或重启内核。

使用 [clobber_compare.py](../clobber_compare.py)，保持既有 payload 和锁外四组
依赖乘加。1/16 cacheline × 1/4/20 线程，每线程 100000 次；每配置交替五轮
legacy-native、clobber-native、legacy-kdlock、clobber-kdlock，奇数轮逆序。
准备、自然 promotion、翻译、发布和稳定等待不计入测量；测量前 daemon 已退出。
两种调用者的区别仅为 legacy 构建增加 `KCFLAGS=-DKD_SPIN_LEGACY_CALLER`。
报告每组五个有效样本的中位数，不采用旧扫描的最佳样本口径。

固定 Python 依赖为 miasm 0.1.5、future 1.0.0、pyparsing 2.4.7、pyelftools 0.27。
实际命令在 guest checkout 执行；重复运行须选择新的输出目录：

```sh
PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH \
  LC_ALL=C PYTHONNOUSERSITE=1 KDIR=/root/linux-6.1.159-kdclobber1 \
  KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 3600s python3 bench/spin_cacheline/clobber_compare.py \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918 \
  --output /root/kdlock-evidence/spin-unified-20260918-0506/compare
```

## 完整操作吞吐

单位 **百万次完整操作/秒**。JIT 列为测量期间实际返回正文数 / 完成操作数的
五轮中位数；每个表格单元均有五个有效会话。

| cachelines | 线程 | legacy native | clobber native | legacy kdlock | clobber kdlock | legacy JIT | clobber JIT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 11.0891 | 9.8719 | 9.5532 | 9.6692 | 0% | 0% |
| 1 | 4 | 3.2840 | 2.9927 | 0.8488 | 0.8867 | 51.7015% | 54.2433% |
| 1 | 20 | 3.1372 | 2.9487 | 1.6920 | 1.6294 | 99.8227% | 99.8380% |
| 16 | 1 | 10.3670 | 9.3769 | 8.2786 | 8.1826 | 0% | 0% |
| 16 | 4 | 1.9172 | 1.7519 | 0.7922 | 0.8064 | 53.8115% | 52.6203% |
| 16 | 20 | 1.9173 | 1.8030 | 1.6826 | 1.6370 | 99.8369% | 99.8073% |

40 个竞争 kdlock 会话均有实际 JIT，20 个单线程 kdlock 会话均为 NO_JIT；
另 60 个为不加载 provider 的 native。单线程 NO_JIT 只测加载 hook 后的无代理
路径，不能证明 wrapper 或批次保存逻辑的收益。新 ABI 的四个竞争配置吞吐分别
为对应 native 的 **29.63%、55.26%、46.03%、90.79%**。

本轮新旧调用者 ABI 的 kdlock 吞吐之比：4 线程的 1/16 cacheline 分别变化
**+4.46% / +1.80%**，20 线程分别为 **−3.70% / −2.71%**。4 线程的 JIT 比例
并不完全相等，尤其 16 cacheline 的新 ABI 中位数更低，不能将该点较快直接归因
于精简状态搬运。20 线程覆盖率接近；五轮样本仍不足以将小差值当作可靠加速。
新 ABI 的 20 线程吞吐范围为 1.6038–1.6847 / 1.5909–1.6623 Mops/s。

## 与统一循环前的历史测量比较

下表复用[前一轮](20260918-clobber-v1.md)冻结数据，仅比较相同内核、负载、线程
及五轮中位数。两个版本没有在本轮交替运行，原生对照也有波动，不能把历史差值
全部归因于 combiner 改动。

| cachelines | 线程 | legacy kdlock 较前轮 | clobber kdlock 较前轮 |
| --- | --- | --- | --- |
| 1 | 4 | +1.84% | +6.96% |
| 1 | 20 | +3.50% | −0.33% |
| 16 | 4 | +1.52% | −2.40% |
| 16 | 20 | +3.46% | +0.12% |

新 ABI 的 20 线程结果基本持平，4 线程两点方向不同。此次实测不支持统一循环
给新代理路径带来普遍吞吐提升。原生对照为 Linux qspinlock，没有 TCLock 同环境
性能结果；实现逻辑的对照不能代替三方性能测量。

## 调用者成本与观测修复

| cachelines | legacy 单线程 native ns/op | clobber 单线程 native ns/op | 差值 |
| --- | --- | --- | --- |
| 1 | 90.178 | 101.298 | +11.119 |
| 16 | 96.460 | 106.645 | +10.185 |

两份调用者反汇编仍显示：clobber 在函数序言/尾声额外保存恢复 RBX、R12–R15，
增加 40 字节栈空间；lock/unlock 各传递三条元数据指令。该负载没有跨边界的
活跃 C 局部值，额外保存主要履行函数对外的 callee-saved 义务。表中为完整操作
均摊 wall time，包含桥接、payload 和锁外计算，不是单独的 spill 周期或锁延迟。

首次准备在加载模块前失败：私有 `observation.patch` 的错误日志 hunk 仍使用旧
`return NULL` 上下文。改为统一 C 循环的 `return`，保留 `--fuzz=0` 和原有错误
诊断。随后测试发现抽取该代码块的夹具也保留旧返回类型；将夹具改为 void，仍
检查提前返回、后继节点与 quiet 模式下错误日志不被屏蔽。JIT 正文计数位置未改。
最终 `make -C bench/spin_cacheline test` 的 **15 + 7 项检查全部通过**，之后在
全新目录重新运行完整 120 场，没有拼接失败版本的数据。

私有 provider 的 W=1、严格 daemon/client 及两份 workload 构建通过。保留
自定义切栈/返回等既有 objtool 警告；不能将成功构建写成 objtool 无警告。
本轮未扩展为全量单元或复杂 live 回归。

## 证据

guest 原始目录 `/root/kdlock-evidence/spin-unified-20260918-0506/compare/` 保存
计划、120 个会话、24 组 summary、两 ABI 对照、内核身份、202 个冻结源码及
5 个二进制的哈希、调用者反汇编、逐会话生成物、正文计数、日志和退休状态。
结束后确认源码/二进制未变、guest 为 KNOWN_IDLE。`host-source.json` 将冻结输入
关联到宿主提交及上述两处 benchmark 修改，不使用 guest 的旧 Git 元数据代替。

[完整归档](/tmp/kd-spin-unified-20260918/evidence.tar.gz) 的 SHA256 为
`8550f48dd887541a633af07c7f8d0f5547e69c3f9d3c34e227c3b2c6c69da351`，宿主和 guest 一致。
guest 副本为 `/root/kdlock-evidence/spin-unified-20260918.tar.gz`，也包含首次准备
失败的 `spin-unified-20260918-0502/` 和测试夹具失败日志。
[独立只读审计](/tmp/kd-spin-unified-20260918/audit.json) 已重算全部会话数据、
JIT 差值、ABI 身份、生成物/源码/二进制哈希及 24 组中位数；脚本 `audit.py`
在归档内。审计只核对捕获材料，不替代运行期 oracle，也不证明未测的延期功能。
