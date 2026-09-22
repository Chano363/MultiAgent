#!/usr/bin/env bash
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation
for s in 0 1; do
  f="$BASE/final_seed$s/results/train_history_dec_ad2_cp_seed$s.csv"
  echo "===== seed$s CSV 概况 ====="
  echo "总行数(不含头): $(($(wc -l < "$f")-1))"
  echo "ep 范围: $(tr '\r' '\n' < "$f" | tail -n +2 | head -1 | cut -d, -f1) ... $(tr '\r' '\n' < "$f" | tail -1 | cut -d, -f1)"
done