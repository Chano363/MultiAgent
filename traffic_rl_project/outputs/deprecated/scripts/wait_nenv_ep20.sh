#!/bin/bash
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
LOG=outputs/diag_53km_nenv_seed0.log
echo "Kick off; waiting for Ep 20..."
for i in $(seq 1 600); do
  if grep -q 'Ep 20/' "$LOG" 2>/dev/null; then
    echo "REACHED_EP20"
    break
  fi
  if ! pgrep -f "run_training.py.*diag_53km_nenv" >/dev/null 2>&1; then
    echo "PROCESS_DIED"
    break
  fi
  sleep 10
done
echo "===== TB vs BC 判定视窗 (ep15-22) ====="
echo "--- 本日志 ep15-20 行 ---"
grep -E "Ep (1[5-9]|20)/" "$LOG" | head -12
echo "--- 全部已完成 ep 汇总 ---"
grep -oE "Ep [0-9]+/44.*" "$LOG" | tail -25