#!/bin/bash
# 第1层单列循环制动重训（free_length=12 新物理尺度，warm start 自规则）
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/trainer/train_cyclic_braking.py \
    --episodes 300 \
    --grade shuozhou_23800 \
    --warm_start \
    --init_speed_kmh 80 \
    --seed 0 \
    > outputs/train_logs/l1_scale_300ep_seed0.log 2>&1
echo "L1 training done, exit=$?"
