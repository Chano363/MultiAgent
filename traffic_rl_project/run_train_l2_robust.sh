#!/bin/bash
# 第2层 M1 扰动鲁棒性重训（最终分层架构 + 训练加扰动场景）
# 目标：让 M1 学会领航车突发减速时协同保持间距（当前模型未训练扰动，鲁棒性不足）
# 扰动：step500 突发 -0.3m/s² 持续100步（短暂临时限速窗口），初始速度随机化增强泛化
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/trainer/train_fleet.py \
    --episodes 200 \
    --num_trains 3 \
    --preset 10kt_1plus0 \
    --grade shuozhou_23800 \
    --max_steps 1200 \
    --hierarchical \
    --enable_disturbance \
    --disturbance_step 500 \
    --disturbance_duration 100 \
    --disturbance_target_accel -0.3 \
    --random_init_speed \
    --adj_coef 0.3 \
    --entropy 0.001 \
    --seed 0 \
    > outputs/train_logs/l2_robust_200ep_seed0.log 2>&1
echo "L2 robust training done, exit=$?"
