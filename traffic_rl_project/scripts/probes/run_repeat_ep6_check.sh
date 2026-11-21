#!/usr/bin/env bash
# 【判决性对照 B】用**当前代码**在本地复跑 ep6，与本轮已得的 1478.85 比对。
# 目的：判定"本地 vs 云端 17.7% 差异"是否属机器/浮点层面的不可复现：
#   - 若复跑逐位一致（1478.9）⇒ 本地可复现，差异是本地 vs 云端的机器差异；
#   - 若复跑也不一致 ⇒ 本地本身不可复现，整程快评读数的稳定性需重新评估。
#
# 背景（诊断 §19.40）：
#   云端官方 ep6 = 1256.72（峰值列 = 尾列），本地官方 ep6 = 1478.85（峰值列 = 中列）。
#   已证云端代码与当前代码同源（配置 nincrgatecaprel.yaml 于 11-20 15:13 才存在，
#   云端用它 ⇒ 云端代码必然含 ADR-076/077/080/081；metadata.git_commit=154c1b8 是标签失真）。
#   ⇒ 剩余唯一解释是机器/浮点差异。本脚本量化它。
#
# 口径：零机时、同 ckpt、同参数；只作归因，不作峰值/安全判据。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
LOGDIR=outputs/logs/adr083_repeat_ep6
mkdir -p "${LOGDIR}"
python src/evaluation/evaluate_decompose.py \
  --mode decompose_m1 \
  --checkpoint outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt \
  --experiment configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml \
  --max_steps 31500 --num_trains 3 --n_seed 1 --eval_seed 0 \
  --init_speed_kmh 60.0 --decision_interval 10 --mask_lever none \
  --out_suffix "_adr083_repeat_ep6_det_ep6" \
  > "${LOGDIR}/ep6_repeat.log" 2>&1
echo "REPEAT_EP6_DONE rc=$? $(date -Is)"
