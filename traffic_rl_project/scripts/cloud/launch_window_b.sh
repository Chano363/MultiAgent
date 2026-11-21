#!/usr/bin/env bash
# 第 11 投 **窗口 B（对照侧）** 的上传 + 启动脚本（WSL 本地执行）。
#
# ⚠️ **前置条件（必须先满足，否则不得执行）**：
#   ① 窗口 A 已收账（产物回传校验通过 + 实例已停机，Status=Stopped/StopCharging 有回执）；
#   ② 窗口 B 的 closer 双活 + billing_guard **已注册**（PowerShell 注册，见 ADR-084 票据 §3 步骤 2）
#      —— 因为注册需要实例 IP/IP 必须在开机之后拿到，而训练启动必须在 closer 之后
#      ⇒ **顺序 = 开机 → 注册 closer → 本脚本**；
#   ③ 配置已存在且三目录同换 `w5colgap_abphys_ctrl_20261121`。
#
# 用法：
#   bash scripts/cloud/launch_window_b.sh [IP] [RUN_ID] [CONFIG] [EPISODES]
#
# 本脚本做什么（与窗口 A 完全同参，只换配置）：
#   1) rsync 上传本投配置（**不含 outputs/**，避免覆写历史产物）；
#   2) 核对远端 .preflight_ok 与 .git_commit（上传同源校验）；
#   3) 远端拉起 instance_bootstrap.sh：训练 + watchdog + 逐 2 集确定性快评看护
#      （EVAL_CFG 锁本投配置、GAP_MAX_ABS_M/GAP_RISE_TOL = 列距护栏）；
#   4) 打印关键 pid 与日志路径（供 §0.8.2 第 4/5 问的运行时留痕）。
set -uo pipefail

IP="${1:-47.120.11.1}"
RUN_ID="${2:-w5colgap_abphys_ctrl_20261121}"
CONFIG="${3:-configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap_ctrl.yaml}"
EPISODES="${4:-8}"
ROOT=/mnt/d/Code/MultiAgent/traffic_rl_project
KEY="$HOME/.ssh/cloud_traffic"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 root@$IP"

cd "$ROOT" || exit 1
echo "[winB] ip=$IP run_id=$RUN_ID episodes=$EPISODES"
echo "[winB] config=$CONFIG"

echo "[winB] 1/3 上传配置"
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15" \
  "$CONFIG" "root@$IP:/root/traffic_rl_project/configs/experiments/" || exit 2

echo "[winB] 2/3 核对远端预检标记与代码锚"
$SSH "cd /root/traffic_rl_project && \
  echo \"  preflight_ok=\$( [ -f .preflight_ok ] && echo yes || echo NO )\" && \
  echo \"  git_commit=\$(cat .git_commit 2>/dev/null || echo MISSING)\" && \
  grep -n 'results_dir\\|checkpoint_dir' $CONFIG | sed 's/^/  /'"

echo "[winB] 3/3 拉起训练（bootstrap：train + watchdog + 快评看护）"
$SSH "cd /root/traffic_rl_project && mkdir -p outputs/logs/cloud && \
  RUN_ID=$RUN_ID CONFIG=$CONFIG EPISODES=$EPISODES SEED=0 \
  COVER_QUICK_EVAL=1 COVER_EVAL_EVERY=2 COVER_EVAL_STEPS=31500 \
  COVER_EVAL_CFG=$CONFIG \
  GAP_MAX_ABS_M=1300 GAP_RISE_TOL=0.30 \
  nohup bash scripts/cloud/instance_bootstrap.sh > outputs/logs/cloud/boot_${RUN_ID}.log 2>&1 & \
  sleep 20; \
  echo '  === BOOT LOG ==='; cat outputs/logs/cloud/boot_${RUN_ID}.log; \
  echo '  === PROCS ==='; pgrep -af 'run_training.py|cover_quick_eval_watch|instance_watchdog' | cut -c1-110"

echo "[winB] 提示：若需确认快评看护的评估配置与列距护栏阈值，用"
echo "[winB]   ssh -i \$HOME/.ssh/cloud_traffic root@$IP \"tr '\\0' '\\n' < /proc/<quick_eval_pid>/environ | grep -E '^(EVERY|EVAL_STEPS|EVAL_CFG|GAP_)'\""
echo "[winB] 收账由窗口 B 的 closer 自动完成（回传校验 → API 停机复核）；旧 billing_guard 的绝对 deadline 之后需重新注册。"
