#!/bin/bash
# 方案3-A：curriculum 收窄至 1200 步，验证 1500->1200 是否消灭零星破线（全程 ≤1000kN）
# 前提：方案2 (1500步) 部分成功——消除整集崩溃 (best +12688) 但 4/7 集零星破线。
# 依据：收窄 horizon 被证实为治崩有效杠杆，1200 步仍 < 53km 物理 ~1900 步，够用。
# 与方案2/1 唯一差异：curriculum 上限 1500 -> 1200。
set -e
cd /mnt/d/Code/MultiAgent/traffic_rl_project
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 22 \
  --override "curriculum=500:0,1000:10,1200:20" \
  --override n_env=4 --override warm_start=True --override bc_episodes=3 --override bc_epochs=30 \
  --override log_interval=3 \
  --checkpoint_dir outputs/diag_53km_p3_curric1200/seed0 \
  --results_dir outputs/diag_53km_p3_curric1200/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_p3_curric1200/seed0/figures