#!/usr/bin/env bash
echo "训练进程: $(pgrep -fc 'run_training.py --experiment')"
echo "评估进程: $(pgrep -fc 'evaluate_decompose')"
echo "load: $(cat /proc/loadavg)"