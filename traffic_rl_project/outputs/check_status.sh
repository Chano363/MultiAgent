#!/bin/bash
# 临时状态检查脚本：训练最终奖励 + 健壮性/5列评估进度
cd "$(dirname "$0")/.."
for s in 0 1 2 3 4; do
    echo "--- seed${s} 训练日志尾 ---"
    grep -E '最佳奖励|最佳|best_reward|Best' "outputs/train_full_seed${s}.log" 2>/dev/null | tail -2
done
echo "=== 健壮性评估进度（robust_full）==="
grep -E 'seed[0-9]' outputs/tmp_eval_robust_full.log 2>/dev/null | tail -n 8
echo "=== 5列评估进度（5train_full）==="
tail -n 8 outputs/tmp_eval_5train_full.log 2>/dev/null || echo "(尚未开始)"
echo "=== 进程数 ==="
ps aux | grep -c '[e]val_phys2_5train'
