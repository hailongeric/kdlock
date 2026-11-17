#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# A/B within one boot: interleave the values of a kernel core parameter
# (/sys/module/kernel/parameters/PARAM), rotating their order per round, so
# boot-to-boot differences cannot masquerade as an effect. Summarize with
# ab_summary.py OUT.
#   run_ab.sh OUT PARAM "V1 V2 ..." ROUNDS -- run_grid.py args...
out=$1; param=$2; vals=($3); rounds=$4; shift 5
cd "$(dirname "$(readlink -f "$0")")"
for r in $(seq 0 $((rounds-1))); do
  n=${#vals[@]}
  for i in $(seq 0 $((n-1))); do
    v=${vals[$(( (i + r) % n ))]}
    echo $v > /sys/module/kernel/parameters/$param
    python3 -u run_grid.py --out $out --rounds 1 --commit "$param=$v" "$@" >> $out.log 2>&1
  done
done
