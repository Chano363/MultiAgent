#!/bin/bash
# 安全层源头门控（高力禁新AB源）验证短训（30ep）：确认 ep21-30 长时程不再间歇破线
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 30 \
  --checkpoint_dir outputs/diag_53km_abgate/seed0 \
  --results_dir outputs/diag_53km_abgate/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_abgate/seed0/figures \
  > outputs/diag_53km_abgate_seed0.log 2>&1