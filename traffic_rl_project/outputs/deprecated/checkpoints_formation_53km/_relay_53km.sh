#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# formation 多 seed 串行训练自动接力 —— 53km 主线（shuozhou_real_53km）
# （ADR-013 唯一 RL，3列×1+1=6 agents，逐列速度 APF 势场 reward）
# 职责：seed0(现场运行)→seed1→seed2→seed3→seed4 逐个接力；
#       发散检测（coupler>1300kN / viol>200）→ 杀进程 + PAUSE 等待处置；
#       异常/崩溃（进程消失但无完成标记）→ PAUSE 等待处置。
# ⚠ 本脚本替换旧 _relay_formation.sh：旧脚本写 23.8km 已禁止训练，勿再用。
# seed0 现场启动无显式 --seed，靠 override 目录 run2/seed0 识别；seed1-4 由本脚本
# 以 --seed N 启动并写入 seedN_train.log。完成后 relay.log 留痕。
# 启动：nohup bash _relay_53km.sh >/dev/null 2>&1 &
# ═══════════════════════════════════════════════════════════════════════════
REPO=/mnt/d/Code/MultiAgent/traffic_rl_project
OUT=$REPO/outputs/checkpoints_formation_53km
RELAY=$OUT/relay.log
EXP=configs/experiments/formation_ed_ab_3train_1plus1.yaml
SHARED_LOG=$OUT/train.log           # seed0 现场运行写在此共享日志

log() { echo "[$(date '+%F %T')] $*" >> "$RELAY"; }

seed0_running() { pgrep -f "checkpoints_formation_53km/run2/seed0" >/dev/null \
                  || pgrep -f "run_training.py --experiment $EXP --seed 0 " >/dev/null; }
seedN_running() { pgrep -f "run_training.py --experiment $EXP --seed $1 " >/dev/null; }

done_check() { # $1=seed ; seed0 走共享 train.log，seed1-4 走各自日志
  local s=$1 LOG
  if [ "$s" -eq 0 ]; then LOG=$SHARED_LOG; else LOG=$OUT/seed${s}_train.log; fi
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

launch() { # 仅用于 seed1-4
  local s=$1
  cd "$REPO" || exit 9
  source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
  nohup python run_training.py --experiment "$EXP" --seed "$s" --episodes 120 \
    --checkpoint_dir outputs/checkpoints_formation_53km/seed$s \
    --results_dir outputs/checkpoints_formation_53km/seed$s/results \
    --override dirs.figures_dir=outputs/checkpoints_formation_53km/seed$s/figures \
    > outputs/checkpoints_formation_53km/seed${s}_train.log 2>&1 &
  log "launch seed $s (PID $!) -> seed${s}_train.log"
}

# 增量发散检测：$1=LOG $2=已消费行数；命中务必归零 $2 由上层赋新值
scan_anom() { # $1=LOG $2=last -> 返回(经由全局 ANOM)：0 正常
  local LOG=$1 n
  n=$(wc -l < "$LOG" 2>/dev/null || echo 0)
  [ "$n" -le "$2" ] && { echo 0; return; }
  local line r c v
  while IFS= read -r line; do
    read -r r c v < <(parse_ep "$line")
    if [ -n "$c" ] && awk -v c="$c" 'BEGIN{exit !(c>1300)}'; then
      log "!! ANOMALY peakCoupler=${c}kN>1300 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP"; echo 1; return
    fi
    if [ -n "$v" ] && awk -v v="$v" 'BEGIN{exit !(v>200)}'; then
      log "!! ANOMALY viol=$v>200 -> KILL & PAUSE"; pkill -f "run_training.py --experiment $EXP"; echo 1; return
    fi
  done < <(tail -n "$((n-$2))" "$LOG" | grep '^Ep ')
  echo 0
}

wait_seed0() { # 等待现场 seed0 结束；发散则 KILL+PAUSE
  local last=0
  while :; do
    if ! pgrep -f "run_training.py --experiment $EXP" >/dev/null; then
      if done_check 0; then
        if [ -f "$OUT/run2/seed0/results/metadata.json" ]; then
          log "seed 0 完成，metadata OK: $OUT/run2/seed0/results/metadata.json"
        else
          log "!! seed 0 完成但 metadata.json 缺失: $OUT/run2/seed0/results/metadata.json"
        fi
        return 0
      fi
      log "!! seed 0 进程退出但未见完成标记（疑似崩溃/被中断）"; tail -6 "$SHARED_LOG" >> "$RELAY"; return 1
    fi
    [ "$(scan_anom "$SHARED_LOG" "$last")" = 1 ] && return 1
    last=$(wc -l < "$SHARED_LOG" 2>/dev/null || echo 0)
    sleep 120
  done
}

wait_seedN() { # $1=seed(≥1)；完成=0 发散/崩溃=1
  local s=$1 LOG=$OUT/seed${s}_train.log last=0
  while :; do
    if ! seedN_running "$s"; then
      if done_check "$s"; then
        [ -f "$OUT/seed$s/results/metadata.json" ] && log "seed $s 完成，metadata OK: $OUT/seed$s/results/metadata.json" \
          || log "!! seed $s 完成但 metadata 缺失: $OUT/seed$s/results/metadata.json"
        return 0
      fi
      log "!! seed $s 进程退出但未见完成标记（疑似崩溃/被中断）"; tail -6 "$LOG" >> "$RELAY"; return 1
    fi
    [ "$(scan_anom "$LOG" "$last")" = 1 ] && return 1
    last=$(wc -l < "$LOG" 2>/dev/null || echo 0)
    sleep 120
  done
}

log "=== relay 53km start (active=$(pgrep -af run_training | grep -oE -- '(--seed [0-9]|run2/seed0)' | tr '\n' ' ')) ==="

# seed0：现场运行或已完，先归并
if done_check 0; then
  log "seed 0 已完成（交由现场结果），跳过等待"
elif seed0_running || pgrep -f "run_training.py --experiment $EXP" >/dev/null; then
  log "seed 0 正在运行（run2/seed0 / 现场 train.log），等待完成"
  wait_seed0 || { log "=== relay 53km PAUSED at seed0（异常，等待处置；修复后重跑本脚本继续）==="; exit 1; }
else
  log "!! seed0 未完成也未在跑（现场可能已被清理）-> PAUSE 等待处置"
  log "=== relay 53km PAUSED at seed0（现场缺失）==="; exit 1
fi

# seed1-4 接力
for s in 1 2 3 4; do
  if done_check "$s"; then log "seed $s 已完成，跳过"; continue; fi
  launch "$s"
  wait_seedN "$s" || { log "=== relay 53km PAUSED at seed$s（异常，等待处置；修复后重跑本脚本继续）==="; exit 1; }
done
log "=== relay 53km DONE: seeds 0-4 全部完成 ==="