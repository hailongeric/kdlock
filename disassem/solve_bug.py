# Narrow decoder/assembly workarounds, not general x86 correctness fixes.
# The LEA correction consults source encoding before changing a decoded scale;
# the text postprocessor adjusts LOCK-related output before final assembly.
# Both are called by the translator, not standalone project entry points.
from miasm_compat import expr_args, expr_int_value, expr_ptr, set_expr_int_value


def solve_cond_jmp_lock_cmpxchg(file_path):
    """Skip the overlapping unprefixed block after executing its LOCK form.

    A branch may enter the opcode after F0. Miasm then emits two blocks for
    the same source operation; the locked block's actual successor is after
    both encodings. Do not scan source comments as executable instructions or
    infer a successor from an unrelated/final block.
    """
    from pathlib import Path
    import re

    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    blocks = list(re.finditer(
        r"/\*\nloc_([0-9a-fA-F]+)\n(.*?)\*/[ \t]*\nloc_\1:\n",
        text, re.DOTALL))
    insertions = []
    for before, after in zip(blocks, blocks[1:]):
        if int(after[1], 16) != int(before[1], 16) + 1:
            continue
        first = [line.split() for line in before[2].splitlines()
                 if line.strip() and not line.startswith("->")]
        second = [line.split() for line in after[2].splitlines()
                  if line.strip() and not line.startswith("->")]
        if (len(first) != 1 or len(second) != 1 or
                first[0][0] != "LOCK" or first[0][1:] != second[0]):
            continue
        next_before = re.findall(r"t_next:(loc_[0-9a-fA-F]+)", before[2])
        next_after = re.findall(r"t_next:(loc_[0-9a-fA-F]+)", after[2])
        if len(next_before) != 1 or next_before != next_after:
            continue
        insertions.append((after.start(), "JMP             " + next_before[0] + "\n"))
    for position, jump in reversed(insertions):
        text = text[:position] + jump + text[position:]
    if insertions:
        path.write_text(text, encoding="utf-8")


def solve_lea_ra_rb_c_rb(line):
    def get_bits(byte, start, length):
        return (byte >> start) & ((1 << length) - 1)

    bytes_code = line.b

    if bytes_code[0] >= 0x40 and bytes_code[0] <= 0x4F:
        opcode_index = 1
    else:
        opcode_index = 0

    if opcode_index == 1:
        prefix_last_bit = bytes_code[0] & 0b11
        if prefix_last_bit != 0b00 and prefix_last_bit != 0b11:
            return False

    if len(bytes_code) < opcode_index + 2:
        return False

    opcode = bytes_code[opcode_index]
    if opcode != 0x8D:
        return False

    modr_m_index = opcode_index + 1
    modr_m = bytes_code[modr_m_index]
    mod = get_bits(modr_m, 6, 2)
    r_m = get_bits(modr_m, 0, 3)

    if mod != 0x00:
        return False

    if r_m != 4:
        return False

    if len(bytes_code) < modr_m_index + 2:
        return False

    sib_byte = bytes_code[modr_m_index + 1]
    scale = get_bits(sib_byte, 6, 2)
    index = get_bits(sib_byte, 3, 3)
    base = get_bits(sib_byte, 0, 3)

    if index != base or scale not in {0, 1, 2, 3}:
        return False

    read_scale = 1 << scale

    lea_args = expr_args(expr_ptr(line.args[1]))
    scale_arg = lea_args[1]
    if expr_int_value(scale_arg) != read_scale + 1:
        set_expr_int_value(scale_arg, read_scale + 1)

    return True
