"""Exact original-instruction boundaries in the retained JIT backend."""

from assist import make_inst
from conflict import release_conflict
from types import SimpleNamespace


ENCODING = bytes.fromhex('67 48 0f b9 3a')
EXTENDED_ENCODINGS = (bytes.fromhex('0f 01 ee'), bytes.fromhex('0f 01 ca'))
CONTROL_ENCODINGS = (b'\xfa', b'\xfb')
DIRECTION_ENCODINGS = (b'\xfc', b'\xfd')
ENCODINGS = (ENCODING,) + EXTENDED_ENCODINGS + CONTROL_ENCODINGS + DIRECTION_ENCODINGS
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

    def __init__(self, offset, encoding=ENCODING):
        if encoding not in ENCODINGS:
            raise ValueError('unknown source frontier encoding')
        self.offset = offset
        self.b, self.l = encoding, len(encoding)
        # The exact form has address/REX prefixes, but no LOCK or REP group.
        # Shared emitter spelling inspects this metadata even for terminals.
        self.additional_info = SimpleNamespace(g1=SimpleNamespace(value=0), prefixed=b'')

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
    def __init__(self, arch, *, extended=False, controls=False, direction=False):
        self.arch = arch
        self.encodings = ((ENCODING,) + (EXTENDED_ENCODINGS if extended else ())
                          + (CONTROL_ENCODINGS if controls else ())
                          + (DIRECTION_ENCODINGS if direction else ()))

    def __getattr__(self, name):
        return getattr(self.arch, name)

    def dis(self, stream, mode, offset):
        try:
            prefix = stream.getbytes(offset, 1)
        except IOError:
            return self.arch.dis(stream, mode, offset)
        for encoding in self.encodings:
            if prefix != encoding[:1]:
                continue
            try:
                raw = stream.getbytes(offset, len(encoding))
            except IOError:
                continue
            if raw == encoding:
                return Instruction(offset, encoding)
        return self.arch.dis(stream, mode, offset)


def descriptor(line):
    return (line.name == NAME and not line.args and bytes(line.b) in ENCODINGS
            and line.l == len(line.b))


def marker(line, reg_map):
    if not descriptor(line):
        raise ValueError('invalid source frontier instruction')
    code = release_conflict(reg_map)
    code += 'PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n'
    code += make_inst('MOVABS', ['R14', hex(line.offset)])
    code += make_inst('MOV', ['Stack_IJ', str(EXIT)])
    code += make_inst('JMP', ['full_exit'])
    return code
