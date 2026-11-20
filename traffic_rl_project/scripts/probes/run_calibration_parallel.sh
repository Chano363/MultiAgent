#!/usr/bin/env bash
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
  LG10_STEPS=31500 LG10_TAG=adr082_calib_ep${EP} \
    python scripts/probes/calibrate_notch_level.py "$CK" 0.5 > "$LOGDIR/calib_ep${EP}.log" 2>&1 &
  pids+=($!)
  echo "launched calib ep$EP pid=${pids[-1]}"
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "ALL_CALIB_DONE fail=$fail $(date -Is)"
