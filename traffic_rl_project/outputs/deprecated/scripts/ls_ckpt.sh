#!/usr/bin/env bash
for s in 0 1 2 3 4; do
  d=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation/final_seed$s
  echo "--- seed$s ---"
  ls -lt "$d"/mappo_fleet_best*.pt "$d"/mappo_fleet_last_ep*.pt 2>/dev/null | head -3
done