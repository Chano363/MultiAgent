#!/usr/bin/env bash
# 【§19.49】第 11 投的**云端标定**前置动作：在**云端机**上重跑 ep1–ep7 官方快评，
# 并用**同一个**分析器重做"训练期 → 评估态主指标"相关性标定。
#
# 【为什么必须单独在云端做一次】（诊断 §19.49）
#   §19.47 的相关性/阈值/可分性**全部在本地口径上标定**；但实测跨机漂移带显示：
#   `band_rate` ±0.15%、`gap_min_m` ±0.02%（稳），而 `gap_err_mean_abs_m` 可差 **53.5%**、
#   `gap_err_peak_abs_m` 差 28.1% ⇒ **本地标定只能当先验，不能当云端判据**。
#   本脚本产出的**云端标定**才是第 11 投窗口内使用这些判据的依据。
#
# 【用法】（在云端实例内执行）
#   bash scripts/probes/run_cloud_recalibration.sh <train_results_dir> <eval_out_suffix> [ckpt_dir] [ep_list]
#
#   ⚠️ **ckpt_dir 必须显式给对**：第 11 投窗口有自己的 run_tag 与 ckpt 目录
#      ⇒ **不得沿用第 9 投的路径**，否则标定会拉错 ckpt（标定结果毫无意义）。
#      缺省值是第 9 投 W4 窗口的 ckpt 目录（仅用于回溯当前这条校准链）。
#   例：
#     bash scripts/probes/run_cloud_recalibration.sh \
#       outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud \
#       cloud_recal_20261121 "1 2 3 4 5 6 7"
#
# 【口径】
#   · **零新增训练**：只跑评估态整程确定性快评（复用既有 ckpt）；
#   · 每集 31500 步、decision_interval=10、eval_seed=0、init_speed_kmh=60、
#     与云端 W4 窗口快评**完全同参**（保证可与训练窗口产物并列）；
#   · ⚠️ **本脚本不产出峰值/安全判据**，只产出**标定产物**（相关性/可分性）；
#   · ⚠️ **不得把云端标定结果与本地标定结果混引**（跨机不可互引，§19.42 / §19.49）。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

TRAIN_RESULTS_DIR="${1:?用法: run_cloud_recalibration.sh <train_results_dir> <eval_out_suffix> [ckpt_dir] [ep_list]}"
OUT_SUFFIX="${2:?缺 eval_out_suffix}"
CKPT_DIR="${3:-outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud}"
EP_LIST="${4:-1 2 3 4 5 6 7}"

if [ ! -d "${CKPT_DIR}" ]; then
  echo "[recal] ABORT: ckpt dir 不存在：${CKPT_DIR}"
  echo "[recal] ⚠️ 第 11 投窗口必须传入**本投自己的** ckpt 目录，勿沿用第 9 投路径。"
  exit 2
fi
LOGDIR=outputs/logs/adr083_cloud_recal_${OUT_SUFFIX}
mkdir -p "${LOGDIR}"

echo "[recal] train_results_dir=${TRAIN_RESULTS_DIR}"
echo "[recal] out_suffix=${OUT_SUFFIX}  episodes=${EP_LIST}"
echo "[recal] ckpt_dir=${CKPT_DIR}"
echo "[recal] logdir=${LOGDIR}"

# ---- 第一步：云端机重跑 ep1..ep7 官方口径整程确定性快评 ----
MAXJOBS=3
pids=()
for EP in ${EP_LIST}; do
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
    --out_suffix "_${OUT_SUFFIX}_det_ep${EP}" \
    > "${LOGDIR}/ep${EP}.log" 2>&1 &
  pids+=($!)
  echo "launched ep${EP} pid=${pids[-1]}"
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "[recal] QUICK_EVAL_DONE fail=${fail} $(date -Is)"

# ---- 第二步：云端环境指纹（规则第 9 条：开窗必须采集指纹并逐项比对）----
python scripts/probes/collect_env_fingerprint.py --label cloud \
  > "${LOGDIR}/fingerprint.log" 2>&1
echo "[recal] fingerprint rc=$?"

# ---- 第三步：用同一分析器在云端标定数据上重做相关性标定 ----
python scripts/probes/analyze_primary_metric_correlation.py \
  --label cloud \
  --train-dir "${TRAIN_RESULTS_DIR}" \
  --eval-glob "outputs/results/decompose/eval_decompose_*_${OUT_SUFFIX}_det_ep{}.json" \
  --out "outputs/logs/adr083_primary_metric_corr/primary_metric_corr_cloud.json" \
  > "${LOGDIR}/recalibration.log" 2>&1
echo "[recal] recalibration rc=$?"

# ---- 第四步：与本地标定做配对漂移带比较（§19.49 工具）----
python scripts/probes/analyze_cross_machine_band.py \
  --out "outputs/logs/adr083_primary_metric_corr/cross_machine_band_recal.json" \
  > "${LOGDIR}/cross_machine_band.log" 2>&1
echo "[recal] cross_machine_band rc=$?"

echo "[recal] ALL_DONE $(date -Is)"
echo "[recal] 产物："
echo "[recal]   outputs/logs/adr083_primary_metric_corr/primary_metric_corr_cloud.json"
echo "[recal]   outputs/logs/adr083_primary_metric_corr/cross_machine_band_recal.json"
echo "[recal] ⚠️ 本地标定与云端标定**不得混引**；窗口内判据一律以云端标定为准。"
