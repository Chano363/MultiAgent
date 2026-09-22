#!/bin/bash
# 临时监控脚本：打印 5 seed 最新回合进度（用后即删）
cd "$(dirname "$0")/.."
for f in 0 1 2 3 4; do
    last=$(grep -E 'Ep [0-9]+' "outputs/train_full_seed${f}.log" | tail -1)
    echo "seed${f}: ${last}"
done
