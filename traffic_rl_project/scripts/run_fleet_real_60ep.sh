#!/bin/bash
# 第2层短训验证：真实剖面 shuozhou_23800 + 限速 [40,80]km/h + 3列编队 MAPPO
# 观察 Reward 趋势 / best 更新 / 车钩力守住，验证"列间协同循环制动"假设
cd /mnt/d/Code/MultiAgent/traffic_rl_project
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl

python src/trainer/train_fleet.py \
  --episodes 60 \
  --num_trains 3 \
  --preset 10kt_1plus0 \
  --grade shuozhou_23800 \
  --v_max 22.22 \
  --v_min 11.11 \
  --max_steps 1500 \
  --max_accel 1.0 \
  --target_gap 100 \
  --seed 0 \
  2>&1 | tee outputs/train_logs/fleet_60ep_real_seed0.log
