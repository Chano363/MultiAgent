#!/usr/bin/env bash
sleep 30
echo "=== 全部 evaluate_decompose 进程 ==="
ps -eo pid,etime,pcpu,args | grep 'evaluate_decompose' | grep -v grep | sed -E 's/(--checkpoint [^ ]+).*(--out_suffix [^ ]+).*/\1 \2/' 
echo "=== 训练进程 ==="
pgrep -fc 'run_training.py --experiment'
echo "=== load ==="
cat /proc/loadavg