set -eu
cd /root/host_fs/kdlock
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
MUTEX_RUN=/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020
python3 -c 'import runpy; runpy.run_path("tests/kernel/mutex/local/run.py")["idle"]()'
python3 "$MUTEX_RUN/run-finalize.py" --base "$MUTEX_RUN"
timeout 180 /root/kdlock-plot-venv-20261019/bin/python3 "$MUTEX_RUN/plot.py" --comparison "$MUTEX_RUN/comparison.json" --output "$MUTEX_RUN"
python3 bench/archive_run.py --base "$MUTEX_RUN" --output "${MUTEX_RUN}-archives" --health "$MUTEX_RUN/health.json" --group current=current --group checks=checks --timeout-seconds 600
timeout 180 python3 "$MUTEX_RUN/export-compact.py" --base "$MUTEX_RUN" --archives "${MUTEX_RUN}-archives" --output "${MUTEX_RUN}-compact"
