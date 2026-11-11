savedcmd_kd_runtime_fixture.mod := printf '%s\n'   runtime_fixture.o | awk '!x[$$0]++ { print("./"$$0) }' > kd_runtime_fixture.mod
