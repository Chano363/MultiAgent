#!/usr/bin/env bash
# 5-seed 并行编排（2026-09-20 接手串行 job-f15928，诊断出单核瓶颈后改写）。
# 根因：n_env=4 在 train_runner.py:156 为纯串行 for 循环（非线程/进程），整训练单核跑，
#      且 launch_final_5seed.sh 在一个进程内前台顺序跑 seed0→4 → 12 核只用了 ~1 核。
# 本方案：每个 seed 独立后台进程（各占 1 核），wait 聚合；物理保真零改动（不动 train.py/mappo_agent.py）。
#   墙钟：5-seed 串行 ~5.7天 → 并行 ~2.4天（= 最长单 seed 1400ep）。
# 各 seed 从原始 resume 权重续训 1400ep 窗口，语义与旧串行脚本完全一致（可复现）。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/logs_final_parallel

run_seed () {
  local seed="$1" resume="$2"
  echo "[parallel] seed${seed} START $(date) | resume=$resume"
  python run_training.py \
    --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
    --seed "$seed" --episodes 1400 --resume "$resume" --override n_env=4 \
    --checkpoint_dir "outputs/checkpoints_formation/final_seed${seed}" \
    --results_dir "outputs/checkpoints_formation/final_seed${seed}/results" \
    --override "dirs.figures_dir=outputs/checkpoints_formation/final_seed${seed}/figures" \
    > "outputs/logs_final_parallel/seed${seed}.log" 2>&1
  echo "[parallel] seed${seed} DONE $(date)"
}

# 并行后台，`wait` 保持本包装进程前台存活直至全部完成（规避 wrapper 回收子进程）
run_seed 0 outputs/checkpoints_formation/seed0_valid_lean/mappo_fleet_best_dec_ad2_cp_seed0.pt &
run_seed 1 outputs/checkpoints_formation/seed1/mappo_fleet_best_dec_ad2_cp_seed1.pt &
run_seed 2 outputs/checkpoints_formation/seed2/mappo_fleet_best_dec_ad2_cp_seed2.pt &
run_seed 3 outputs/checkpoints_formation/seed3/mappo_fleet_best_dec_ad2_cp_seed3.pt &
run_seed 4 outputs/checkpoints_formation/seed4/mappo_fleet_best_dec_ad2_cp_seed4.pt &
wait
echo "ALL 5 SEEDS COMPLETE $(date)"