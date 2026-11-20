#!/usr/bin/env bash
# Cross-ckpt generalisation test for the per-column AB threshold mechanism.
# For each ckpt: run base (no threshold) and the tuned variant (foll=0.90),
# to test whether the mechanism's benefit transfers across training stages.
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
CKROOT=outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud
LOGDIR=outputs/logs/adr082
mkdir -p "$LOGDIR"
pids=()
for EP in "$@"; do
  CK="$CKROOT/mappo_fleet_ep${EP}_dec_ad1_cp_seed0.pt"
  for V in base bias_n; do
    LG10_CKPT="$CK" LG10_ONLY="$V" LG10_TAG="adr082_crossckpt_ep${EP}" \
      python scripts/probes/probe_percol_ab_threshold.py \
      > "$LOGDIR/cross_ep${EP}_${V}.log" 2>&1 &
    pids+=($!)
    echo "launched ep$EP $V pid=${pids[-1]}"
  done
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "ALL_CROSS_DONE fail=$fail $(date -Is)"
