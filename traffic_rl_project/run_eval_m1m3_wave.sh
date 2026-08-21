#!/bin/bash
# 缓解波匹配后重评估 M1 vs M3 vs 惰行
# 验证：缓解波下协同增量 + 低40（第1层缓解波训练后应不掉速）
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/evaluation/evaluate_m1_m3_long.py \
    all \
    outputs/checkpoints/mappo_fleet_best_cp_seed0.pt \
    > outputs/train_logs/eval_m1m3_wave.log 2>&1
echo "Eval wave done, exit=$?"
