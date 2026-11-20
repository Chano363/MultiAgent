#!/usr/bin/env bash
# 第 11 投方向候选的可行性取证：ep1..ep7 逐集"动作面漂移"轨迹（零机时、零费用）。
#
# 【为什么跑这个】
#   ADR-082 判定"逐列 AB 派生阈值"机制不进第 11 投配置，方向候选改为
#   「在训练中检测到 ep6 式动作面漂移时及时止损 / 回退到 ep4 形态」。
#   但该候选要落地，必须先回答一个前置问题：**漂移是突变还是渐变？**
#   现有证据只有 ep2 / ep4 / ep6 三个点（§19.33）：
#     ep2 (PASS)  中列 AB 使用率 0.159、中列 ED≤0 率 0.084、peak 1179.2
#     ep4 (PASS)  中列 AB 使用率 0.212、中列 ED≤0 率 0.057、peak 1132.4
#     ep6 (BREAK) 中列 AB 使用率 0.377、中列 ED≤0 率 0.321、peak 1256.7
#   三点无法区分两种形态：
#     (a) 突变型 —— ep5 正常、ep6 突然漂移 ⇒ 在线检测器只能"事后止损"，
#                  无法提前一集预警；
#     (b) 渐变型 —— ep3/ep4/ep5 已单向漂移、ep6 只是越过阈值 ⇒ 在线检测器
#                  可以在 ep5 就触发，回退成本低得多。
#   这个问题的答案直接决定第 11 投该不该做、以及止损策略该怎么设计，
#   因此属于**方向候选的前置取证**，零机时本地跑，不涉及云实例。
#
# 【口径纪律】
#   全部是**零机时整程 OOD 对照**（既有 ckpt + 确定性快评，31500 步）⇒ 只作方向筛选，
#   **不作峰值/安全判据、不作论文口径**；绝对阈值不可跨环境引用。
#   逐集指标一律**同环境内纵向比较**（ep1→ep7 同一条训练轨迹、同一探针口径）。
#   ⚠️ **本探针的绝对数值与 §19.33 的 W4 云端快评数值不可互相替代**
#   （ADR-070 第 6 次：训练 rollout 对确定性评估盲；例如本探针 base 的 peak
#   高于云端快评的 1256.72）。本脚本**只用纵向趋势**（同一探针同一口径下
#   ep1→ep7 的逐集变化），不用绝对值跨源比较。
#
# 【并发】
#   31500 步 × 7 集，CPU 密集 ⇒ 并发上限 3，避免抢满机器拖长总时长。
#
# 【运行方式】
#   WSL 内 bash；**经 Windows schtasks 启动**（红线 2：>5 min 长跑不得在
#   IDE 终端启动，客户端关闭会连带杀掉 WSL 子进程）。
#   判活看产物目录而非日志末行（红线 2）。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

TAG=adr083_drift_trajectory_20261121
CKPT_DIR=outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud
LOGDIR=outputs/logs/${TAG}
mkdir -p "${LOGDIR}"

pids=()
MAXJOBS=3
for EP in 1 2 3 4 5 6 7; do
  CK="${CKPT_DIR}/mappo_fleet_last_ep${EP}_dec_ad1_cp_seed0_seed0.pt"
  if [ ! -f "${CK}" ]; then
    echo "SKIP ep${EP}: ckpt missing ${CK}"
    continue
  fi
  while [ "$(jobs -rp | wc -l)" -ge "${MAXJOBS}" ]; do sleep 5; done
  LG10_CKPT="${CK}" LG10_TAG="${TAG}_ep${EP}" LG10_ONLY=base \
    python scripts/probes/probe_percol_ab_threshold.py \
    > "${LOGDIR}/ep${EP}.log" 2>&1 &
  pids+=($!)
  echo "launched ep${EP} pid=${pids[-1]} ckpt=${CK}"
done

fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
echo "ALL_EPISODES_DONE fail=${fail} $(date -Is)"
