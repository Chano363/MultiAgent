#!/bin/bash
# 2026-09-06 R0 物理下分层 platoon 线重训（用户要求自动跑 + 5 seed）
#   L1: 第1层规则循环制动 MAPPO（seed0, 15000步完整协议）
#   L2: 3列 platoon M1 第2层 MAPPO（200ep, curriculum 1000:66/3000:132, 5 seed）
# 输出到 outputs/checkpoints_r0_l1, outputs/checkpoints_r0_platoon_m1（不覆盖历史）
# OMP_NUM_THREADS=2 防 12 核机上多进程线程超订阅
set -u
cd "$(dirname "$0")/.."
PY=/home/chano/miniconda3/envs/traffic_rl/bin/python
mkdir -p outputs/logs_r0 outputs/checkpoints_r0_l1 outputs/checkpoints_r0_platoon_m1 \
         outputs/results_r0_l1 outputs/results_r0_platoon_m1

# ---- L1：第1层规则循环制动 MAPPO（seed0，curriculum 加速）----
echo "[$(date +%H:%M:%S)] ===== L1 seed0 开始（300ep, curriculum 300-1000-15000）====="
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY src/trainer/train_cyclic_braking.py \
  --episodes 300 --grade shuozhou_23800 --seed 0 --curriculum 300-1000-15000 \
  --checkpoint_dir outputs/checkpoints_r0_l1 --results_dir outputs/results_r0_l1 \
  > outputs/logs_r0/train_l1_r0_seed0.log 2>&1
echo "[$(date +%H:%M:%S)] ===== L1 seed0 结束 ====="

# ---- L2：3列 platoon M1 第2层 MAPPO（5 seed，并行）----
EPISODES=200
CURR="1000:66,3000:132"
for s in 0 1 2 3 4; do
  echo "[$(date +%H:%M:%S)] ===== L2-M1 seed$s 后台开始 ====="
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY src/trainer/train_fleet.py \
    --episodes $EPISODES --max_steps 300 --curriculum "$CURR" --seed $s \
    --hierarchical --adj_coef 0.1 --enable_etcs \
    --checkpoint_dir outputs/checkpoints_r0_platoon_m1 \
    --results_dir outputs/results_r0_platoon_m1 \
    > outputs/logs_r0/train_platoon_m1_r0_seed${s}.log 2>&1 &
done

echo "[$(date +%H:%M:%S)] 等待 5 个 L2-M1 seed 完成"
wait
echo "[$(date +%H:%M:%S)] ===== 全部完成 ====="

for s in 0 1 2 3 4; do
  echo "--- L2-M1 seed$s ---"
  grep -E "最佳奖励|最终平均奖励|平均车钩力" outputs/logs_r0/train_platoon_m1_r0_seed${s}.log 2>/dev/null | tail -3
done
echo "--- L1 ---"
grep -E "最佳奖励|最终平均奖励|平均车钩力" outputs/logs_r0/train_l1_r0_seed0.log 2>/dev/null | tail -3
echo "[$(date +%H:%M:%S)] 汇总终了"