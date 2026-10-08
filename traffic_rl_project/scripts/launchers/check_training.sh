#!/usr/bin/env bash
echo "=== 运行中的 run_training 进程数 ==="
pgrep -fc 'run_training.py --experiment'
echo "=== load ==="
cat /proc/loadavg
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints/formation
for s in 0 1 2 3 4; do
  f="$BASE/final_seed$s/results/train_history_dec_ad2_cp_seed$s.csv"
  printf "seed%s: " "$s"
  if [ ! -f "$f" ]; then echo "no csv"; continue; fi
  n=$(($(wc -l < "$f")-1))
  printf "%s ep | " "$n"
  tail -1 "$f" | tr -d '\r'
done