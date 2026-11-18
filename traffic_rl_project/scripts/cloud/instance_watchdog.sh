#!/usr/bin/env bash
# 实例侧看护：只做"防止实例开着空转计费"这一件事。
#
# 三种结局（对应 AGENTS.md「云实例纪律」第 3 条）：
#   A) 心跳超时（进程在但 heartbeat.txt 不更新）→ 杀训练 + 写 DEAD 标记 + 关机
#   B) 训练进程消失但已有 exit_code.txt（正常/异常退出）→ 等本地回传标记（有界）→ 关机
#   C) 训练进程消失且无 exit_code.txt（被外部杀）→ 写 DEAD 标记 + 关机
#
# 关机两级（2026-11-18 服务器端 closer 增强，一手依据见 docs/CLOSER_SERVER_SIDE_ASSESSMENT.md）：
#   第一道 = 实例内 API 自停机 self_stop_ecs.sh（RAM 角色免 AK，StopInstance --StoppedMode
#            StopCharging）→ 实例自己完成"停费"，不依赖本地 Windows 在线。
#   第二道 = OS 层 poweroff（自停机脚本缺失/失败时回退；按量实例 OS 关机不保证等于节省停机，
#            此时仍需本地看护补 API 停机）。
# 三种结局判据（心跳超时/进程退出/无退出码）完全不变——只换执行方式，不引入新误杀面。
set -uo pipefail

RESULTS=""; PID=""; STALE_S=1800; GRACE_S=900; LEDGER=/dev/null
SELF_STOP="${SELF_STOP_SCRIPT:-/root/traffic_rl_project/scripts/cloud/self_stop_ecs.sh}"
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
  local reason="${1:-watchdog}"
  log "shutdown_requested reason=$reason"
  sync
  # 第一道：实例内 API 自停机（RAM 角色免 AK，StopInstance --StoppedMode StopCharging）。
  # 成功 = 已确认 Stopped+StopCharging = 已停费，无需 OS poweroff，也不必等本地。
  if [ -f "$SELF_STOP" ] && bash "$SELF_STOP" "$reason" >>"$LEDGER" 2>&1; then
    log "self_stop_verified reason=$reason：实例已 API 停机并复核 StopCharging"
    return 0
  fi
  # 第二道：自停机脚本缺失/失败（RAM 角色未绑/CLI 未装等）→ OS poweroff 止血，
  # 本地看护再补 API 停机。此回退路径与改动前行为一致。
  log "self_stop_unavailable reason=$reason → OS poweroff 回退（需本地补 API 停机）"
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
      poweroff_now "DEAD_HEARTBEAT"
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
      poweroff_now "train_exit_rc_${RC}"
    else
      log "DEAD_NO_EXIT_CODE"
      echo "DEAD_NO_EXIT_CODE at $(date -Is)" \
        > "$RESULTS/DEAD_$(date +%Y%m%d_%H%M%S).txt"
      poweroff_now "DEAD_NO_EXIT_CODE"
    fi
    exit 0
  fi
  sleep 60
done
