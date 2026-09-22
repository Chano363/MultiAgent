#!/usr/bin/env bash
d=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation/seed0_valid_latest_ep1623/results/train_history_dec_ad2_cp_seed0.csv
echo "=== 验证CSV ==="
if [ -f "$d" ]; then
  echo "行数(含头): $(wc -l < "$d")"
  tr '\r' '\n' < "$d" | tail -4
else
  echo "无CSV"
fi
echo "=== 验证进程 ==="
pgrep -af 'seed0_valid_latest_ep1623' | head -1