#!/usr/bin/env bash
# 实例侧看护：只做"防止实例开着空转计费"这一件事。
#
# 三种结局（对应 AGENTS.md「云实例纪律」第 3 条）：
#   A) 心跳超时（进程在但 heartbeat.txt 不更新）→ 杀训练 + 写 DEAD 标记 + 关机
#   B) 训练进程消失但已有 exit_code.txt（正常/异常退出）→ 等本地回传标记（有界）→ 关机
#   C) 训练进程消失且无 exit_code.txt（被外部杀）→ 写 DEAD 标记 + 关机
#
# 关机 = OS 层 poweroff（第一道）。**API 层 stop + StopCharging 二次复核由本地看护负责**，
# 因为按量付费实例的系统内关机状态不保证等于"节省停机"。
set -uo pipefail

RESULTS=""; PID=""; STALE_S=1800; GRACE_S=900; LEDGER=/dev/null
while [ $# -gt 0 ]; do
  case "$1" in
    --results-dir) RESULTS="$2"; shift 2;;
    --train-pid) PID="$2"; shift 2;;
    --stale-s) STALE_S="$2"; shift 2;;
    --grace-s) GRACE_S="$2"; shift 2;;
    --ledger) LEDGER="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 2;;
  esac
done
[ -n "$RESULTS" ] && [ -n "$PID" ] || { echo "缺 --results-dir/--train-pid"; exit 2; }

HB="$RESULTS/heartbeat.txt"
log() { echo "$(date -Is) $*" | tee -a "$LEDGER"; }
poweroff_now() {
  log "poweroff_requested"
  sync
  poweroff -f 2>/dev/null || shutdown -h now 2>/dev/null || log "poweroff 命令不可用，需本地看护 API 停机"
}

log "watchdog_start pid=$PID stale=${STALE_S}s grace=${GRACE_S}s"

while true; do
  # A) 心跳超时
  if [ -f "$HB" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$HB") ))
    if [ "$AGE" -gt "$STALE_S" ]; then
      log "DEAD_HEARTBEAT age=${AGE}s"
      echo "DEAD_HEARTBEAT age=${AGE}s at $(date -Is)" \
        > "$RESULTS/DEAD_$(date +%Y%m%d_%H%M%S).txt"
      kill -TERM "$PID" 2>/dev/null
      sleep 20
      kill -KILL "$PID" 2>/dev/null
      poweroff_now
      exit 0
    fi
  fi

  # B/C) 进程消失
  if ! kill -0 "$PID" 2>/dev/null; then
    if [ -f "$RESULTS/exit_code.txt" ]; then
      RC=$(tr -d '\r\n' < "$RESULTS/exit_code.txt")
      log "train_exit rc=$RC：等本地回传（上限 ${GRACE_S}s）"
      WAITED=0
      while [ "$WAITED" -lt "$GRACE_S" ]; do
        [ -f "$RESULTS/.pull_done" ] && { log "pull_done 已到，立即关机"; break; }
        sleep 30; WAITED=$((WAITED + 30))
      done
      [ -f "$RESULTS/.pull_done" ] || log "PULL_GRACE_TIMEOUT ${GRACE_S}s：产物仍在实例磁盘上，先关机止血"
      poweroff_now
    else
      log "DEAD_NO_EXIT_CODE"
      echo "DEAD_NO_EXIT_CODE at $(date -Is)" \
        > "$RESULTS/DEAD_$(date +%Y%m%d_%H%M%S).txt"
      poweroff_now
    fi
    exit 0
  fi
  sleep 60
done
