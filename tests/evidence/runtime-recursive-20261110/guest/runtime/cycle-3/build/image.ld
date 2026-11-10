ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc0e00000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
