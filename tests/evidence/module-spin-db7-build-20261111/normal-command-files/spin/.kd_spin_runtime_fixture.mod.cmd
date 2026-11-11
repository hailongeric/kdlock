savedcmd_kd_spin_runtime_fixture.mod := printf '%s\n'   spin_runtime_fixture.o | awk '!x[$$0]++ { print("./"$$0) }' > kd_spin_runtime_fixture.mod
