#!/bin/bash
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 44 \
  --override n_env=4 --override parallel_traj_len=2000 \
  --override random_init_speed=True \
  --checkpoint_dir outputs/diag_53km_nenv/seed0 \
  --results_dir outputs/diag_53km_nenv/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_nenv/seed0/figures \
  > outputs/diag_53km_nenv_seed0.log 2>&1