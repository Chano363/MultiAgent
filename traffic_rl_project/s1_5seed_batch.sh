#!/bin/bash
# 阶段1 编队层 MT-2 多列协同 MAPPO：seed 1..4 顺序长训（临时脚本，用后即删）。
# seed0 由独立 job 先行；本脚本补 1..4，串行避免单卡 GPU/CPU 过载。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
for seed in 1 2 3 4; do
  echo "=== START seed $seed $(date) ==="
  python run_training.py --experiment configs/experiments/platoon_mappo.yaml --seed "$seed" --episodes 500 \
    --override 'curriculum=300:60,1000:160,15000:400' \
    --override 'decision_interval=10' \
    > "/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/train_s1_seed${seed}.log" 2>&1
  echo "=== DONE seed $seed $(date) ==="
done