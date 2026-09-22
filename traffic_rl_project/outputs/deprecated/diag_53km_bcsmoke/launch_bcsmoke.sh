#!/bin/bash
# BC 热启动冒烟（1ep，确认采集+预训练不崩）
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 1 \
  --override warm_start=True --override bc_episodes=2 --override bc_epochs=5 \
  --checkpoint_dir outputs/diag_53km_bcsmoke/seed0 \
  --results_dir outputs/diag_53km_bcsmoke/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_bcsmoke/seed0/figures \
  > outputs/diag_53km_bcsmoke.log 2>&1