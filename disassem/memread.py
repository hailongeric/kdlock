# Read bounded ELF PT_LOAD windows from kcore through the active device lease.
# Pin source residency before reading; extend cold CFG windows without silently
# treating missing bytes as a completed critical section. No execution occurs.
import errno
from typing import NamedTuple

import device_session
import diagnostics
from elftools.elf.elffile import ELFFile

PAGE_SIZE = 0x1000
WINDOW_SIZE = 2 * PAGE_SIZE
MAX_TEXT_BYTES = 256 * 1024


class TextWindowPolicy(NamedTuple):
    lookahead: int
    alignment: int
    budget_fallback: bool = False


DEFAULT_WINDOW_POLICY = TextWindowPolicy(WINDOW_SIZE, PAGE_SIZE)
RETAINED_WINDOW_POLICY = TextWindowPolicy(1024, 16, True)


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


def union_bytes(ranges):
    """Count each cached or decoded address byte once, including overlaps."""
    total = 0
    previous_end = None
    for start, end in sorted(ranges):
        if previous_end is None or start > previous_end:
            total += end - start
        elif end > previous_end:
            total += end - previous_end
        previous_end = end if previous_end is None else max(previous_end, end)
    return total


def _plan_regions(existing, targets, lookahead, alignment):
    """Plan only metadata; old extents and each new instruction remain required."""
    windows = list(existing)
    requested_bytes = 0
    for target in targets:
        start = target & ~(alignment - 1)
        end = max(start + lookahead, target + 15)
        if not 0xFFFFFFFF80000000 < start < end < 0xFFFFFFFFFFFFFFFF:
            raise RuntimeError(f"JMP/CALL target {target:#x} is outside kernel space")
        requested_bytes += end - start
        windows.append((start, end, {target}, target + 15))
    merged = []
    for start, end, roots, required_end in sorted(windows, key=lambda window: window[0]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
            merged[-1][2].update(roots)
            merged[-1][3] = max(required_end, merged[-1][3])
        else:
            merged.append([start, end, set(roots), required_end])
    return merged, requested_bytes


def extend_regions(regions, targets, *, policy=DEFAULT_WINDOW_POLICY):
    """Merge overlapping windows before decoding, including backward CFG edges."""
    if (not isinstance(policy, TextWindowPolicy) or policy.lookahead < 15 or
            policy.alignment <= 0 or policy.alignment & (policy.alignment - 1) or
            type(policy.budget_fallback) is not bool or
            policy.budget_fallback and (policy.lookahead, policy.alignment) != (1024, 16)):
        raise ValueError("invalid text window policy")
    # Existing bytes remain mandatory. A new root needs the full maximum x86
    # instruction length; only new lookahead follows the translation's policy.
    existing = [(start, start + len(data), set(roots), start + len(data))
                for data, start, roots in regions]
    previous_bytes = union_bytes((start, end) for start, end, _, _ in existing)
    targets = sorted(set(targets))
    lookaheads = ((1024, 512, 256, 128, 64, 15) if policy.budget_fallback
                 else (policy.lookahead,))
    # Retry only an oversized plan, before any lease request or source read.
    # Rebuild from the original cache each time: failed optional tails never
    # become mandatory, and no old bytes or roots can be lost to make it fit.
    plans = []
    for lookahead in lookaheads:
        merged, requested_bytes = _plan_regions(existing, targets, lookahead, policy.alignment)
        planned_bytes = sum(end - start for start, end, _, _ in merged)
        fits = planned_bytes <= MAX_TEXT_BYTES
        plans.append(dict(lookahead_bytes=lookahead, requested_bytes=requested_bytes,
                          planned_bytes=planned_bytes, regions=len(merged), within_budget=fits))
        if fits:
            break
    # Diagnostics coalesce by source site. One record therefore carries every
    # rejected plan as well as the selected plan, before its first source read.
    diagnostics.warn(
        "TEXT_CACHE_PLAN", "plan_leased_text", "cached windows include lookahead",
        lookahead_bytes=lookahead, alignment_bytes=policy.alignment,
        preferred_lookahead_bytes=policy.lookahead, attempted_plans=plans,
        previous_bytes=previous_bytes, requested_bytes=requested_bytes,
        planned_bytes=planned_bytes, additional_bytes=planned_bytes - previous_bytes,
        regions=len(merged), targets=len(targets), budget_bytes=MAX_TEXT_BYTES,
        within_budget=fits, selected=fits,
    )
    if not fits:
        raise TextReadLimit(f"reachable text exceeds {MAX_TEXT_BYTES} bytes")
    result = []
    for start, end, roots, required_end in merged:
        try:
            chunk = read_kernel_addr_data(start, end - start)
        except device_session.SourceRefused as error:
            required_end = (required_end + PAGE_SIZE - 1) & ~(PAGE_SIZE - 1)
            if error.errno not in {errno.EPERM, errno.ESTALE} or required_end >= end:
                raise
            # Linux 7 can place a small module's text in a single allocation
            # page. Never read its adjacent hole or loosen the provider lease.
            # Retry only the mandatory prefix through the same pin-before-read
            # boundary; reachable edges beyond it still need CFG expansion.
            diagnostics.warn(
                "TEXT_WINDOW_TRIM", "retry_leased_prefix", str(error),
                address=hex(start), requested_bytes=end - start,
                required_bytes=required_end - start, errno=error.errno,
            )
            end = required_end
            chunk = read_kernel_addr_data(start, end - start)
        if chunk is None or len(chunk) != end - start:
            raise RuntimeError(f"incomplete kernel text read at {start:#x}")
        result.append([chunk, start, sorted(roots)])
    return result


def read(entry, jump_table, excluded_callees=None, *, policy=DEFAULT_WINDOW_POLICY):
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

    # Keep exact history edges for CALL-specific dispatch, but never import a
    # service/Native boundary as an independent decoded source root.
    targets = [x[1] for x in ij_his if x[1] not in excluded_callees]
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

    res = extend_regions([], targets, policy=policy)
    total_bytes = sum(len(chunk) for chunk, _, _ in res)

    print(
        f"Translation input: entry={entry:#x} targets={len(targets)} "
        f"regions={len(res)} bytes={total_bytes}"
    )

    return res
