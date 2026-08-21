#!/bin/bash
# 方案A：缓解波下第1层完整重训（release_sync=False + E16.1奖励塑形，修复缓解波掉速）
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
    --no_release_sync \
    > outputs/train_logs/l1_wave_300ep_seed0.log 2>&1
echo "L1 wave training done, exit=$?"
