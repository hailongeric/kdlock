savedcmd_kd_spin_runtime_fixture.o := ld -m elf_x86_64 -z noexecstack --no-warn-rwx-segments   -r -o kd_spin_runtime_fixture.o @kd_spin_runtime_fixture.mod  ; /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build/tools/objtool/objtool --hacks=jump_label --hacks=noinstr --hacks=skylake --retpoline --rethunk --sls --stackval --static-call --uaccess --prefix=16  --link  --module kd_spin_runtime_fixture.o

kd_spin_runtime_fixture.o: $(wildcard /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build/tools/objtool/objtool)
