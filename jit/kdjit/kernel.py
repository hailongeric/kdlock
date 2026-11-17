# SPDX-License-Identifier: GPL-2.0
"""Access to the running kernel for the translator.

Wraps /dev/kdlock (layouts mirror include/kdlock/kd_uapi.h) and
/proc/kallsyms. Nothing here interprets code.
"""

import bisect
import ctypes
import fcntl
import os
import struct

MASK64 = (1 << 64) - 1

# ---- ioctl encoding (asm-generic/ioctl.h) -----------------------------------

_IOC_WRITE, _IOC_READ = 1, 2


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("K") << 8) | nr


KD_MAX_SYMS = 96
INFO_FMT = "<II" + "Q" * 17 + "QQII" * KD_MAX_SYMS
READ_FMT = "<QQQ"
ALLOC_FMT = "<QQII"
LOAD_FMT = "<IIQQQQ"
SITE_FMT = "<Q"
EVENT_FMT = "<IIQQQ"
TEXT_FMT = "<QQIIQQII"

KD_IOC_INFO = _ioc(_IOC_READ, 1, struct.calcsize(INFO_FMT))
KD_IOC_READ = _ioc(_IOC_WRITE, 2, struct.calcsize(READ_FMT))
KD_IOC_IMAGE_ALLOC = _ioc(_IOC_READ | _IOC_WRITE, 3, struct.calcsize(ALLOC_FMT))
KD_IOC_IMAGE_LOAD = _ioc(_IOC_WRITE, 4, struct.calcsize(LOAD_FMT))
KD_IOC_SITE_DROP = _ioc(_IOC_WRITE, 5, struct.calcsize(SITE_FMT))
KD_IOC_ENABLE = _ioc(_IOC_WRITE, 6, 4)
KD_IOC_TEXT = _ioc(_IOC_READ | _IOC_WRITE, 7, struct.calcsize(TEXT_FMT))

KD_ABI_VERSION = 4

# Exit codes (kd_uapi.h).
KD_X_UNLOCK, KD_X_ACQUIRE, KD_X_MISS_CODE, KD_X_MISS_IND = 1, 2, 3, 4
KD_X_MISS_RET, KD_X_FRONTIER, KD_X_BUDGET = 5, 6, 7
KD_X_UNLOCK_ANC, KD_X_NESTED = 8, 9
KD_X_TAIL = 0x10000

KD_SYM_UNLOCK, KD_SYM_ACQUIRE, KD_SYM_NESTED, KD_SYM_LOCAL, KD_SYM_UNLOCK_CL = 1, 2, 3, 4, 5

KD_EV_REQUEST, KD_EV_MISS_CODE, KD_EV_MISS_IND, KD_EV_MISS_RET, KD_EV_SITE_OFF = 1, 2, 3, 4, 5
KD_EV_TEXT_GONE = 6
KD_EV_HANDBACK = 7


class Info:
    """Decoded struct kd_info."""

    def __init__(self, raw):
        f = struct.unpack(INFO_FMT, raw)
        self.abi, nr_syms = f[0], f[1]
        (self.jit_exit, self.pcpu_task, self.pcpu_canary, self.pcpu_stack_top,
         self.pcpu_root, self.pcpu_exit_ip, self.pcpu_resume, self.pcpu_aux,
         self.pcpu_exit_code, self.src_current_task, self.src_stack_canary,
         self.src_stack_top, self.pcpu_anc, self.jit_exit_cl) = f[2:16]
        syms = f[19:]
        # addr -> (class, op, alternative entry for generated code)
        self.syms = {syms[4 * i]: (syms[4 * i + 2], syms[4 * i + 3], syms[4 * i + 1])
                     for i in range(nr_syms)}
        if self.abi != KD_ABI_VERSION:
            raise RuntimeError("kdlock ABI %d, translator expects %d" % (self.abi, KD_ABI_VERSION))

    def gs_substitutions(self):
        """Per-CPU symbol -> kd_cpu field holding the origin's value."""
        pairs = ((self.src_current_task, self.pcpu_task),
                 (self.src_stack_canary, self.pcpu_canary),
                 (self.src_stack_top, self.pcpu_stack_top))
        return {src: dst for src, dst in pairs if src}


class Device:
    def __init__(self, path="/dev/kdlock"):
        self.fd = os.open(path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def info(self):
        buf = bytearray(struct.calcsize(INFO_FMT))
        fcntl.ioctl(self.fd, KD_IOC_INFO, buf, True)
        return Info(bytes(buf))

    def read_kernel(self, addr, length):
        buf = ctypes.create_string_buffer(length)
        req = struct.pack(READ_FMT, addr & MASK64, length, ctypes.addressof(buf))
        fcntl.ioctl(self.fd, KD_IOC_READ, req)
        return buf.raw

    def image_alloc(self, size):
        buf = bytearray(struct.pack(ALLOC_FMT, size, 0, 0, 0))
        fcntl.ioctl(self.fd, KD_IOC_IMAGE_ALLOC, buf, True)
        _, base, image_id, _ = struct.unpack(ALLOC_FMT, buf)
        return image_id, base

    def image_load(self, image_id, site, entry_off, text, gen):
        """Publish an image. Fails with ESTALE if text changed since `gen`."""
        buf = ctypes.create_string_buffer(text, len(text))
        req = struct.pack(LOAD_FMT, image_id, gen, site & MASK64, entry_off, len(text),
                          ctypes.addressof(buf))
        fcntl.ioctl(self.fd, KD_IOC_IMAGE_LOAD, req)

    def text(self, addr, max_fixups=4096):
        """(start, end, gen, fixups) for the text region holding addr.

        start == end == 0 when addr is not in live kernel or module text.
        `fixups` are the instructions with exception-table entries there.
        """
        while True:
            arr = (ctypes.c_uint64 * max_fixups)()
            buf = bytearray(struct.pack(TEXT_FMT, addr & MASK64, ctypes.addressof(arr),
                                        max_fixups, 0, 0, 0, 0, 0))
            fcntl.ioctl(self.fd, KD_IOC_TEXT, buf, True)
            _, _, _, count, start, end, gen, _ = struct.unpack(TEXT_FMT, buf)
            if count <= max_fixups:
                return start, end, gen, frozenset(arr[:count])
            max_fixups = count

    def text_gen(self):
        return self.text(0, 0)[2]

    def site_drop(self, site):
        fcntl.ioctl(self.fd, KD_IOC_SITE_DROP, struct.pack(SITE_FMT, site & MASK64))

    def enable(self, on):
        fcntl.ioctl(self.fd, KD_IOC_ENABLE, struct.pack("<I", 1 if on else 0))

    def events(self, max_events=256):
        """Drain pending events; returns a list of (type, cpu, site, ip, target)."""
        size = struct.calcsize(EVENT_FMT)
        raw = os.read(self.fd, size * max_events)
        return [struct.unpack_from(EVENT_FMT, raw, off) for off in range(0, len(raw), size)]


class KernelView:
    """Symbols, text bytes and text regions of the running kernel.

    Everything here belongs to one text generation (`gen`); sync() rereads
    symbols and drops all caches when modules came or went since.
    """

    PAGE = 4096

    def __init__(self, dev, kallsyms="/proc/kallsyms"):
        self.dev = dev
        self.kallsyms = kallsyms
        self.gen = None
        self.sync()

    def sync(self):
        """Prepare for a build: drop cached text, reread symbols if needed.

        Returns the generation the following build is based on. The
        generation is read before the symbols, so a change in between
        makes the image load fail with ESTALE instead of going unnoticed.
        """
        self.pages = {}
        gen = self.dev.text_gen()
        if gen != self.gen:
            self.regions = []       # (start, end, fixups)
            self.sc_sites = {}      # static call name -> call site addresses
            self._load_symbols()
            self.gen = gen
        return self.gen

    def _load_symbols(self):
        self.names_at = {}      # addr -> [names]
        self.addr_of = {}       # name -> first addr (unique names only matter)
        text = set()
        with open(self.kallsyms) as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                addr, kind, name = int(parts[0], 16), parts[1], parts[2]
                if addr == 0:
                    continue
                self.addr_of.setdefault(name, addr)
                if kind in "tTwW":
                    self.names_at.setdefault(addr, []).append(name)
                    text.add(addr)
        if not text:
            raise RuntimeError("no kernel symbols; run as root with kptr_restrict=0")
        self.text_syms = sorted(text)

    def read(self, addr, length):
        out = bytearray()
        while length > 0:
            page = addr & ~(self.PAGE - 1)
            data = self.pages.get(page)
            if data is None:
                data = self.dev.read_kernel(page, self.PAGE)
                self.pages[page] = data
            off = addr - page
            chunk = data[off:off + length]
            out += chunk
            addr += len(chunk)
            length -= len(chunk)
        return bytes(out)

    def static_call_sites(self, name):
        """Addresses of the inline call sites of static call `name`.

        The kernel rewrites such a site whenever the call's target changes:
        it can be `call target`, a 5-byte NOP, or `xor %eax,%eax` for a
        target that returns 0. So the live text alone does not show that the
        instruction stands for the call. The kernel's own site tables do,
        and they cover modules as well: the key (__SCK__name) points either
        to its run of entries in the core kernel's table (low bit set) or to
        a list of {next, module, entries}, one per module with sites. Each
        table is sorted by key, so a key's entries are contiguous. An entry
        is two 32-bit offsets relative to their own addresses: the site, and
        the key with two flag bits (include/linux/static_call_types.h).
        Sites in init text are left out (the kernel no longer patches them).
        """
        cached = self.sc_sites.get(name)
        if cached is not None:
            return cached
        out = set()
        key = self.addr_of.get("__SCK__" + name)
        if key is not None:
            try:
                word = struct.unpack("<Q", self.read(key + 8, 8))[0]
                runs = []
                if word & 1:
                    runs.append(word & ~1)
                else:
                    mod = word
                    while mod and len(runs) < 65536:
                        nxt, _module, entries = struct.unpack("<QQQ", self.read(mod, 24))
                        if entries:
                            runs.append(entries)
                        mod = nxt
                for entry in runs:
                    while True:
                        addr, kref = struct.unpack("<ii", self.read(entry, 8))
                        if ((entry + 4 + kref) & MASK64) & ~3 != key:
                            break
                        # STATIC_CALL_SITE_INIT: init text, freed after
                        # init; a later module may reuse the addresses.
                        if not kref & 2:
                            out.add((entry + addr) & MASK64)
                        entry += 8
            except OSError:
                # A module went away while its table was read; the
                # generation changed, so the image will be refused and
                # built again from a fresh view.
                pass
        self.sc_sites[name] = out
        return out

    def func_of(self, addr):
        """Start address of the text symbol containing addr, or None."""
        i = bisect.bisect_right(self.text_syms, addr) - 1
        return self.text_syms[i] if i >= 0 else None

    def names(self, addr):
        return self.names_at.get(addr, ())

    def _region(self, addr):
        for region in self.regions:
            if region[0] <= addr < region[1]:
                return region
        start, end, _gen, fixups = self.dev.text(addr)
        if start == end:
            return None
        region = (start, end, fixups)
        self.regions.append(region)
        return region

    def in_text(self, addr):
        """addr lies in live core-kernel or module text."""
        return self._region(addr) is not None

    def has_fixup(self, addr):
        """The instruction at addr has an exception-table entry.

        Such an instruction relies on its own address being in the table,
        so a relocated copy must never execute it. Covers modules too.
        """
        region = self._region(addr)
        return region is not None and addr in region[2]
