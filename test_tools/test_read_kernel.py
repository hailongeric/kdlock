#!/usr/bin/env python3

from elftools.elf.elffile import ELFFile

def read_kernel_addr_data(addr, size):
    with open('/proc/kcore', 'rb') as f:
        elf = ELFFile(f)
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                vaddr = segment['p_vaddr']
                memsz = segment['p_memsz']
                # 检查地址是否落在此段内
                if vaddr <= addr < vaddr + memsz:
                    offset = segment['p_offset'] + (addr - vaddr)
                    f.seek(offset)
                    return f.read(size)
    return None

# 使用示例
data = read_kernel_addr_data(0xffffffffbae00300, 64)
print(data.hex())