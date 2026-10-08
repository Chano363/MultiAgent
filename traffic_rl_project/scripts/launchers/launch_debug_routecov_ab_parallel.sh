#!/usr/bin/env bash
# 【2026-10-06】L2 路线覆盖 A/B —— 并行版：OFF / ON 两臂同时跑（12 核，各占 ~1 核）。
#
# 与 launch_debug_routecov_ab_seed0.sh（串行）产物完全一致，仅改为并行以省一半墙钟：
#   串行 ≈ 2×184min；并行 ≈ 184min（contention 有限）。
# 两臂的唯一差异 = env_cfg.start_randomization（OFF=无，ON=enabled+seed0）。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

python -u run_training.py \
  --experiment configs/experiments/_debug_routecov_off_slice16k.yaml \
  --seed 0 > outputs/logs/diagnostics/log_debug_routecov_off_slice16k_seed0_20261006.txt 2>&1 &
PID_OFF=$!

python -u run_training.py \
  --experiment configs/experiments/_debug_routecov_on_slice16k.yaml \
  --seed 0 > outputs/logs/diagnostics/log_debug_routecov_on_slice16k_seed0_20261006.txt 2>&1 &
PID_ON=$!

echo "OFF pid=$PID_OFF  ON pid=$PID_ON  （并行运行）"
wait $PID_OFF; echo "OFF 臂完成"
wait $PID_ON;  echo "ON 臂完成"
echo '########## DONE ##########'