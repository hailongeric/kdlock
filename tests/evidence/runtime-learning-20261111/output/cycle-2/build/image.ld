ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc0e20000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
