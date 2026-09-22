#!/bin/bash
# 泛化：用 tmux 持久会话拉起/重启 formation seed{N} 训练（ADR-013 唯一 RL）
# 用法: bash _launch_tmux_seed.sh {N}
REPO=/mnt/d/Code/MultiAgent/traffic_rl_project
OUT=$REPO/outputs/checkpoints_formation
EXP=configs/experiments/formation_ed_ab_3train_1plus1.yaml
CURR=1000:0,2000:20,3000:30,5000:40,8000:60,12000:75,15000:90
S="${1:?need seed N}"
tmux has-session -t train$S 2>/dev/null && tmux kill-session -t train$S
tmux new-session -d -s train$S "cd $REPO && source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl && exec python run_training.py --experiment $EXP --seed $S --episodes 120 --checkpoint_dir outputs/checkpoints_formation/seed$S --results_dir outputs/checkpoints_formation/seed$S/results --override dirs.figures_dir=outputs/checkpoints_formation/seed$S/figures --override curriculum=$CURR --override env_cfg.max_steps=15000 > outputs/checkpoints_formation/seed${S}_train.log 2>&1"
echo "tmux train$S launched"