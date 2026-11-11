ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc004f000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
