#!/bin/bash
# 监控回滚训练，等待首个关键 ep 段输出，超时 3000s
LOG=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/diag_53km_rollback_seed0.log
for i in $(seq 1 100); do
  sleep 30
  if grep -q "Ep 20/30" "$LOG" 2>/dev/null; then
    echo "REACHED_EP20 at $(date +%H:%M)"
    break
  fi
  if ! pgrep -f run_training.py >/dev/null 2>&1; then
    echo "TRAIN_DONE_EARLY"
    break
  fi
done
echo "=== LATEST EP ==="
grep "Ep " "$LOG" 2>/dev/null | tail -n 8
echo "=== DONE ==="