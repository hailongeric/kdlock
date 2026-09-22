# 2026-09-22：撤回512槽直接映射并复核性能

按用户要求恢复 `bf16b10`，生产实现、头文件、单元fixture和内核探针均与该提交
逐字节一致。每CPU/type恢复256桶、256条记录，以完整地址和冲突链区分；满表
保留已有记录。本地busy、已有pin复用、CPU1024/锁1025阈值恢复原有行为。
普通spin IRQ语义、wrapper栈修复、ticket和continuation协议均保留。

[512槽功能实验](20260922-directhash-v2.md)和[性能结果](20260922-directhash-v2-performance.md)
保留并标记为已撤回，不删除失败证据。回退前差异和源码副本另存宿主
`/tmp/kd-rollback-v2-20260922/before.patch`、`before.tar.gz`。

## 验证

只在guest `6.1.159-kdclobber2`执行；现有内核与TCLock未改。
宿主vCPU映射与回退前一致，测试CPU0..19固定在物理插槽0。

- 基础2项、hotlock sampling和spin preempt共4/4驱动通过；11个错误变体检出，19条获取路由抢占配对通过。
- SELFTEST构建及ELF布局通过：热表entry/table/cpu为24/6688/13376 B；continuation704 B、存储栈8512 B、节点128 B。
- 生命周期探针通过：表满保留既有热表身份及真实owner，解锁后word=0；mutex从CPU1迁移到CPU2且抢占配对正常。探针mutex_jit=0。
- adaptive/plain/c1/t4完成400000次操作，实际JIT正文232146次；业务、IRQ/preempt和排空通过。
- 20线程定向三方benchmark共12/12场通过、24000000次完整操作，KD的4场全部有实际JIT，最终排空。

构建仍保留手写恢复汇编的objtool及locale警告，未宣称无警告构建。
本轮没有重跑完整线程矩阵、nested/early、真实mutex JIT或PMU；以往结果不算本次重跑。

## 20线程性能复核

Linux/TCLock/当前KD，plain，observe，1/16 cacheline；每线程100000次。
每配置两轮，各后端取有效最大吞吐，保留对应ns/op与获选会话；预热和准备不计时。
Mops/s按完整操作计算，不是单独获取锁延迟。

| cacheline | Linux Mops/s | TCLock Mops/s | 恢复后KD Mops/s | 直接映射版此前记录 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4.004 | 4.986 | 5.002 | 3.916 |
| 16 | 4.702 | 3.273 | 4.771 | 3.831 |

KD两轮分别为c1 4.996/5.002、c16 4.770824/4.770712 Mops/s，回到此前
256桶版本的性能范围。与最近直接映射批次相比最大值提高约27.7%/24.5%；
这是连续两批的结果，不是同期交错对照，不据此指定某条指令或缓存机制为根因。
Linux c16两轮为2.318/4.702，波动明显；按用户指定取最大值，未删除任一有效样本。

## 证据

命令、输入哈希、普通/SELFTEST ELF、布局、原始日志、两轮记录和审核结果位于guest
`/root/kdlock-evidence/rollback-v2-20260922/`。
[本地归档](../../.tmp/rollback_v2_20260922/rollback-v2-20260922.tar.gz) SHA256：
`b1c6f1caf981300323862e828c67a908ca2de3f0b1c26097fd2403b25cc39134`。
归档在忽略目录，新checkout不自带原始文件。
