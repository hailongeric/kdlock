"""Exact original-instruction boundaries in the retained JIT backend."""

from assist import make_inst
from conflict import release_conflict


ENCODING = bytes.fromhex('67 48 0f b9 3a')
NAME = 'SOURCE_FRONTIER'
EXIT = 16
REQUIREMENT = 1 << 14


class Instruction:
    """A terminal source instruction; it has no JIT successor or CALL word."""
    name = NAME
    args = ()
    delayslot = 0
    l = len(ENCODING)
    b = ENCODING

    def __init__(self, offset):
        self.offset = offset

    def breakflow(self):
        return True

    def splitflow(self):
        return False

    def dstflow(self):
        return False

    def is_subcall(self):
        return False

    def to_string(self, *args, **kwargs):
        return NAME

    def __str__(self):
        return NAME


class Decoder:
    """Supplement only the instruction offset requested by the real decoder."""
    def __init__(self, arch):
        self.arch = arch

    def __getattr__(self, name):
        return getattr(self.arch, name)

    def dis(self, stream, mode, offset):
        try:
            raw = stream.getbytes(offset, len(ENCODING))
        except IOError:
            raw = b''
        if raw == ENCODING:
            return Instruction(offset)
        return self.arch.dis(stream, mode, offset)


def descriptor(line):
    return (line.name == NAME and not line.args and line.l == len(ENCODING)
            and bytes(line.b) == ENCODING)


def marker(line, reg_map):
    if not descriptor(line):
        raise ValueError('invalid source frontier instruction')
    code = release_conflict(reg_map)
    code += 'PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n'
    code += make_inst('MOVABS', ['R14', hex(line.offset)])
    code += make_inst('MOV', ['Stack_IJ', str(EXIT)])
    code += make_inst('JMP', ['full_exit'])
    return code
