#!/bin/bash
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
echo "WAITING_P2..."
for i in $(seq 1 400); do
  if ! pgrep -f "run_training.py.*diag_53km_p2" >/dev/null 2>&1; then
    break
  fi
  sleep 15
done
echo "=====P2_STATUS====="
if pgrep -f "run_training.py.*diag_53km_p2" >/dev/null 2>&1; then
  echo "STILL_RUN (timeout 100min)"
else
  echo "COMPLETED"
fi
echo "=====FULL_CSV====="
cat outputs/diag_53km_p2_curric1500/seed0/results/train_history_*.csv 2>/dev/null