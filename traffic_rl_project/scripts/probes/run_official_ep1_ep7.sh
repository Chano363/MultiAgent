#!/usr/bin/env bash
# 第 11 投前置取证的**权威口径**批次：用官方评估入口跑 ep1/ep2/ep3/ep5/ep7 快评。
#
# 【为什么必须重跑官方口径】
# §19.40 上一批用 probe_percol_ab_threshold.py 的 base 变体取 ep1..ep7 轨迹，
# 但那个探针的**绝对值与官方快评不可比**（ep6 上探针 peak 1478.9 vs 官方快评
# 1256.72，差 17.7%；ep2/ep4 上只差 0.5%/3.2%）⇒ 差值随"漂移程度"放大。
# 原因是探针走的是自建 env 构造路径（make_yaml + 自造 args），与官方入口
# `evaluate_decompose.py` 的工况固化（起点口径 / decision_interval / ckpt metadata
# 解析 / official 守卫）不是同一条。
# ⇒ **漂移轨迹必须用官方入口重取**，否则趋势结论的数值不可引用。
#
# 【参数与云端 W4 快评逐项对齐】（取自云端 eval json 的 metadata.eval_args）
#   mode=decompose_m1  experiment=formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml
#   max_steps=31500  num_trains=3  n_seed=1  eval_seed=0
#   init_speed_kmh=60.0  decision_interval=10  mask_lever=none
#   out_suffix=<run_tag>_det_ep<N>
#
# 【ep2 是校验集】：云端 ep2 官方快评 peak=1179.23 / band=0.9089。
# 本地重跑必须复现该数（逐位或可解释微小差异）⇒ 否则本批数据不可用。
#
# 【口径】零机时整程 OOD 对照 ⇒ 只作方向筛选，不作峰值/安全判据、不作论文口径。
# 绝对值仅在**同一入口同一参数**下跨集纵向比较。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

TAG=adr083_official_ep1_ep7_20261121
CKPT_DIR=outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud
LOGDIR=outputs/logs/${TAG}
mkdir -p "${LOGDIR}"
MAXJOBS=3

pids=()
for EP in ${EP_LIST:-1 2 3 5 7}; do
  CK="${CKPT_DIR}/mappo_fleet_last_ep${EP}_dec_ad1_cp_seed0_seed0.pt"
  if [ ! -f "${CK}" ]; then
    echo "SKIP ep${EP}: ckpt missing ${CK}"
    continue
  fi
  while [ "$(jobs -rp | wc -l)" -ge "${MAXJOBS}" ]; do sleep 5; done
  python src/evaluation/evaluate_decompose.py \
    --mode decompose_m1 \
    --checkpoint "${CK}" \
    --experiment configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml \
    --max_steps 31500 --num_trains 3 --n_seed 1 --eval_seed 0 \
    --init_speed_kmh 60.0 --decision_interval 10 --mask_lever none \
    --out_suffix "_${TAG}_det_ep${EP}" \
    > "${LOGDIR}/ep${EP}.log" 2>&1 &
  pids+=($!)
  echo "launched ep${EP} pid=${pids[-1]}"
done

fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "ALL_OFFICIAL_DONE fail=${fail} $(date -Is)"
