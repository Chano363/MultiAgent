#!/usr/bin/env bash
# 【2026-10-01】ADR-021 口径 seed0 1400ep 重训启动器。
#
# 为什么用脚本而不是一行命令：`cd && source && conda activate && python … &`
# 会把**整条链**放进后台子 shell；父 bash 退出时该子 shell 收到 SIGHUP 直接死掉
# （连重定向的 log 文件都不会创建）。故把环境激活与 exec python 固化进本脚本，
# 由调用方决定"如何让它脱离会话"。
#
# ⚠️ 两种调用场合行为不同（2026-10-01 实测，详见 LEARNINGS.md LRN-20261001-014）：
#   ① 用户自己的 WSL 终端 —— 下面的 nohup/setsid 用法**有效**，可安全断开、退出 IDE 也不受影响
#      （推荐用于数天级长跑）。
#   ② IDE 的 Shell 工具 —— **无效**：该工具在调用返回时会回收本次调用派生的全部进程，
#      setsid/nohup 都挡不住（实测探针 `nohup setsid sleep 90 … &` 下次调用即查不到）。
#      在工具内请改用后台模式，并让本脚本**前台等待**：
#        wsl -e bash -lc "cd /mnt/d/Code/MultiAgent/traffic_rl_project && \
#          bash scripts/launchers/launch_retrain_adr021_seed0.sh > outputs/logs/diagnostics/log_retrain_adr021_seed0_20261001.txt 2>&1"
#      （配 run_in_background=true；进程随该后台作业存活，上限 = IDE 会话）
#
# 用法（用户 WSL 终端，脱离会话，可安全断开）：
#   cd /mnt/d/Code/MultiAgent/traffic_rl_project
#   nohup setsid bash scripts/launchers/launch_retrain_adr021_seed0.sh \
#     > outputs/logs/diagnostics/log_retrain_adr021_seed0_20261001.txt 2>&1 < /dev/null &
#
# 恢复（若进程被中断，ADR-019 续训：--episodes 语义为「总目标集数」）：
#   python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
#     --seed 0 --episodes 1400 --resume latest \
#     --checkpoint_dir outputs/checkpoints/formation/adr021_1400ep_seed0 \
#     --results_dir outputs/checkpoints/formation/adr021_1400ep_seed0/results \
#     --override dirs.figures_dir=outputs/checkpoints/formation/adr021_1400ep_seed0/figures
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints/formation/adr021_1400ep_seed0 \
  --results_dir outputs/checkpoints/formation/adr021_1400ep_seed0/results \
  --override dirs.figures_dir=outputs/checkpoints/formation/adr021_1400ep_seed0/figures