#!/usr/bin/env bash
# 【2026-10-04】沙盒启动器：ADR-029（牵引进入安全层 + EBI 紧急不被动作 AB 源压过）训练级验证。
#
# 目的：修复"牵引绕过安全层"根因后，验证训练态 gap_min<0（虚拟穿透）是否归零、
#       单集 |R| 是否回到 ~1e4 量级、vstd 是否无阶跃（与 v3/v4 基线同配置同 seed 对照）。
# 与 _debug_gapv4_bounded 同配置（剖面/编组/窗口/奖励 v4 一致），仅 src 修复生效（ADR-029），
# 产物目录改为 _debug_gapv5_adr029_slice16k，不覆盖 v4 旧产物。
#
# 监控判据：gap_min<0 归零；峰值/band/最小列距三项 ≥ 规则基线；vstd 无阶跃。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python -u run_training.py \
  --experiment configs/experiments/_debug_train_method_slice16k.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints/formation/_debug_gapv5_adr029_slice16k \
  --results_dir outputs/checkpoints/formation/_debug_gapv5_adr029_slice16k/results \
  --override dirs.figures_dir=outputs/checkpoints/formation/_debug_gapv5_adr029_slice16k/figures