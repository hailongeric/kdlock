#!/bin/bash
# dis.sh SYM START END: guest helper, disassemble SYM+START..SYM+END of the
# kdall vmlinux in /mnt/kdlock-builds/kda/out3 (offsets in hex, 0x...).
cd /mnt/kdlock-builds/kda/out3
a=$(grep -E " $1$" /proc/kallsyms | head -1 | cut -d" " -f1)
st=$(python3 -c "print(hex(int('$a',16)+int('$2',16)))"); en=$(python3 -c "print(hex(int('$a',16)+int('$3',16)))")
objdump -d --no-show-raw-insn --start-address=$st --stop-address=$en vmlinux | grep -vE "^$|Disassembly|file format"
