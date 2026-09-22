#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# formation 多 seed 串行训练自动接力（ADR-013 唯一 RL，3列×1+1=6 agents）
# 职责：seed0→seed1→seed2→seed3→seed4 逐个接力；
#       发散检测（coupler>1300kN / viol>200）→ 杀进程 + PAUSE 等待处置；
#       异常/崩溃（进程消失但无完成标记）→ PAUSE 等待处置。
# 启动：nohup bash _relay_formation.sh >/dev/null 2>&1 &
# ═══════════════════════════════════════════════════════════════════════════
REPO=/mnt/d/Code/MultiAgent/traffic_rl_project
OUT=$REPO/outputs/checkpoints_formation
RELAY=$OUT/relay.log
EXP=configs/experiments/formation_ed_ab_3train_1plus1.yaml

log() { echo "[$(date '+%F %T')] $*" >> "$RELAY"; }

launch() {
  local s=$1
  cd "$REPO" || exit 9
  source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
  nohup python run_training.py --experiment "$EXP" --seed "$s" --episodes 120 \
    --checkpoint_dir outputs/checkpoints_formation/seed$s \
    --results_dir outputs/checkpoints_formation/seed$s/results \
    --override dirs.figures_dir=outputs/checkpoints_formation/seed$s/figures \
    > outputs/checkpoints_formation/seed${s}_train.log 2>&1 &
  log "launch seed $s (PID $!) -> seed${s}_train.log"
}

seed_running() { # $1=seed
  pgrep -f "run_training.py --experiment $EXP --seed $1 " >/dev/null
}

done_check() { # $1=seed
  local s=$1 LOG=$OUT/seed${s}_train.log
  [ -f "$LOG" ] || return 1
  grep -q "训练完成" "$LOG" && return 0
  tail -60 "$LOG" | grep -qE "Ep 120/120" && return 0
  return 1
}

# 解析一行 Ep 日志，输出: reward coupler viol（无则空）
parse_ep() { echo "$1" | awk '
  /^Ep / {
    r=""; c=""; v=""
    if (match($0, /Reward -?[0-9.]+/)) r=substr($0, RSTART+7, RLENGTH-7)+0
    if (match($0, /peakCoupler [0-9.]+/)) c=substr($0, RSTART+12, RLENGTH-12)+0
    if (match($0, /viol [0-9.]+/)) v=substr($0, RSTART+5, RLENGTH-5)+0
    print r, c, v
  }' ; }

wait_seed() { # $1=seed ; 返回 0=正常完成 1=异常(发散/崩溃)
  local s=$1 LOG=$OUT/seed${s}_train.log
  local last=-1
  while :; do
    if ! seed_running "$s"; then
      if done_check "$s"; then
        local meta=$OUT/seed$s/results/metadata.json
        if [ -f "$meta" ]; then log "seed $s 完成（完成标记+进程退出）metadata OK: $meta"
        else log "!! seed $s 完成但 metadata.json 缺失: $meta"; fi
        return 0
      fi
      log "!! seed $s 进程退出但未见完成标记（疑似崩溃/被中断）"
      tail -6 "$LOG" >> "$RELAY"
      return 1
    fi
    # 增量读日志，发散检测
    local n; n=$(wc -l < "$LOG")
    if [ "$n" -gt "$last" ]; then
      local line
      tail -n $((n-last)) "$LOG" | grep '^Ep ' | while IFS= read -r line; do
        read -r r c v < <(parse_ep "$line")
        if [ -n "$c" ] && awk -v c="$c" 'BEGIN{exit !(c>1300)}'; then
          log "!! ANOMALY seed $s peakCoupler=${c}kN>1300 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP --seed $s "; return 1
        fi
        if [ -n "$v" ] && awk -v v="$v" 'BEGIN{exit !(v>200)}'; then
          log "!! ANOMALY seed $s viol=$v>200 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP --seed $s "; return 1
        fi
      done
      last=$n
    fi
    sleep 120
  done
}

active=$(pgrep -af run_training | grep -oE -- '--seed [0-9]' | head -1 | awk '{print $2}')
[ -z "$active" ] && active=none
log "=== relay formation start (active_seed=$active) ==="

for s in 0 1 2 3 4; do
  if done_check "$s"; then log "seed $s 已完成，跳过"; continue; fi
  if ! seed_running "$s"; then launch "$s"; else log "seed $s 已在运行，等待其完成"; fi
  if ! wait_seed "$s"; then
    log "=== relay PAUSED at seed $s（异常，等待处置；修复后重跑本脚本继续）==="
    exit 1
  fi
done
log "=== relay DONE: seeds 0-4 全部完成 ==="
