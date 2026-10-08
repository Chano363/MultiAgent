#!/usr/bin/env bash
# 5-seed 续训到 1400ep（ADR-018 治本后代码，2026-09-30）。
# 起点 = final_seed{N}/mappo_fleet_best_*.pt（09-20~22 中断的续训产物，ep~520-992/1400）。
# 输出 = final_seed{N}_v2/（新目录，防覆盖历史）。
# 用 --override start_ep=<当前已到 ep> 让 curriculum 按实际进度解析。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/logs_final_v2

run_seed () {
  local seed="$1" resume="$2" start_ep="$3"
  echo "[v2] seed${seed} START $(date) | resume=$resume start_ep=$start_ep"
  python run_training.py \
    --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
    --seed "$seed" --episodes 1400 --resume "$resume" \
    --override start_ep="$start_ep" --override n_env=4 \
    --checkpoint_dir "outputs/checkpoints_formation/final_seed${seed}_v2" \
    --results_dir "outputs/checkpoints_formation/final_seed${seed}_v2/results" \
    --override "dirs.figures_dir=outputs/checkpoints_formation/final_seed${seed}_v2/figures" \
    > "outputs/logs_final_v2/seed${seed}.log" 2>&1
  echo "[v2] seed${seed} DONE $(date)"
}

run_seed 0 outputs/checkpoints_formation/final_seed0/mappo_fleet_best_dec_ad2_cp_seed0.pt 992 &
run_seed 1 outputs/checkpoints_formation/final_seed1/mappo_fleet_best_dec_ad2_cp_seed1.pt 992 &
run_seed 2 outputs/checkpoints_formation/final_seed2/mappo_fleet_best_dec_ad2_cp_seed2.pt 521 &
run_seed 3 outputs/checkpoints_formation/final_seed3/mappo_fleet_best_dec_ad2_cp_seed3.pt 661 &
run_seed 4 outputs/checkpoints_formation/final_seed4/mappo_fleet_best_dec_ad2_cp_seed4.pt 671 &
wait
echo "ALL 5 SEEDS V2 COMPLETE $(date)"