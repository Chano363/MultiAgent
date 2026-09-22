#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# formation 多 seed 串行训练 supervisor（ADR-013 唯一 RL，3列×1+1=6 agents）
# 职责：seed0→seed1→seed2→seed3→seed4 逐个接力（每个 seed 独立 tmux 会话 train{seed}，
#       tmux 保证进程在 wsl 会话退出后存活）；每 30min 巡检快照写 patrol.log；
#       发散检测（Ep reward<-20万 或 (coupler>1300 且 viol>200)）→ 杀进程 + PAUSE；
#       异常退出（无完成标记）→ PAUSE 等待处置。
# 启动：tmux new-session -d -s train_sup 'bash _supervise_formation.sh'
# 恢复：修复后重跑本命令即可（幂等：已完成/运行中的 seed 自动跳过）。
# 依赖：tmux（已确认可用）；路径均为 WSL /mnt/d/...。
# ═══════════════════════════════════════════════════════════════════════════
REPO=/mnt/d/Code/MultiAgent/traffic_rl_project
OUT=$REPO/outputs/checkpoints_formation
PATROL=$OUT/patrol.log
EXP=configs/experiments/formation_ed_ab_3train_1plus1.yaml
CURR=1000:0,2000:20,3000:30,5000:40,8000:60,12000:75,15000:90
STEP_MAX=15000

log() { echo "[$(date '+%F %T')] $*" >> "$PATROL"; }

snapshot() {
  {
    echo "=== PATROL $(date '+%F %T') ==="
    echo "  active_seed=$(pgrep -af run_training | grep -oE -- '--seed [0-9]' | head -1 | awk '{print $2}')"
    for s in 0 1 2 3 4; do
      LOG=$OUT/seed${s}_train.log
      LAST=""
      [ -f "$LOG" ] && LAST=$(grep '^Ep ' "$LOG" | tail -1)
      if tmux has-session -t train$s 2>/dev/null; then ST=alive; else ST=done; fi
      echo "  seed${s}: ${LAST:-no-ep-yet} | tmux=$ST"
    done
  } >> "$PATROL"
}

# 从一行 Ep 日志解析 r/c/v，返回空格分隔
parse_ep() { echo "$1" | awk '
  /^Ep / {
    r=""; c=""; v=""
    if (match($0, /Reward -?[0-9.]+/)) r=substr($0, RSTART+7, RLENGTH-7)+0
    if (match($0, /peakCoupler [0-9.]+/)) c=substr($0, RSTART+12, RLENGTH-12)+0
    if (match($0, /viol [0-9.]+/)) v=substr($0, RSTART+5, RLENGTH-5)+0
    print r, c, v
  }' ; }

done_check() { # $1=seed
  local s=$1 LOG=$OUT/seed${s}_train.log
  [ -f "$LOG" ] || return 1
  grep -q "训练完成" "$LOG" && return 0
  tail -80 "$LOG" | grep -qE "Ep 120/120" && return 0
  return 1
}

launch_seed() { # $1=seed ; 创建独立 tmux 会话 train$s
  local s=$1
  tmux new-session -d -s train$s "cd $REPO && source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl && exec python run_training.py --experiment $EXP --seed $s --episodes 120 --checkpoint_dir outputs/checkpoints_formation/seed$s --results_dir outputs/checkpoints_formation/seed$s/results --override dirs.figures_dir=outputs/checkpoints_formation/seed$s/figures --override curriculum=$CURR --override env_cfg.max_steps=$STEP_MAX > outputs/checkpoints_formation/seed${s}_train.log 2>&1"
  log "launch seed $s -> tmux train$s"
}

wait_seed() { # $1=seed ; 每5min轮询；每30min快照；发散→kill+pause(返回1)；完成→返回0；异常退出→pause(返回2)
  local s=$1 LOG=$OUT/seed${s}_train.log last=-1 tick=0
  while tmux has-session -t train$s 2>/dev/null; do
    local n; n=$(wc -l < "$LOG" 2>/dev/null || echo 0)
    if [ "$n" -gt "$last" ]; then
      tail -n $((n-last)) "$LOG" | grep '^Ep ' | while IFS= read -r line; do
        read -r r c v < <(parse_ep "$line")
        if [ -n "$r" ] && awk -v r="$r" 'BEGIN{exit !(r<-200000)}'; then
          log "!! ANOMALY seed $s reward=${r}<-200000 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP --seed $s "; return 1
        fi
        if [ -n "$c" ] && [ -n "$v" ] && awk -v c="$c" -v v="$v" 'BEGIN{exit !(c>1300 && v>200)}'; then
          log "!! ANOMALY seed $s coupler=${c}kN viol=${v} 同时超限 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP --seed $s "; return 1
        fi
      done
      last=$n
    fi
    sleep 300
    tick=$((tick+1))
    [ $((tick % 6)) -eq 0 ] && snapshot
  done
  # tmux 会话结束：确认是否正常完成
  if done_check "$s"; then
    log "seed $s 完成（完成标记+tmux 退出）✅"
    snapshot
    return 0
  fi
  log "!! seed $s tmux 退出但无完成标记（异常/被杀）—— PAUSE 等待处置"
  tail -6 "$LOG" >> "$PATROL"
  return 2
}

log "=== supervise formation start (tmux 模式, curriculum=$CURR) ==="
snapshot

for s in 0 1 2 3 4; do
  if done_check "$s"; then log "seed $s 已完成，跳过"; continue; fi
  if tmux has-session -t train$s 2>/dev/null; then
    log "seed $s 已在运行(train$s)，等待其完成"
  else
    launch_seed "$s"
  fi
  wait_seed "$s"
  rc=$?
  if [ $rc -ne 0 ]; then
    log "=== supervise PAUSED at seed $s（异常，等待处置；修复后重跑本脚本继续）==="
    exit 1
  fi
done
log "=== supervise DONE: seeds 0-4 全部完成 ==="
snapshot
