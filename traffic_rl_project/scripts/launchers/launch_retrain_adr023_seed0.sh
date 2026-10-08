#!/usr/bin/env bash
# 【2026-10-02】ADR-023 口径 seed0 1400ep 重训启动器（ed_mod_coef = 1.0 全幅调制）。
#
# 为什么重跑：ADR-023 把 decompose 通道的 ED 调制带宽从 0.5 放宽到 1.0（全幅）⇒
# **动作空间语义变更** ⇒ 旧带宽（0.5）下产出的 ckpt/评估数值对新口径失效。
# 旧运行 `outputs/checkpoints_formation/adr021_1400ep_seed0`（ep55 后主动停掉）原样保留，
# 仅作"旧带宽口径"留痕，不覆盖、不删除（见 ADR-023「后果」）。
#
# 调用方式（同 ADR-021 启动器，教训 LRN-20261001-014）：
#   ① 用户自己的 WSL 终端（数天级长跑首选，可安全断开）：
#        cd /mnt/d/Code/MultiAgent/traffic_rl_project
#        nohup setsid bash scripts/launchers/launch_retrain_adr023_seed0.sh \
#          > outputs/logs/diagnostics/log_retrain_adr023_seed0_20261002.txt 2>&1 < /dev/null &
#   ② IDE 的 Shell 工具：nohup/setsid 无效（工具返回时回收派生进程），须用工具的后台模式
#      并让本脚本**前台等待**（exec python 顶替 bash 成为该调用的直接子进程）。
#
# 恢复（ADR-019 续训；--episodes 语义 = 「总目标集数」）：
#   python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
#     --seed 0 --episodes 1400 --resume latest \
#     --checkpoint_dir outputs/checkpoints_formation/adr023_1400ep_seed0 \
#     --results_dir outputs/checkpoints_formation/adr023_1400ep_seed0/results \
#     --override dirs.figures_dir=outputs/checkpoints_formation/adr023_1400ep_seed0/figures
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints_formation/adr023_1400ep_seed0 \
  --results_dir outputs/checkpoints_formation/adr023_1400ep_seed0/results \
  --override dirs.figures_dir=outputs/checkpoints_formation/adr023_1400ep_seed0/figures