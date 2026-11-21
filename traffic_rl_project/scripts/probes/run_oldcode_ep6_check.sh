#!/usr/bin/env bash
# 【判决性对照】用云端快评当时的代码版本（154c1b8）在本地跑 ep6，
# 与云端官方读数 peak=1256.72 比对，判决"本地 vs 云端 17.7% 差异"的来源：
#   若本地旧代码 ≈ 1256.72 ⇒ 差异来自**代码版本**（评估读的标签是真的旧代码）；
#   若本地旧代码 ≈ 1478.9  ⇒ 差异来自**机器/浮点**（云端跑的其实是新代码，metadata 标签失真）。
#
# 背景：§19.40 发现本地当前代码 ep6 = 1478.85，云端 ep6 = 1256.72，峰值列也不同。
# 云端 metadata.git_commit = 154c1b8（该 sha 不含 ADR-076/077/080/081 四个提交），
# 但 prepare_upload.sh 的注释称"实际运行的是 dcbe214 工作区代码"⇒ 必须实测判决。
#
# 口径：零机时、同 ckpt、同参数（与云端 eval_args 逐项对齐）；只作归因，不作峰值判据。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl

OLD=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/tmp_old154/traffic_rl_project
NEW=/mnt/d/Code/MultiAgent/traffic_rl_project
CKPT=${NEW}/outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt
LOGDIR=${NEW}/outputs/logs/adr083_oldcode_ep6
mkdir -p "${LOGDIR}"

cd "${OLD}"
python src/evaluation/evaluate_decompose.py \
  --mode decompose_m1 \
  --checkpoint "${CKPT}" \
  --experiment configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml \
  --max_steps 31500 --num_trains 3 --n_seed 1 --eval_seed 0 \
  --init_speed_kmh 60.0 --decision_interval 10 --mask_lever none \
  --out_suffix "_adr083_oldcode154c1b8_det_ep6" \
  > "${LOGDIR}/ep6_oldcode.log" 2>&1
echo "OLDCODE_EP6_DONE rc=$? $(date -Is)"
