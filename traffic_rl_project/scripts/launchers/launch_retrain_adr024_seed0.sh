#!/usr/bin/env bash
# 【2026-10-02】ADR-024 口径 seed0 1400ep 重训启动器（ed_mod_coef = 0.5 半幅调制，回退）。
#
# 为什么再次重跑：ADR-023 把 decompose 通道的 ED 调制带宽放宽到 1.0（全幅）以消除 NMPC
# 桥接的"越权请求"截断，但完整剖面 A/B 实测证明"对 MPC 无收益、对 RL 有害"（1.0 允许策略
# 整幅撤销规则层 ED ⇒ 长下坡持续破 1000 kN）。ADR-024 遂回退到 0.5，保留 ADR-023 的两项
# 结构性改进（派生常量 + metadata 键）。动作空间语义再次变更 ⇒ 两个 1.0 口径产物均失效。
# `adr023_1400ep_seed0`（ep205 停）、`adr021_1400ep_seed0`（ep55 停）原样保留，仅作留痕。
#
# 调用方式（同 ADR-021/023 启动器，教训 LRN-20261001-014）：
#   ① 用户自己的 WSL 终端（数天级长跑首选，可安全断开）：
#        cd /mnt/d/Code/MultiAgent/traffic_rl_project
#        nohup setsid bash scripts/launchers/launch_retrain_adr024_seed0.sh \
#          > outputs/logs/diagnostics/log_retrain_adr024_seed0_20261002.txt 2>&1 < /dev/null &
#   ② IDE 的 Shell 工具：nohup/setsid 无效（工具返回时回收派生进程），须用工具的后台模式
#      并让本脚本**前台等待**（exec python 顶替 bash 成为该调用的直接子进程）。
#
# 恢复（ADR-019 续训；--episodes 语义 = 「总目标集数」）：
#   python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
#     --seed 0 --episodes 1400 --resume latest \
#     --checkpoint_dir outputs/checkpoints_formation/adr024_1400ep_seed0 \
#     --results_dir outputs/checkpoints_formation/adr024_1400ep_seed0/results \
#     --override dirs.figures_dir=outputs/checkpoints_formation/adr024_1400ep_seed0/figures
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints_formation/adr024_1400ep_seed0 \
  --results_dir outputs/checkpoints_formation/adr024_1400ep_seed0/results \
  --override dirs.figures_dir=outputs/checkpoints_formation/adr024_1400ep_seed0/figures