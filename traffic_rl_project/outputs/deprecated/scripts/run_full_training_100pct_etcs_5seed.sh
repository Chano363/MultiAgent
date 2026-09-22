#!/bin/bash
# 100% 动力学 + ETCS 训练对齐的 M1 重训 5 seed —— 修复"训练/评估分布不一致"
#
# 背景（诊断-2026-09-03）：无 ETCS 训练的 M1 在 100% 动力学下协同价值消失（M3>M1）。
# 根因假设：① 训练无 ETCS / 评估有 ETCS 分布不一致；② 训练 adj_coef=0.3 但评估 0.1。
# 本脚本：--enable_etcs（训练与评估对齐）+ --adj_coef 0.1（与评估一致）。
# 输出：outputs/checkpoints_100pct_etcs / outputs/results_100pct_etcs（不覆盖历史）
set -u
cd "$(dirname "$0")/.."

CKPT=outputs/checkpoints_100pct_etcs
RES=outputs/results_100pct_etcs
EPISODES=200
CURR="1000:66,3000:132"

mkdir -p "$CKPT" "$RES"

run_seed() {
    local s=$1
    echo "[$(date +%H:%M:%S)] ===== 100pct+ETCS seed$s 开始（200ep，adj_coef=0.1）====="
    /home/chano/miniconda3/envs/traffic_rl/bin/python \
        src/trainer/train_fleet.py \
        --episodes $EPISODES --max_steps 300 \
        --curriculum "$CURR" --seed "$s" --hierarchical \
        --adj_coef 0.1 --enable_etcs \
        --checkpoint_dir "$CKPT" --results_dir "$RES" \
        > "outputs/train_100pct_etcs_seed${s}.log" 2>&1
    echo "[$(date +%H:%M:%S)] ===== 100pct+ETCS seed$s 结束 ====="
}

for s in 0 1 2 3 4; do
    run_seed $s &
done
wait
echo "全部 5 seed ETCS 训练完成"

for s in 0 1 2 3 4; do
    echo "--- seed$s ---"
    grep -E "最佳奖励|最终平均奖励" "outputs/train_100pct_etcs_seed${s}.log" 2>/dev/null | tail -2
done
