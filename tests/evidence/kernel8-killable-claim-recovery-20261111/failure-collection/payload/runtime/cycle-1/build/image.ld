ENTRY(kd_fixture_entry)
SECTIONS { .text 0xffffffffc000f000 : { *(.text) } /DISCARD/ : { *(.note.GNU-stack) } }
