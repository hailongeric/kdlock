# Read bounded ELF PT_LOAD windows from kcore through the active device lease.
# Pin source residency before reading; extend cold CFG windows without silently
# treating missing bytes as a completed critical section. No execution occurs.
import device_session
from elftools.elf.elffile import ELFFile

PAGE_SIZE = 0x1000
WINDOW_SIZE = 2 * PAGE_SIZE
MAX_TEXT_BYTES = 256 * 1024


class TextReadLimit(RuntimeError):
    """The reachable text exceeds this translator's bounded admission scope."""


def read_kernel_addr_data(addr, size):
    # Fixtures may substitute this I/O boundary; real reads must retain the
    # same provider throughout decode/emission, including cold extensions.
    device_session.pin_range(addr, size)
    with open("/proc/kcore", "rb") as f:
        elf = ELFFile(f)
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                vaddr = segment["p_vaddr"]
                memsz = segment["p_memsz"]
                # Map the virtual kernel address through the matching ELF segment.
                if vaddr <= addr < vaddr + memsz:
                    if addr + size > vaddr + memsz:
                        raise RuntimeError(
                            f"kernel text range crosses ELF segment at {addr:#x}"
                        )
                    offset = segment["p_offset"] + (addr - vaddr)
                    f.seek(offset)
                    return f.read(size)
    return None


def extend_regions(regions, targets):
    """Merge overlapping windows before decoding, including backward CFG edges."""
    windows = [(start, start + len(data), set(roots)) for data, start, roots in regions]
    for target in targets:
        start = target & ~(PAGE_SIZE - 1)
        if not 0xFFFFFFFF80000000 < start < 0xFFFFFFFFFFFFFFFF - WINDOW_SIZE:
            raise RuntimeError(f"JMP/CALL target {target:#x} is outside kernel space")
        windows.append((start, start + WINDOW_SIZE, {target}))
    merged = []
    for start, end, roots in sorted(windows, key=lambda window: window[0]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
            merged[-1][2].update(roots)
        else:
            merged.append([start, end, set(roots)])
    if sum(end - start for start, end, _ in merged) > MAX_TEXT_BYTES:
        raise TextReadLimit(f"reachable text exceeds {MAX_TEXT_BYTES} bytes")
    result = []
    for start, end, roots in merged:
        chunk = read_kernel_addr_data(start, end - start)
        if chunk is None or len(chunk) != end - start:
            raise RuntimeError(f"incomplete kernel text read at {start:#x}")
        result.append([chunk, start, sorted(roots)])
    return result


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

    res = extend_regions([], targets)
    total_bytes = sum(len(chunk) for chunk, _, _ in res)

    print(
        f"Translation input: entry={entry:#x} targets={len(targets)} "
        f"regions={len(res)} bytes={total_bytes}"
    )

    return res
