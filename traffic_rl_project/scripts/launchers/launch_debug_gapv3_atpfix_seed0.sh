#!/usr/bin/env bash
# 【2026-10-04】沙盒启动器：ATP 优先级修复（断开"为压车钩力放掉防追尾制动"的自毁闭环）
# + ADR-026 v3 间距奖励。与 _debug_train_method_slice16k.yaml 同配置（剖面/编组/窗口一致），
# 仅产物目录改为 _debug_gapv3_atpfix_slice16k，不覆盖 v3 旧产物（_debug_gapv3_slice16k）。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python -u run_training.py \
  --experiment configs/experiments/_debug_train_method_slice16k.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints/formation/_debug_gapv3_atpfix_slice16k \
  --results_dir outputs/checkpoints/formation/_debug_gapv3_atpfix_slice16k/results \
  --override dirs.figures_dir=outputs/checkpoints/formation/_debug_gapv3_atpfix_slice16k/figures