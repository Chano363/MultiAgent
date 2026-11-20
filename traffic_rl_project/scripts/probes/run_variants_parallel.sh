#!/usr/bin/env bash
# ADR-082: run remaining variants in parallel (each variant in its own python process).
# Runs inside WSL. Launched via Windows schtasks so it survives IDE terminal close.
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
export LG10_TAG=adr082_abcolbias_probe_20261120
LOGDIR=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs/adr082
mkdir -p "${LOGDIR}"
pids=()
for V in "$@"; do
  LG10_ONLY="$V" python scripts/probes/probe_percol_ab_threshold.py > "${LOGDIR}/${V}.log" 2>&1 &
  pids+=($!)
  echo "launched $V pid=${pids[-1]}"
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "ALL_VARIANTS_DONE fail=$fail $(date -Is)"
