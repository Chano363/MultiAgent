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

# 1b) 上传同源校验（诊断 §19.34-C/D，2026-11-20）
#   - .git_commit：由 scripts/cloud/prepare_upload.sh 按本地 HEAD 生成，是"这次
#     实际上云的代码"的权威锚（云端 .git 是部署残留，git rev-parse HEAD 会失真）。
#   - MANIFEST/ref：参考速度表 md5 必须与本地一致，否则训练/评估用的参考速度
#     表不是同一份 ⇒ 口径不同源（该表在 outputs/ 下，rsync 会排除，必须单独传）。
#   校验失败只告警不阻断（训练窗口已获批，硬阻断会造成空转），但会写进 ledger。
UPLOAD_NOTE=""
if [ -f "$ROOT/.git_commit" ]; then
  UPLOAD_NOTE="git_commit=$(cat "$ROOT/.git_commit")"
else
  UPLOAD_NOTE="git_commit=MISSING(provenance失真风险)"
fi
if [ -f "$ROOT/.upload_payload/MANIFEST.txt" ]; then
  LOCAL_MD5="$(grep -F 'ref_speed_table.npz' "$ROOT/.upload_payload/MANIFEST.txt" 2>/dev/null | awk '{print $1}')"
  CLOUD_REF="$(python -c 'import sys,yaml;cfg=yaml.safe_load(open(sys.argv[1],encoding="utf-8")) or {};print(((cfg.get("env_cfg") or {}).get("speed_ref_table") or ""))' "$CONFIG" 2>/dev/null | head -1 | tr -d "\r")"
  if [ -n "$CLOUD_REF" ] && [ -f "$CLOUD_REF" ]; then
    CLOUD_MD5="$(md5sum "$CLOUD_REF" | awk '{print $1}')"
    if [ -n "$LOCAL_MD5" ] && [ "$LOCAL_MD5" != "$CLOUD_MD5" ]; then
      UPLOAD_NOTE="$UPLOAD_NOTE; ref_table_md5_MISMATCH local=$LOCAL_MD5 cloud=$CLOUD_MD5"
    else
      UPLOAD_NOTE="$UPLOAD_NOTE; ref_table_md5=OK"
    fi
  else
    UPLOAD_NOTE="$UPLOAD_NOTE; ref_table_CLOUD_MISSING($CLOUD_REF)"
  fi
else
  UPLOAD_NOTE="$UPLOAD_NOTE; upload_manifest=MISSING"
fi
echo "upload_provenance: $UPLOAD_NOTE" | tee -a "$LEDGER"

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

# 3b) 【COVER 投】快评看护（G1 第 4 问）：每 10 集确定性快评、破线即杀。
# 仅当 COVER_QUICK_EVAL=1 时启动；默认关 = 非 COVER 训练零回归。
QPID=""
if [ "${COVER_QUICK_EVAL:-0}" = "1" ]; then
  RUN_ID="$RUN_ID" ROOT="$ROOT" EVERY="${COVER_EVAL_EVERY:-10}" \
  EVAL_STEPS="${COVER_EVAL_STEPS:-31500}" \
  EVAL_CFG="${COVER_EVAL_CFG:-configs/experiments/formation_ed_ab_3train_1plus108_cover.yaml}" \
  nohup bash scripts/cloud/cover_quick_eval_watch.sh \
    > "$LOG_DIR/quick_eval_$RUN_ID.log" 2>&1 &
  QPID=$!
  echo "quick_eval_pid=$QPID" | tee -a "$LEDGER"
fi

wait "$PID"; RC=$?
# 通知快评看护：训练已结束，停止轮询（收尾交给 watchdog）
touch "$RES/train_finished.marker" 2>/dev/null
echo "$RC" > "$RES/exit_code.txt"
echo "train_rc=$RC end_at=$(date -Is) end_epoch=$(date +%s)" | tee -a "$LEDGER"

# 4) 收尾交给看护（等本地 .pull_done 后关机）；这里只兜底等它 5 min
for _ in $(seq 1 10); do
  kill -0 "$WPID" 2>/dev/null || break
  sleep 30
done
exit "$RC"
