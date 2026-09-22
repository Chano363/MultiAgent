#!/bin/bash
# 【2026-09-10 curriculum 退火验证】诊断结论：ep21(global_ep=20) 坍塌 = curriculum 1000→2000 步
# 跳变触发 MAPPO 长时程 on-policy 训练动力学崩溃（ep1-20 同 seed 完全一致，两轮独立验证）。
# 退火杠杆：把 1000→2000→3000 跨越放缓为每 10ep 增 500 步，让策略在每档位充分稳定。
# 验证判据：ep21-46（≥2000 步，最高 3000 步）车钩力峰值持续 ≤1000kN、viol≈0（原 ep21 即破线 1735kN）。
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 46 \
  --override 'curriculum=500:0,1000:10,1500:20,2000:30,2500:40,3000:50' \
  --checkpoint_dir outputs/diag_53km_anneal/seed0 \
  --results_dir outputs/diag_53km_anneal/seed0/results \
  --override dirs.figures_dir=outputs/diag_53km_anneal/seed0/figures \
  > outputs/diag_53km_anneal_seed0.log 2>&1