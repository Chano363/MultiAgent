#!/bin/bash
# 【2026-09-10 fleet BC 热启动验证】治诊断-2026-09-10 长时程训练坍塌。
# 关键设计：沿用【原陡峭 curriculum 2000:20】（前 6 轮 ep21 必崩点），仅加
# warm_start。若 BC 后 ep21（2000 步）不再塌、peak<=1000kN/viol≈0 持续到 ep46，即证明
# 热启动让 RL 从安全规则域出发躲过随机探索吸态，是治长时程坍塌的解药。
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 46 \
  --override warm_start=True \
  --override bc_episodes=3 \
  --override bc_epochs=30 \
  --checkpoint_dir outputs/diag_53km_bc/seed0 \
  --results_dir outputs/diag_53km_bc/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_bc/seed0/figures \
  > outputs/diag_53km_bc_seed0.log 2>&1