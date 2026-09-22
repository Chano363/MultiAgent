#!/bin/bash
# 方案1（HANDOFF §8.3 / 诊断1581 受控修正）：
#   BC warm_start + n_env=4 + curriculum 渐进起步(parallel_traj_len=0)
#   = 并行结构 + 安全起点 + 渐进到2000档（原崩点）
# 判据：ep21-24@2000档 peakCoupler≤1000kN 且 viol≈0 才算 PASS
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 24 \
  --override n_env=4 \
  --override warm_start=True \
  --override bc_episodes=3 --override bc_epochs=30 \
  --override log_interval=3 \
  --checkpoint_dir outputs/diag_53km_p1_bcnenv_curric/seed0 \
  --results_dir outputs/diag_53km_p1_bcnenv_curric/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_p1_bcnenv_curric/seed0/figures \
  > outputs/diag_53km_p1_bcnenv_curric_seed0.log 2>&1