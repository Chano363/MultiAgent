#!/bin/bash
# 车钩力惩罚强化（真实峰值 + 破线二次硬惩罚 + 0.9x早触发）验证：30ep，观察长时程是否仍破线。
# 相比上一轮（ep21-30 破线 1200-1735kN），验证奖励塑形能否让 RL 不再暴力循环制动。
# 启动：setsid nohup bash launch_diag.sh >/dev/null 2>&1 &
REPO=/mnt/d/Code/MultiAgent/traffic_rl_project
cd "$REPO" || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 30 \
  --checkpoint_dir outputs/diag_53km_coupler_pen/seed0 \
  --results_dir outputs/diag_53km_coupler_pen/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_coupler_pen/seed0/figures \
  > outputs/diag_53km_relanchor_seed0.log 2>&1