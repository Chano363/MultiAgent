#!/bin/bash
# 第2层 M2 消融训练（最终分层架构，忽略车钩力 use_coupler_constraint=False）
# 证明"车钩力建模必要性"创新点：M1(考虑车钩力)守住约束且协同有效，M2(忽略)超限。
source /home/chano/miniconda3/etc/profile.d/conda.sh
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
    --no_coupler_constraint \
    --adj_coef 0.3 \
    --entropy 0.001 \
    --seed 0 \
    > outputs/train_logs/l2_nocp_200ep_seed0.log 2>&1
echo "L2 nocp training done, exit=$?"
