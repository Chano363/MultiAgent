#!/bin/bash
# 并行多环境 n_env 冒烟（2ep，快速验证逻辑不崩、多轨迹共享buffer统一update）
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 2 \
  --override n_env=4 --override parallel_traj_len=300 \
  --override random_init_speed=True \
  --checkpoint_dir outputs/diag_53km_nenv_smoke/seed0 \
  --results_dir outputs/diag_53km_nenv_smoke/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_nenv_smoke/seed0/figures \
  > outputs/diag_53km_nenv_smoke.log 2>&1