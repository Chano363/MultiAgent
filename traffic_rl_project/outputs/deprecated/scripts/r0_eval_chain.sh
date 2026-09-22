#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/evaluation/evaluate_m1_m3_long.py mpc_rule --etcs --num_trains 3 --max_steps 300 --grade shuozhou_23800 --n_seed 1 > outputs/logs_r0/eval_mpc_rule_300.log 2>&1
python -m pytest tests/ -q > outputs/logs_r0/pytest_final.log 2>&1
python src/evaluation/plot_physical_curves.py > outputs/logs_r0/plot_phys.log 2>&1
python src/evaluation/plot_profile_validation.py > outputs/logs_r0/plot_profile.log 2>&1
echo done > outputs/logs_r0/chain_done.flag
