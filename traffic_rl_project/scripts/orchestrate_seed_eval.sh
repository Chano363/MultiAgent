#!/bin/bash
# 幂等编排：推进 seed1-4 训练 → 全部完成后启动逐-seed D-RL 评测。
# 每次由定时任务调用（只汇报、必要时启动一个任务），不重复启动已在跑的进程。
# 训练 seed0 已由 12291 的 all 主评估覆盖其 D-RL；本脚本只负责 seed1-4 的 D-RL 评测。
set -u

cd /mnt/d/Code/MultiAgent/traffic_rl_project
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl

GRADE=shuozhou_real_53km
MAX=36000
CK=outputs/checkpoints_formation
RES=outputs/results_decompose

# 完成标记 = 最终 ep120 checkpoint 存在（best 仅是训练中最佳存档，不等于完成）
done_marker() { echo "$CK/seed$1/mappo_fleet_ep120_dec_ad2_cp_seed$1.pt"; }
train_done() { [ -f "$(done_marker $1)" ]; }

# 每 seed 取评估用 checkpoint（优先 ep120，否则 fallback best）
ckpt_of() {
  if [ -f "$(done_marker $1)" ]; then
    echo "$(done_marker $1)"
  elif [ -f "$CK/seed$1/mappo_fleet_best_dec_ad2_cp_seed$1.pt" ]; then
    echo "$CK/seed$1/mappo_fleet_best_dec_ad2_cp_seed$1.pt"
  else
    echo ""
  fi
}

echo "=== 编排状态 $(date '+%F %T') ==="
for s in 1 2 3 4; do
  if train_done $s; then echo "seed$s 训练: 完成 ($(ckpt_of $s))"; else echo "seed$s 训练: 未完成"; fi
done

TRAIN_PID=$(pgrep -f "run_training.py --experiment" | head -1)
EVAL_PID=$(pgrep -f "evaluate_decompose.py --mode" | head -1)
[ -n "$TRAIN_PID" ] && echo "训练进程在跑: $TRAIN_PID"
[ -n "$EVAL_PID" ] && echo "评估进程在跑: $EVAL_PID"

# ---------- 训练推进（兜底：无训练进程且有未完成 seed 时启动下一个）----------
NEED=""
for s in 1 2 3 4; do
  if ! train_done $s; then NEED=$s; break; fi
done
if [ -n "$NEED" ] && [ -z "$TRAIN_PID" ]; then
  echo "→ 检测到 seed$NEED 未完成且无训练进程，启动训练..."
  nohup python run_training.py \
    --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
    --seed $NEED --episodes 120 \
    --override n_env=4 --override warm_start=True \
    --override bc_episodes=3 --override bc_epochs=30 --override log_interval=10 \
    --checkpoint_dir "$CK/seed$NEED" --results_dir "$CK/seed$NEED/results" \
    --override dirs.figures_dir="$CK/seed$NEED/figures" \
    > "outputs/train_formation_seed$NEED.log" 2>&1 &
fi

# ---------- 评测推进（全部训练完成 且 无训练/评估进程时，启动下一个 D-RL 评测）----------
ALL=1
for s in 1 2 3 4; do
  train_done $s || ALL=0
done

if [ "$ALL" = 1 ] && [ -z "$TRAIN_PID" ] && [ -z "$EVAL_PID" ]; then
  for s in 1 2 3 4; do
    ck=$(ckpt_of $s)
    out="$RES/eval_decompose_decompose_m1_ms${MAX}_s${s}_53km.json"
    if [ -n "$ck" ] && [ ! -f "$out" ]; then
      echo "→ 启动 seed$s D-RL 评测 (checkpoint=$ck)"
      nohup python src/evaluation/evaluate_decompose.py \
        --mode decompose_m1 --checkpoint "$ck" \
        --grade $GRADE --num_trains 3 --max_steps $MAX \
        --n_seed 5 --decision_interval 10 --out_suffix "_s${s}_53km" \
        > "outputs/eval_main_53km_s${s}.log" 2>&1 &
      break
    fi
  done
fi

# ---------- 汇总已生成的 D-RL 结果 ----------
echo "--- 已生成 D-RL 评测结果 ---"
for s in 1 2 3 4; do
  out="$RES/eval_decompose_decompose_m1_ms${MAX}_s${s}_53km.json"
  if [ -f "$out" ]; then echo "seed$s D-RL: $out"; else echo "seed$s D-RL: 未生成"; fi
done
if [ -f "$RES/eval_decompose_all_ms36000_s0_53km.json" ]; then
  echo "seed0 D-RL(all): $RES/eval_decompose_all_ms36000_s0_53km.json"
else
  echo "seed0 D-RL(all): 未生成（all 主评估运行中）"
fi