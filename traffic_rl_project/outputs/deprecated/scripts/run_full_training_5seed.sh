#!/bin/bash
# 全独立从头训练 M1 群组协同 5 seed（新物理下，无热启动）
#
# 用法（务必在【常驻终端】里运行，不能关闭窗口/标签页）：
#   bash outputs/run_full_training_5seed.sh            # 串行（默认，最稳）
#   bash outputs/run_full_training_5seed.sh --parallel # 并行 5 进程（快，吃 CPU/内存）
#
# 配置：200 回合，curriculum 1000@ep66,3000@ep132（前 66 回合 300 步，
#       中间 66 回合 1000 步，最后 68 回合 3000 步——与评估长度一致）
# 输出：outputs/checkpoints_full/*.pt + outputs/results_full/train_history_*.json/csv
# 预估：串行 ~100 分钟/seed；并行 5 seed 视 CPU 核数约 2~4 小时
set -u
cd "$(dirname "$0")/.."

MODE="${1:-seq}"                       # seq 或 --parallel
CKPT=outputs/checkpoints_full
RES=outputs/results_full
EPISODES=200
CURR="1000:66,3000:132"                # 绝对全局回合边界（ep66 起 1000 步，ep132 起 3000 步）

mkdir -p "$CKPT" "$RES"

run_seed() {
    local s=$1
    echo "[$(date +%H:%M:%S)] ===== seed$s 开始（200ep，curriculum=$CURR）====="
    /home/chano/miniconda3/envs/traffic_rl/bin/python \
        src/trainer/train_fleet.py \
        --episodes $EPISODES --max_steps 300 \
        --curriculum "$CURR" --seed "$s" --hierarchical \
        --checkpoint_dir "$CKPT" --results_dir "$RES" \
        > "outputs/train_full_seed${s}.log" 2>&1
    echo "[$(date +%H:%M:%S)] ===== seed$s 结束，日志 outputs/train_full_seed${s}.log ====="
}

if [ "$MODE" = "--parallel" ]; then
    echo "并行模式：5 个 seed 同时训练（若机器 CPU 核数 <8 或内存 <16GB 建议改串行）"
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

# 结束前打印各 seed 摘要
for s in 0 1 2 3 4; do
    echo "--- seed$s ---"
    grep -E "最佳奖励|最终平均奖励" "outputs/train_full_seed${s}.log" 2>/dev/null | tail -2
done
