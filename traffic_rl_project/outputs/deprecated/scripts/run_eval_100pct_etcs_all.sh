#!/bin/bash
# 100% 动力学 + ETCS 训练模型 论文数据全量评估（聚焦 MARL vs MPC 叙事）
#
# 前置：outputs/run_full_training_100pct_etcs_5seed.sh 完成
# 协议：朔黄线主剖面 3000 步（--max_steps 3000，历史论文协议，勿用默认 35000）
# 输出：outputs/eval_100pct_etcs_all.log
set -u
cd "$(dirname "$0")/.."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl

CKPT=outputs/checkpoints_100pct_etcs
DQN=outputs/checkpoints_100pct/dqn
LOG=outputs/eval_100pct_etcs_all.log
: > "$LOG"
STEPS="--max_steps 3000"
M1="$CKPT/mappo_fleet_best_cp_seed0.pt"

echo "############ 1) 主对比（固定初态确定性，--etcs） ############" | tee -a "$LOG"
echo "=== M-MARL（ETCS训练 seed0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"
echo "=== No-C（M3 独立 δ=0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"
echo "=== M-MPC-fair（分层公平版）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py fairmpc - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"
echo "=== M-MPC（直接加速 mpc_dir）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mpc_dir - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"
echo "=== M-DQN-fair（100pct 重训 seed0）===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mdqn_fair - $STEPS --etcs --n_seed 1 --dqn_seed 0 --dqn_dir "$DQN" 2>&1 | tee -a "$LOG"
echo "=== Coast 惰行 ===" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py coast - $STEPS --etcs --n_seed 1 2>&1 | tee -a "$LOG"

echo "############ 2) 随机化初态统计（5 seed，55-75km/h，--etcs） ############" | tee -a "$LOG"
echo "--- M-MARL seed0 随机化 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 5 --randomize_init 2>&1 | tee -a "$LOG"
echo "--- No-C 随机化 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 5 --randomize_init 2>&1 | tee -a "$LOG"
echo "--- M-MPC-direct 随机化 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py mpc_dir - $STEPS --etcs --n_seed 5 --randomize_init 2>&1 | tee -a "$LOG"
echo "--- M-MPC-fair 随机化 ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py fairmpc - $STEPS --etcs --n_seed 5 --randomize_init 2>&1 | tee -a "$LOG"

echo "############ 3) 压力消融（gap 100→40，M-MARL vs No-C，--etcs） ############" | tee -a "$LOG"
for gap in 80 60 40; do
    echo "--- target_gap=$gap M-MARL ---" | tee -a "$LOG"
    python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 5 --randomize_init --target_gap "$gap" 2>&1 | tee -a "$LOG"
    echo "--- target_gap=$gap No-C ---" | tee -a "$LOG"
    python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 5 --randomize_init --target_gap "$gap" 2>&1 | tee -a "$LOG"
done

echo "############ 4) 安全层消融（--no_coupler，M-MARL，--etcs） ############" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 3 --randomize_init --no_coupler 2>&1 | tee -a "$LOG"

echo "############ 5) 第二剖面泛化（long_downhill_20km，--etcs） ############" | tee -a "$LOG"
echo "--- M-MARL 20km ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m1 "$M1" $STEPS --etcs --n_seed 5 --randomize_init --grade long_downhill_20km 2>&1 | tee -a "$LOG"
echo "--- No-C 20km ---" | tee -a "$LOG"
python src/evaluation/evaluate_m1_m3_long.py m3 - $STEPS --etcs --n_seed 5 --randomize_init --grade long_downhill_20km 2>&1 | tee -a "$LOG"

echo "############ ALL DONE ############" | tee -a "$LOG"
