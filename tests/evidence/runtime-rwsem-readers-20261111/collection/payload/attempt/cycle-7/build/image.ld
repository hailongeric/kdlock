ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc0012000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
