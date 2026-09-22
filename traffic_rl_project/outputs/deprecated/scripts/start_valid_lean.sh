#!/usr/bin/env bash
# 验证治本杠杆：ep841 续训 30ep（n_env=4, 1200步档）。exec 保证 job wrapper 内持续运行。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 30 \
  --resume outputs/checkpoints_formation/seed0_nep1400/mappo_fleet_best_dec_ad2_cp_seed0.pt \
  --override n_env=4 \
  --checkpoint_dir outputs/checkpoints_formation/seed0_valid_lean \
  --results_dir outputs/checkpoints_formation/seed0_valid_lean/results \
  --override dirs.figures_dir=outputs/checkpoints_formation/seed0_valid_lean/figures \
  2>&1