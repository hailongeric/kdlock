ENTRY(kd_mm_entry)
SECTIONS { .text 0xffffffffc000e000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
