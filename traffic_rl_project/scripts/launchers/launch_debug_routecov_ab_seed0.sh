#!/usr/bin/env bash
# 【2026-10-06】L2 路线覆盖 A/B 启动器：训练起点随机化 on/off（slice16k 沙盒，seed 0）。
#
# 目的（DIAGNOSTICS_2026-10「路线覆盖/看不全路」）：验证"训练起点随机化"能否消除
#   固定起点的坡度 OOD（L1：固定起点仅覆盖 −1.5‰ 单坡段，评估 83.9% 步落在训练未见
#   坡度区间），并确认不引入回归（viol / 峰值 / band / 最小列距 不劣于 OFF 臂）。
# 两臂唯一差异 = env_cfg.start_randomization（OFF=无，ON=enabled+seed0）；配置其余全同。
#
# 判据：ON 臂 long_eval 完整剖面 峰值/band/最小列距 ≥ OFF 臂，且训练态 gap_min≥0、viol 不升。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

echo '########## OFF 臂（固定起点）##########'
python -u run_training.py \
  --experiment configs/experiments/_debug_routecov_off_slice16k.yaml \
  --seed 0 2>&1 | tee outputs/logs/diagnostics/log_debug_routecov_off_slice16k_seed0_20261006.txt

echo '########## ON 臂（起点随机化）##########'
python -u run_training.py \
  --experiment configs/experiments/_debug_routecov_on_slice16k.yaml \
  --seed 0 2>&1 | tee outputs/logs/diagnostics/log_debug_routecov_on_slice16k_seed0_20261006.txt

echo '########## DONE ##########'