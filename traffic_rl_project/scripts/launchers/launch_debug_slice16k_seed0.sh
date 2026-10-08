#!/usr/bin/env bash
# 【2026-10-03】训练方法调试沙盒启动器（ADR-025 修复后的快速迭代）。
#
# 目的：用最短可测的轮数（80 ep）判断 ADR-025 三项修复是否止住了"越练越差"的震荡。
# 剖面 = shuozhou_real_53km_slice16k（53km 的 21.06–37.02km 切片 ≈15.7km，物理/编组/安全层
# 与主口径一致）。单集窗口保持 ≤1200 步（≥90s 滞后），否则测不到真机制。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
#
#   nohup setsid bash scripts/launchers/launch_debug_slice16k_seed0.sh \
#     > outputs/logs/diagnostics/log_debug_slice16k_adr025_seed0_20261003.txt 2>&1 < /dev/null &
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python -u run_training.py \
  --experiment configs/experiments/_debug_train_method_slice16k.yaml \
  --seed 0