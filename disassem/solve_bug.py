def solve_cond_jmp_lock_cmpxchg(file_path):

    def is_match(a, b):
        a1 = a.split()
        b1 = b.split()
        if len(a1) == len(b1) + 1:
            return False
        for e in range(0, len(b1)):
            if a1[e + 1] != b1[e]:
                return False
        return True

    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
    lines_to_add = []
    target_line_number = []
    for i, line in enumerate(lines):
        if len(line) > 5 and line[:5] == "LOCK ":
            for j in range(i, -1, -1):
                if lines[j][:4] == "loc_":
                    break
            if lines[j][-2:] != ":\n":
                continue
            for j in range(i, -1, -1):
                if lines[j] == "/*\n":
                    before_addr = int(lines[j + 1][4:], 16)
                    break
            for j in range(i, len(lines)):
                if lines[j] == "/*\n":
                    after_addr = int(lines[j + 1][4:], 16)
                    break
            if after_addr == before_addr + 1:
                flag = False
                for k in range(j, len(lines)):
                    if lines[k] == "":
                        break
                    if is_match(line, lines[k]):
                        flag = True
                        break
                if flag:
                    target_line_number.append(j - 2)
                    for k in range(i, -1, -1):
                        if "->	c_next:loc_" in lines[k]:
                            lines_to_add.append(
                                "JMP             " + lines[k].split(":")[1]
                            )
                            break

    if len(target_line_number) == 0:
        return

    new_lines = []
    pre_number = 0
    for i, n in enumerate(target_line_number):
        new_lines.extend(lines[pre_number:n])
        new_lines.extend(lines_to_add[i])
        pre_number = n
    new_lines.extend(lines[pre_number:])

    with open(file_path, "w", encoding="utf-8") as file:
        file.writelines(new_lines)
    # print("add_jmp_cond_jmp_lock_cmpxchg")


# def solve_lea_ra_rb_c_rb(line, offset):
#     need_solve_code = {
#         b"\x48\x8d\x14\x7f": 3,
#         b"\x48\x8d\x04\x9b": 5,
#         b"\x48\x8D\x04\x80": 5,
#         b"\x48\x8D\x14\x9B": 5,
#     }
#     if line.b in need_solve_code:
#         line.args[1]._ptr._args[1]._arg = need_solve_code[line.b]
#         print("miasm bug at %x" % offset)


def solve_lea_ra_rb_c_rb(line, offset):
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
    reg = get_bits(modr_m, 3, 3)
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

    if line.args[1]._ptr._args[1]._arg != read_scale + 1:
        line.args[1]._ptr._args[1]._arg = read_scale + 1
        # print("solve solve_lea_ra_rb_c_rb %x" % offset, line, line.b)

    return True
