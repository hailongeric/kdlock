set -eu
cd /root/host_fs/kdlock
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
MUTEX_RUN=/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020
MUTEX_INPUT=bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020
python3 -c 'import runpy; runpy.run_path("tests/kernel/mutex/local/run.py")["idle"]()'
mkdir "$MUTEX_RUN"
cp "$MUTEX_INPUT/run-checks.py" "$MUTEX_INPUT/run-matrix.py" "$MUTEX_INPUT/capture-host.py" "$MUTEX_INPUT/host-before.json" "$MUTEX_RUN/"
cp /tmp/mutex32-native-tclock-round.sh "$MUTEX_RUN/round-command.sh"
python3 "$MUTEX_RUN/run-checks.py" --commit bd9d4ce205512fd34dc00044e3ad238f985d4b6d --output "$MUTEX_RUN/checks"
python3 "$MUTEX_RUN/run-matrix.py" --commit bd9d4ce205512fd34dc00044e3ad238f985d4b6d --base "$MUTEX_RUN"
