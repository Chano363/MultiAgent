#!/usr/bin/env bash
# 前台运行 3 ep，捕获完整错误堆栈（不重定向，直接输出）
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 3 \
  --resume outputs/checkpoints_formation/seed0_nep1400/mappo_fleet_best_dec_ad2_cp_seed0.pt \
  --override n_env=2 \
  --override env_cfg.max_steps=60 \
  --checkpoint_dir outputs/checkpoints_formation/seed0_valid_lean \
  --results_dir outputs/checkpoints_formation/seed0_valid_lean/results \
  2>&1