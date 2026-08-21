#!/bin/bash
# 第2层 M1 群组协同 MAPPO 分层训练（free_length=12 + log_prob 修复后）
# 加载新第1层 checkpoint，RL 只学协同 δ
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/trainer/train_fleet.py \
    --episodes 200 \
    --num_trains 3 \
    --preset 10kt_1plus0 \
    --grade shuozhou_23800 \
    --max_steps 300 \
    --hierarchical \
    --adj_coef 0.1 \
    --entropy 0.001 \
    --layer1_checkpoint outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt \
    --seed 0 \
    > outputs/train_logs/l2_m1_200ep_seed0.log 2>&1
echo "L2 M1 training done, exit=$?"
