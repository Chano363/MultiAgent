#!/bin/bash
# 步骤③：修复后确定性重评估 M1 vs M3 vs 惰行
# 关键验证：M1(协同δ) 相对 M3(δ=0) 在 free_length=12 真实编队尺度下是否出现协同增量
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/evaluation/evaluate_m1_m3_long.py \
    all \
    outputs/checkpoints/mappo_fleet_best_cp_seed0.pt \
    > outputs/train_logs/eval_m1m3_after_fix.log 2>&1
echo "Eval done, exit=$?"
