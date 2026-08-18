#!/bin/bash
# 临时启动脚本：M1 群组 MAPPO 决定性长训（E3）
# 用法：bash run_m1_train.sh
cd /mnt/d/Code/MultiAgent/traffic_rl_project
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
exec python src/trainer/train_fleet.py \
  --episodes 300 \
  --num_trains 3 \
  --grade shuozhou_23800 \
  --max_steps 1500 \
  --seed 0 \
  --target_gap 100 \
  --device cuda
