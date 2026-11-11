ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc0030000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
