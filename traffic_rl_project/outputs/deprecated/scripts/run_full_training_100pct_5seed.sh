#!/bin/bash
# 100% 动力学（Bug 3 修复后）M1 群组协同重训 5 seed —— 论文数据重跑
#
# 背景：历史 checkpoints_full（8/30-31）在 75% 动力学（Newmark 欠松弛 bug）下训练，
# Bug 3 修复后需在 100% 动力学下重训，论文/汇报数值以本批为准。
# 配方与 run_full_training_5seed.sh 一致：200ep，curriculum 1000@ep66,3000@ep132，hierarchical。
# 输出到新目录 outputs/checkpoints_100pct / outputs/results_100pct（不覆盖历史）。
#
# 用法（常驻终端）：
#   bash outputs/run_full_training_100pct_5seed.sh            # 串行
#   bash outputs/run_full_training_100pct_5seed.sh --parallel # 并行 5 进程
set -u
cd "$(dirname "$0")/.."

MODE="${1:-seq}"
CKPT=outputs/checkpoints_100pct
RES=outputs/results_100pct
EPISODES=200
CURR="1000:66,3000:132"

mkdir -p "$CKPT" "$RES"

run_seed() {
    local s=$1
    echo "[$(date +%H:%M:%S)] ===== 100pct seed$s 开始（200ep，curriculum=$CURR）====="
    /home/chano/miniconda3/envs/traffic_rl/bin/python \
        src/trainer/train_fleet.py \
        --episodes $EPISODES --max_steps 300 \
        --curriculum "$CURR" --seed "$s" --hierarchical \
        --checkpoint_dir "$CKPT" --results_dir "$RES" \
        > "outputs/train_100pct_seed${s}.log" 2>&1
    echo "[$(date +%H:%M:%S)] ===== 100pct seed$s 结束，日志 outputs/train_100pct_seed${s}.log ====="
}

if [ "$MODE" = "--parallel" ]; then
    echo "并行模式：5 个 seed 同时训练"
    for s in 0 1 2 3 4; do
        run_seed $s &
    done
    wait
    echo "全部 5 seed 训练完成"
else
    for s in 0 1 2 3 4; do
        run_seed $s
    done
    echo "全部 5 seed 训练完成"
fi

for s in 0 1 2 3 4; do
    echo "--- seed$s ---"
    grep -E "最佳奖励|最终平均奖励" "outputs/train_100pct_seed${s}.log" 2>/dev/null | tail -2
done
