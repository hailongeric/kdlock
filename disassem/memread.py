import sys
from elftools.elf.elffile import ELFFile

def getmap(pid):
    path = "/proc/" + str(pid) +"/maps"
    try:
        f = open(path)
    except Exception as e:
        sys.exit(1)

    lines = f.readlines()
    maps = []
    for i in range(len(lines)):
        lines[i] = lines[i].split(' ')
        if 'x' not in lines[i][1]:
            continue
        [start, end] = lines[i][0].split('-')
        #maps.append([int(start,16), int(end,16), lines[i][1], lines[i][-1]])
        maps.append([int(start,16), int(end,16)])
    f.close()

    return maps

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

def read(pid, entry, jump_table):
    try:
        ij_file = open('./asm/ij_table.txt', 'r', 4096).read()
    except Exception as e:
        ij_file = ''
        print('No ij_table')

    ij_file = list(set(ij_file.splitlines()))
    ij_his = [[int(x.split()[0], 16), int(x.split()[1], 16) ] for x in ij_file]

    for t in ij_his:
        if t[0] not in jump_table:
            jump_table[t[0]] = []
        jump_table[t[0]].append(t[1])
    for x in jump_table:
        jump_table[x] = list(set(jump_table[x])) 

    targets = [x[1] for x in ij_his]
    targets.append(entry)
    
    try:
        calleefile = open('./asm/callee_table.txt', 'r', 4096).read()
    except Exception as e:
        calleefile = ''
        print('No callee_table')
    callees = [int(x, 16) for x in calleefile.splitlines()]
    targets += callees

    targets = list(set(targets))
    print("Targets:", [hex(x) for x in targets])

    # maps = getmap(pid) HL MOD
    targets_of= dict()        #map file ID to a list of targets within
    for t in targets:
        # for i in range(len(maps)):
        #     if maps[i][0] <= t and maps[i][1] > t:
        #         if i not in targets_of:
        #             targets_of[i] = []
        #         targets_of[i].append(t)
        #         found = 1
        t1 = t & 0xfffffffffffff000
        if t1 > 0xffffffff80000000 and t1 < 0xffffffffffffffff:
            if t1 not in targets_of:
                targets_of[t1] = []
            targets_of[t1].append(t)
        else:
            print('JMP/CALL target', hex(t), 'not found')
            exit(0)

    # path = "/proc/" + str(pid) +"/mem"
    # mem_file = open(path, 'rb', 4096)
    res = []

    for t in targets_of:
        [start, end] = [t, t + 0x2000]
        # mem_file.seek(start)
        chunk = read_kernel_addr_data(start, end - start)
        # print chunk info
        print([hex(i) for i in chunk[:100]])
        res.append([chunk, start, targets_of[t]])

    # mem_file.close()
    return res

def read2(pid, entry):
    maps = getmap(pid)
    found = 0
    for m in maps:
        if m[0] <= entry and m[1] > entry:
            [start, end] = m[0:2]
            found = 1
            break
    if found == 0:
        print('raed2 start address not found in memory')
        exit(0)
        
    path = "/proc/" + str(pid) +"/mem"
    mem_file = open(path, 'rb', 4096)
    mem_file.seek(start)
    chunk = mem_file.read(end - start)
    mem_file.close()
    return chunk, [start, end]
