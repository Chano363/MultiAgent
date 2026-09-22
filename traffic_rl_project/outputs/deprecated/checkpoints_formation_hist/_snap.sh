#!/bin/bash
echo "=== snapshot $(date '+%F %T') ==="
echo "run_training procs:"
pgrep -af run_training | grep -v 'grep -v grep' | head -3
echo "active_seed via fixed detect:"
pgrep -af run_training | grep -oE -- '--seed [0-9]' | head -1 | awk '{print $2}'
echo "seed logs:"
for s in 0 1 2 3 4; do
  LOG="/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation/seed${s}_train.log"
  if [ -f "$LOG" ]; then
    LAST=$(grep -E '^Ep ' "$LOG" | tail -1)
    echo "  seed${s}: ${LAST:-no-ep-yet}"
  fi
done
echo "relay tail:"
tail -3 /mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation/relay.log
