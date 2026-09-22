#!/usr/bin/env bash
# 2026-09-22 检验：取 seed0 最新 checkpoint（全局 ep1623）做 30ep 验证（n_env=4, 1200步档）。
# 模式同 start_valid_lean.sh（治本验证）；结果写独立目录，不干扰 5-seed 长训的 final_seed0。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 30 \
  --resume outputs/checkpoints_formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt \
  --override n_env=4 \
  --checkpoint_dir outputs/checkpoints_formation/seed0_valid_latest_ep1623 \
  --results_dir outputs/checkpoints_formation/seed0_valid_latest_ep1623/results \
  --override dirs.figures_dir=outputs/checkpoints_formation/seed0_valid_latest_ep1623/figures \
  2>&1