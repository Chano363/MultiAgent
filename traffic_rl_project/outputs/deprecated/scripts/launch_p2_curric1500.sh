#!/bin/bash
# 方案2（/goal 先1后2）：curriculum 上限锁 1500 步（避开 2000 步崩点）
#   基于方案1铁证：500/1000 档全绿（viol=0, peak 508~808kN, reward 稳爬），唯 >=2000 步崩。
#   53km@~27.8m/s≈1900 步，1500 步已物理够用（收敛接受较短 horizon，不盲增）。
#   仍保留 BC warm_start + n_env=4（正贡献已证）。
# 判据：ep21-24@1500档 peakCoupler<=1000kN 且 viol≈0 → PASS，证明避开崩点可训到物理够用 horizon
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 26 \
  --override curriculum="500:0,1000:10,1500:20" \
  --override n_env=4 \
  --override warm_start=True \
  --override bc_episodes=3 --override bc_epochs=30 \
  --override log_interval=3 \
  --checkpoint_dir outputs/diag_53km_p2_curric1500/seed0 \
  --results_dir outputs/diag_53km_p2_curric1500/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_p2_curric1500/seed0/figures \
  > outputs/diag_53km_p2_curric1500_seed0.log 2>&1