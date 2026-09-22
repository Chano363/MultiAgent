#!/usr/bin/env bash
sleep 40
echo "=== 53km 评估进程 ==="
pgrep -af 'evaluate_decompose.*53km' | head -1 || echo '已退出!'
echo "=== 35km 评估进程 ==="
pgrep -af 'evaluate_decompose.*35km' | head -1 || echo '已退出!'
echo "=== 当前 python 进程 ==="
ps -eo pid,etime,pcpu,args | grep -E 'evaluate_decompose' | grep -v grep | sed -E 's/(--checkpoint [^ ]+).*/\1/' | head -4
echo "=== 训练进程是否仍存活 ==="
pgrep -fc 'run_training.py --experiment'