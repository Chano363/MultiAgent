#!/bin/bash
# 步骤⑥：奖励塑形后重评估 M1 vs M3 vs 惰行
# 验证：低40下降 + 协同增量保持/提升 + 整体reward是否转正
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/evaluation/evaluate_m1_m3_long.py \
    all \
    outputs/checkpoints/mappo_fleet_best_cp_seed0.pt \
    > outputs/train_logs/eval_m1m3_relief.log 2>&1
echo "Eval relief done, exit=$?"
