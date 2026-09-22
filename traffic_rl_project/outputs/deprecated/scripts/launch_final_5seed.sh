#!/usr/bin/env bash
# 铺 5-seed（seed0-4）全量 1400ep 主训练（治本杠杆已入 mappo_agent.py，2026-09-20）
# 策略：续训各 seed 干净 best 权重（已 BC warm_start，含安全行为）→ 延伸至 1400ep 总预算
#   前台顺序循环，规避 exec 破坏循环 / nohup& 被 job wrapper 终止的问题。
# 前置：2026-09-19 的 30ep 治本验证已 SUCCESS（viol 全0 / loss 小负 / 原发散区零复发）。
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

# seed0 从治本验证后的干净权重续训；seed1-4 从各自 120ep best 续训
for seed in 0 1 2 3 4; do
  case "$seed" in
    0) RESUME=outputs/checkpoints_formation/seed0_valid_lean/mappo_fleet_best_dec_ad2_cp_seed0.pt ;;
    1) RESUME=outputs/checkpoints_formation/seed1/mappo_fleet_best_dec_ad2_cp_seed1.pt ;;
    2) RESUME=outputs/checkpoints_formation/seed2/mappo_fleet_best_dec_ad2_cp_seed2.pt ;;
    3) RESUME=outputs/checkpoints_formation/seed3/mappo_fleet_best_dec_ad2_cp_seed3.pt ;;
    4) RESUME=outputs/checkpoints_formation/seed4/mappo_fleet_best_dec_ad2_cp_seed4.pt ;;
  esac
  echo "===== SEED $seed START $(date) | resume=$RESUME ====="
  python run_training.py \
    --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
    --seed "$seed" --episodes 1400 \
    --resume "$RESUME" \
    --override n_env=4 \
    --checkpoint_dir "outputs/checkpoints_formation/final_seed${seed}" \
    --results_dir "outputs/checkpoints_formation/final_seed${seed}/results" \
    --override "dirs.figures_dir=outputs/checkpoints_formation/final_seed${seed}/figures" \
    2>&1
  echo "===== SEED $seed DONE $(date) ====="
done
echo "ALL 5 SEEDS COMPLETE $(date)"