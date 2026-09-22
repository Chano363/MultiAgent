#!/bin/bash
# 回滚车钩力惩罚后验证短训（30ep）：确认 kl/value 震荡源消除后 ep21-30 长时程是否收敛
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 30 \
  --checkpoint_dir outputs/diag_53km_rollback/seed0 \
  --results_dir outputs/diag_53km_rollback/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_rollback/seed0/figures \
  > outputs/diag_53km_rollback_seed0.log 2>&1