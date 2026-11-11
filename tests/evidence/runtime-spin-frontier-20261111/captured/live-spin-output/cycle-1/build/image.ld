ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc0011000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
