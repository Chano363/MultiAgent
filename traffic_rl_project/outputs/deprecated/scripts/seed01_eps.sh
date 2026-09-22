#!/usr/bin/env bash
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation
for s in 0 1; do
  f="$BASE/final_seed$s/results/train_history_dec_ad2_cp_seed$s.csv"
  echo "===== seed$s ====="
  echo "ep 唯一值数 / 总行: $(tr '\r' '\n' < "$f" | tail -n +2 | cut -d, -f1 | sort -n | uniq | wc -l) / $(($(wc -l < "$f")-1))"
  echo "ep 前20个: $(tr '\r' '\n' < "$f" | tail -n +2 | cut -d, -f1 | head -20 | tr '\n' ' ')"
  echo "ep 后20个: $(tr '\r' '\n' < "$f" | tail -n +2 | cut -d, -f1 | tail -20 | tr '\n' ' ')"
  echo
done