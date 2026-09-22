# 2026-09-22：公共调用精简，第二阶段

在第一阶段 `31d8fd2` 上消除 clobber→通用获取、clobber→公共解锁和 pinned→通用热度
包装调用，复用同一个已 pin 核心。旧接口、JIT ABI、32位锁字和慢路径 request/frame 协议保留。
**单线程改善，但竞争验收仍未通过，默认保留旧调用壳并关闭冷路径。**

本阶段使用函数局部 cookie。用户随后要求改为 per-CPU，此报告保存改动前的历史实测，
不能作为 per-CPU 版本的成绩。每配置一轮，不补测或跨阶段选优；长批次PMU留给最终版本。

## 同期性能

recovery guest，plain/cacheline，1/16 cacheline × 1/4/20线程，每线程100000次，共36场。
Linux/TCLock各一次；KD observe/adaptive各使用同一源码的 paired/on 和保留 clobber/off。
准备及48000次预热不计时。每格 **Mops/s / 完整操作 ns/op**。

| cacheline | 线程 | Linux | TCLock | observe off | observe on | adaptive off | adaptive on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.153 / 58.30 | 15.102 / 66.22 | 8.394 / 119.13 | 12.954 / 77.19 | 10.563 / 94.67 | 14.842 / 67.38 |
| 1 | 4 | 3.585 / 278.96 | 2.927 / 341.65 | 1.858 / 538.20 | 1.859 / 538.00 | 1.841 / 543.26 | 1.792 / 558.19 |
| 1 | 20 | 4.798 / 208.43 | 4.967 / 201.31 | 4.975 / 201.01 | 4.514 / 221.51 | 4.988 / 200.50 | 4.563 / 219.16 |
| 16 | 1 | 13.838 / 72.26 | 12.441 / 80.38 | 8.211 / 121.78 | 11.996 / 83.36 | 9.545 / 104.77 | 11.295 / 88.53 |
| 16 | 4 | 2.078 / 481.26 | 2.227 / 449.04 | 1.581 / 632.34 | 1.572 / 636.31 | 1.705 / 586.56 | 1.602 / 624.41 |
| 16 | 20 | 2.682 / 372.81 | 3.273 / 305.54 | 4.726 / 211.58 | 4.043 / 247.31 | 4.737 / 211.10 | 4.163 / 240.22 |

同期 on/off：c1单线程 observe/adaptive 提升54.32%/40.50%，c16提升46.10%/18.33%。
c16四线程adaptive下降6.06%，20线程下降8.52%–14.45%，这些配置仍是待解决问题。

仅看公共调用精简后的**保留壳**，相对第一阶段单轮，c1单线程observe/adaptive提高
20.76%/29.04%，c16提高31.35%/30.87%。两批测试时间不同，Linux/TCLock也有波动；
这些是分阶段观察值，不是对包装开销的严格因果估计。机器码已确认三类包装调用消失。

## 验证及修复

- 性能36/36场、30000000次计时操作完成，16/16竞争KD有实际JIT，计时JIT正文17856254次。
  IRQ/preempt、业务数据、队列/ACK、内核日志及排空检查全部通过。
- 定向功能7/7场、1100000次操作通过并排空：nested/early各4线程，RCUHT
  observe/adaptive各1/4线程，以及4线程delegation关闭。nested/early有196459/49954次
  JIT正文，RCUHT两个4线程有125730/129875次；关闭delegation为0。
- 最终基础2组加直接相关6组通过；25项clobber准入及运行器13项通过。实际paired wrapper
  测试覆盖栈中五寄存器入口值、解锁保存新值、MINIMAL COMPLETE、入口拒绝及FULL/native续跑。
  fixture开发时的汇编/link/续跑断言失败日志保留，修复后重新执行对应项。
- JIT测试发现outer unlock后的native suffix已裁剪，但continuation dispatch仍引用其标签，
  导致链接失败。现在只保留实际生成范围内的续跑目标；内层CALL目标和准入检查不变。
- 首次nested实际入口拒绝：旧内层clobber使外层paired unlock准备保存的寄存器失去已定义来源。
  mixed场景在原内层调用前后显式保存/恢复五寄存器，保留原符号、元数据和续跑协议。
  新准入回归证明未恢复的代码仍被拒绝。失败会话已排空并归档，不计入通过场次。
  此修复只在`SC_SCENARIO!=0`启用；修复前性能ELF与修复后plain功能ELF全部执行节及
  `.rela.text`哈希完全相同，见`plain-code-audit.json`，没有追加性能重复轮次。
- provider W=1构建；内核6.1.159-kdclobber2，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，ext4/nokaslr/voluntary。
  快照及vCPU0..39→host CPU0..39绑定沿用并核验。未修改、构建或安装guest内核。
  单独在证据目录构建用户态perf工具，PMU事件可用；本阶段未跑正式长批次。

## 证据

性能命令同[第一阶段](20260922-spin-cold-stage1.md)，输出改为
`/root/kdlock-evidence/cold-fast-20260922/stage2/performance`。
功能命令及配置见同目录`run-functional-fixed.py`与`functional-final/*/plan.json`；
代码、ELF和内核身份分别冻结，日志中有完整命令。最终空闲检查通过。

guest目录`/root/kdlock-evidence/cold-fast-20260922/stage2/`，宿主归档
[stage2.tar.gz](../../.tmp/cold-fast-20260922/stage2.tar.gz)，SHA256：
`80d976d289adaecdce6a6e2331c6945b0723aeb02a944a4cd0b07ba74ba98716`。
归档含原始records/summary、provider反汇编、call-audit、功能与失败日志。
