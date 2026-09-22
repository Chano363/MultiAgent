#!/bin/bash
# 100% 动力学（Bug 3 修复后）论文数据全量评估：主对比 + 随机化 + ETCS + 压力消融 + 安全层消融
#
# 前置：outputs/run_full_training_100pct_5seed.sh 训练完成（M1 5 seed）
#        outputs/run_dqn_100pct_3seed.sh 训练完成（DQN-fair 3 seed）
#
# 输出：outputs/eval_100pct_all.log（完整汇总，带时间戳）
# 说明：所有方法统一 --etcs（ETCS 兜底防追尾，聚焦控制质量）。
set -u
cd "$(dirname "$0")/.."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl

CKPT=outputs/checkpoints_100pct
DQN=outputs/checkpoints_100pct/dqn
LOG=outputs/eval_100pct_all.log
: > "$LOG"

M1="outputs/checkpoints_100pct/mappo_fleet_best_cp_seed0.pt"
# ⚠️ 协议修正（2026-09-03）：历史论文协议 = 朔黄线主剖面 3000 步。
# evaluate_m1_m3_long.py 默认 MAX_STEPS=35000（35km 剖面专用），
# 若不传 --max_steps 3000 会跑 35000 步导致间距漂移巨大（假崩溃）。
STEPS="--max_steps 3000"

echo "############ 1) 主对比（朔黄线 3000 步，固定初速，确定性，--etcs） ############" | tee -a "$LOG"

echo "=== M1 群组协同（best cp seed0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "=== M3 单列独立（δ=0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "=== M-MPC-fair 公平版（分层 fairmpc）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py fairmpc - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "=== M-MPC 公平版（直接加速 mpc_dir）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mpc_dir - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "=== M-MPC-rule（直接加速+规则内层兜底，P2 公平基线）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mpc_rule - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "=== M-DQN-fair（100pct 重训 seed0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mdqn_fair - $STEPS --etcs --n_seed 1 --dqn_seed 0 --dqn_dir "$DQN" 2>&1 | tee -a "$LOG"

echo "=== Coast 惰行 baseline ===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py coast - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "############ 2) M1 5 seed 评估（随机化初态 55-75km/h，--etcs，统计稳健性） ############" | tee -a "$LOG"
for s in 0 1 2 3 4; do
    echo "--- M1 seed$s ---" | tee -a "$LOG"
    python src/evaluation/evaluate_m1_m3_long.py m1 "outputs/checkpoints_100pct/mappo_fleet_best_cp_seed${s}.pt" \
        $STEPS --etcs --n_seed 5 --randomize_init 2>&1 | tee -a "$LOG"
done

echo "############ 3) 压力消融（gap 100→40，M1 vs M3，--etcs） ############" | tee -a "$LOG"
for gap in 100 80 60 40; do
    echo "--- target_gap=$gap ---" | tee -a "$LOG"
    python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 5 --randomize_init --target_gap "$gap" 2>&1 | tee -a "$LOG"
    python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 5 --randomize_init --target_gap "$gap" 2>&1 | tee -a "$LOG"
done

echo "############ 4) 安全层消融（--no_coupler，M1 vs M-DQN 无安全层，--etcs） ############" | tee -a "$LOG"
echo "--- M1 no_coupler ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 3 --randomize_init --no_coupler 2>&1 | tee -a "$LOG"

echo "############ 5) 第二剖面泛化（long_downhill_20km，--etcs） ############" | tee -a "$LOG"
echo "--- M1 20km ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 5 --randomize_init --grade long_downhill_20km 2>&1 | tee -a "$LOG"
echo "--- M3 20km ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 5 --randomize_init --grade long_downhill_20km 2>&1 | tee -a "$LOG"

echo "############ 6) 5 列扩展（--num_trains 5，M1 vs M3，--etcs） ############" | tee -a "$LOG"
echo "--- M1 5列 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 3 --randomize_init --num_trains 5 2>&1 | tee -a "$LOG"
echo "--- M3 5列 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 3 --randomize_init --num_trains 5 2>&1 | tee -a "$LOG"

echo "############ ALL DONE ############" | tee -a "$LOG"
