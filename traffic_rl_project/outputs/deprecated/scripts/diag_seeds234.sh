#!/usr/bin/env bash
for s in 2 3 4; do
  echo "--- seed$s 尾部 ---"
  tr '\r' '\n' < "/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs_final_parallel/seed$s.log" 2>/dev/null | tail -4
  echo
done
echo "=== COMPLETE 标记 ==="
grep -l "ALL 5 SEEDS COMPLETE" /mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs_final_parallel/*.log 2>/dev/null || echo "无COMPLETE标记"
echo "=== seed2-4 是否还活着 ==="
pgrep -af 'run_training.py' | grep -oE -- '--seed [0-9]' || echo "无python进程"