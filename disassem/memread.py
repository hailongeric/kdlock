from elftools.elf.elffile import ELFFile


def read_kernel_addr_data(addr, size):
    with open("/proc/kcore", "rb") as f:
        elf = ELFFile(f)
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                vaddr = segment["p_vaddr"]
                memsz = segment["p_memsz"]
                # Map the virtual kernel address through the matching ELF segment.
                if vaddr <= addr < vaddr + memsz:
                    offset = segment["p_offset"] + (addr - vaddr)
                    f.seek(offset)
                    return f.read(size)
    return None


def read(entry, jump_table, excluded_callees=None):
    excluded_callees = excluded_callees or set()
    try:
        with open("./asm/ij_table.txt", "r", encoding="ascii") as table:
            ij_file = table.read()
    except OSError:
        ij_file = ""

    ij_file = sorted(set(ij_file.splitlines()))
    ij_his = [[int(x.split()[0], 16), int(x.split()[1], 16)] for x in ij_file]

    for t in ij_his:
        if t[0] not in jump_table:
            jump_table[t[0]] = []
        jump_table[t[0]].append(t[1])
    for x in jump_table:
        jump_table[x] = sorted(set(jump_table[x]))

    targets = [x[1] for x in ij_his]
    targets.append(entry)

    try:
        with open("./asm/callee_table.txt", "r", encoding="ascii") as table:
            calleefile = table.read()
    except OSError:
        calleefile = ""
    callees = [
        int(x, 16)
        for x in calleefile.splitlines()
        if int(x, 16) not in excluded_callees
    ]
    targets += callees

    targets = sorted(set(targets))

    targets_of = {}
    for t in targets:
        t1 = t & 0xFFFFFFFFFFFFF000
        if t1 > 0xFFFFFFFF80000000 and t1 < 0xFFFFFFFFFFFFFFFF:
            if t1 not in targets_of:
                targets_of[t1] = []
            targets_of[t1].append(t)
        else:
            raise RuntimeError(f"JMP/CALL target {t:#x} is outside kernel space")

    res = []
    total_bytes = 0

    for start, page_targets in targets_of.items():
        end = start + 0x2000
        chunk = read_kernel_addr_data(start, end - start)
        if chunk is None:
            raise RuntimeError(f"cannot read kernel text at {start:#x}")
        res.append([chunk, start, page_targets])
        total_bytes += len(chunk)

    print(
        f"Translation input: entry={entry:#x} targets={len(targets)} "
        f"regions={len(res)} bytes={total_bytes}"
    )

    return res
