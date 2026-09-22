#!/usr/bin/env bash
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation
f="$BASE/final_seed0/results/train_history_dec_ad2_cp_seed0.csv"
echo "=== seed0 CSV: 头2行 ==="; tr '\r' '\n' < "$f" | head -2
echo "=== seed0 CSV: 行10-12 ==="; tr '\r' '\n' < "$f" | sed -n '11,12p'
echo "=== seed0 CSV: 行 400 ==="; tr '\r' '\n' < "$f" | sed -n '400p'
echo "=== seed0 CSV: 尾2行 ==="; tr '\r' '\n' < "$f" | tail -2
echo "=== 第一列非数字行检查 ==="; tr '\r' '\n' < "$f" | tail -n +2 | awk -F, '$1 ~ /^[0-9]+$/ {n++} END{print "数字ep行="n}'