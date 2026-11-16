#!/usr/bin/env bash
# 实例侧一键启动：**第一条命令即训练**，不做环境安装/调试。
#
# 前置（本地已完成）：preflight_payload.sh 全 PASS → 生成 .preflight_ok 并随代码 rsync 上云。
# 退出码约定：
#   0    训练正常结束（run.log 有「训练完成」）
#   1..N run_training.py 的非 0 返回码（原样写进 results/exit_code.txt）
#   90   缺 .preflight_ok（说明预检没过就开了机 —— 直接退出，不跑）
#   91   conda 环境激活失败
#
# 环境变量（都有默认值）：
#   RUN_ID / EPISODES / SEED / RESUME / CONFIG / ROOT / STALE_S / GRACE_S
set -uo pipefail

ROOT=${ROOT:-/root/traffic_rl_project}
CONFIG=${CONFIG:-configs/experiments/formation_ed_ab_3train_1plus108.yaml}
EPISODES=${EPISODES:-60}
SEED=${SEED:-0}
RESUME=${RESUME:-}
RUN_ID=${RUN_ID:-cloud_$(date +%Y%m%d_%H%M%S)}
STALE_S=${STALE_S:-1800}     # 心跳龄 > 30 min 视为卡死
GRACE_S=${GRACE_S:-900}      # 训练结束后等本地回传的上限（不会无限空等）

BASE="$ROOT/outputs"
CKPT="$BASE/checkpoints/formation_10kt_1plus108/$RUN_ID"
RES="$BASE/results/formation_10kt_1plus108/$RUN_ID"
FIG="$BASE/figures/formation_10kt_1plus108/$RUN_ID"
LOG_DIR="$BASE/logs/cloud"
LOG="$LOG_DIR/$RUN_ID.log"
LEDGER="$LOG_DIR/lifecycle_$RUN_ID.txt"

mkdir -p "$CKPT" "$RES" "$FIG" "$LOG_DIR"

# 0) 换机复核：预检标记必须在
if [ ! -f "$ROOT/.preflight_ok" ]; then
  echo "NO_PREFLIGHT_MARK：本地预检未通过就开机，拒绝启动（不消耗机时）" | tee -a "$LEDGER"
  exit 90
fi

# 1) 环境只激活、不安装（镜像已预装）
source /root/miniconda3/etc/profile.d/conda.sh || { echo "conda 初始化失败"; exit 91; }
conda activate traffic_rl || { echo "conda traffic_rl 激活失败"; exit 91; }
cd "$ROOT" || exit 91

echo "boot_at=$(date -Is) boot_epoch=$(date +%s) run_id=$RUN_ID" | tee -a "$LEDGER"

ARGS=(--experiment "$CONFIG" --seed "$SEED" --episodes "$EPISODES"
      --override device=cpu --override n_env_parallel=true
      --checkpoint_dir "$CKPT" --results_dir "$RES"
      --override "dirs.figures_dir=$FIG")
[ -n "$RESUME" ] && ARGS+=(--resume "$RESUME")

# 2) 立刻开训（后台 + 前台 wait，保证拿到真实退出码）
nohup python run_training.py "${ARGS[@]}" > "$LOG" 2>&1 &
PID=$!
echo "train_pid=$PID log=$LOG" | tee -a "$LEDGER"

# 3) 看护：心跳超时 / 进程消失（无 exit_code）→ 写 DEAD 标记并关机
nohup bash scripts/cloud/instance_watchdog.sh \
  --results-dir "$RES" --train-pid "$PID" \
  --stale-s "$STALE_S" --grace-s "$GRACE_S" --ledger "$LEDGER" \
  > "$LOG_DIR/watchdog_$RUN_ID.log" 2>&1 &
WPID=$!
echo "watchdog_pid=$WPID" | tee -a "$LEDGER"

wait "$PID"; RC=$?
echo "$RC" > "$RES/exit_code.txt"
echo "train_rc=$RC end_at=$(date -Is) end_epoch=$(date +%s)" | tee -a "$LEDGER"

# 4) 收尾交给看护（等本地 .pull_done 后关机）；这里只兜底等它 5 min
for _ in $(seq 1 10); do
  kill -0 "$WPID" 2>/dev/null || break
  sleep 30
done
exit "$RC"
