#!/usr/bin/env bash
# 云侧快评看护（G1 第 4 问协议固化，ADR-073 第 4 投）：训练中每 10 集插确定性快评，
# 破线即杀（触发实例内自停机 self_stop_ecs.sh）。v21 用临时脚本做此事，本脚本固化进仓库。
#
# 判据（src/evaluation/cover_quick_eval.py，单测 8/8）：
#   零穿透 / band >= 0.85 / peak <= 1500 安全线 / peak 较上次快评上行 <= 2% 噪声带。
# 不达标 = 写 BREAK_LINE 标记 + 调 self_stop；达标 = 记一行继续。
# 与训练主进程并行运行；训练正常结束由 instance_watchdog.sh 收尾，本脚本只管破线早停。
set -uo pipefail
ROOT="${ROOT:-/root/traffic_rl_project}"
RUN_ID="${RUN_ID:-w4cover_full_20261118}"
CKPT_DIR="$ROOT/outputs/checkpoints/formation_10kt_1plus108/$RUN_ID"
RES_DIR="$ROOT/outputs/results/formation_10kt_1plus108/$RUN_ID"
LOG_DIR="$ROOT/outputs/logs/cloud"
# 【2026-11-18】评估配置改为可覆盖：快评环境必须与训练配置同源（decompose 模式、
# act_dim 一致），否则策略载入即失败/快评静默失效。默认保持 cover 配置（零回归）。
EVAL_CFG="${EVAL_CFG:-configs/experiments/formation_ed_ab_3train_1plus108_cover.yaml}"
EVAL_STEPS="${EVAL_STEPS:-31500}"        # v21 口径（全程确定性评估步数）
EVERY="${EVERY:-10}"                      # 每 10 集快评
POLL="${POLL:-300}"                       # 5 min 轮询
SELF_STOP="${SELF_STOP_SCRIPT:-$ROOT/scripts/cloud/self_stop_ecs.sh}"
WLOG="$LOG_DIR/quick_eval_$RUN_ID.log"
mkdir -p "$RES_DIR" "$LOG_DIR"

log() { echo "$(date -Is) [quick_eval] $*" | tee -a "$WLOG"; }
prev_peak=""
done_marks="$RES_DIR/.quick_eval_done"

# 等待 ckpt 出现（训练启动中）
log "watch_start run=$RUN_ID every=$EVERY steps=$EVAL_STEPS"
while true; do
  # 训练进程消失 → 收尾由 watchdog 负责，本脚本退出
  if [ -f "$CKPT_DIR/train_finished.marker" ]; then
    log "train_finished marker seen, watcher exit"; exit 0
  fi
  # 找最新 ep：训练 ckpt 命名 = mappo_fleet_last_ep{N}_{tag}_seed{S}.pt（logger.py:221），
  # 不写 last_ep.txt——从文件名解析 ep 号，取最大者。
  # 逐个提 ep 号再数值排序（文件名含多段下划线，直接 sort 字段不可靠）
  latest=""; max_ep=0
  for f in "$CKPT_DIR"/mappo_fleet_last_ep*.pt; do
    [ -f "$f" ] || continue
    e=$(basename "$f" | sed -n 's/^mappo_fleet_last_ep\([0-9]*\)_.*/\1/p')
    [ -n "$e" ] && [ "$e" -gt "$max_ep" ] 2>/dev/null && { max_ep="$e"; latest="$f"; }
  done
  ep="$max_ep"
  [ -n "$latest" ] || { sleep "$POLL"; continue; }
  [ -n "$ep" ] || { sleep "$POLL"; continue; }
  # 只处理 EVERY 的倍数且未评估过
  if [ $((ep % EVERY)) -eq 0 ] && [ "$ep" -gt 0 ] && ! grep -qx "$ep" "$done_marks" 2>/dev/null; then
    snap="$latest"   # 直接用该 ep 的快照 ckpt（文件名已含 ep，无需复制）
    tag="_${RUN_ID}_det_ep${ep}"
    log "eval_start ep=$ep steps=$EVAL_STEPS ckpt=$(basename "$snap")"
    # 模块方式跑（SERVER_OPS §15.1 第7条：文件直跑秒挂=79min空转根因）
    # 产物名规则（evaluate_decompose.py:712）：eval_decompose_{mode}_ms{steps}{out_suffix}.json
    python -m src.evaluation.evaluate_decompose \
      --experiment "$EVAL_CFG" --mode decompose_m1 \
      --checkpoint "$snap" --max_steps "$EVAL_STEPS" \
      --n_seed 1 --eval_seed 0 --out_suffix "$tag" >>"$WLOG" 2>&1
    rc=$?
    jf="$ROOT/outputs/results/decompose/eval_decompose_decompose_m1_ms${EVAL_STEPS}${tag}.json"
      if [ "$rc" -ne 0 ] || [ ! -f "$jf" ]; then
        log "eval_FAILED ep=$ep rc=$rc json=${jf:-?}（评估故障不判破线，仅留痕；deadline 兜底）"
      else
        verdict=$(PREV_PEAK="$prev_peak" EVAL_JSON="$jf" python -c "
import os
from src.evaluation.cover_quick_eval import judge
prev = os.environ.get('PREV_PEAK', '')
prev_f = float(prev) if prev else None
r = judge(os.environ['EVAL_JSON'], prev_f)
print(('PASS' if r['pass'] else 'BREAK') + '|' + r['reason'] + '|' + str(r['metrics']['peak_kN']))
")
        echo "$ep" >> "$done_marks"
        log "eval_done ep=$ep verdict=$verdict"
        case "$verdict" in
          BREAK*)
            reason=$(echo "$verdict" | cut -d'|' -f2)
            echo "BREAK_LINE ep=$ep reason=$reason at $(date -Is)" > "$RES_DIR/BREAK_LINE.txt"
            log "BREAK_LINE 触发自停机：ep=$ep reason=$reason"
            if [ -f "$SELF_STOP" ]; then bash "$SELF_STOP" "BREAK_LINE_ep${ep}" >>"$WLOG" 2>&1; fi
            exit 0
            ;;
          PASS*)
            prev_peak=$(echo "$verdict" | cut -d'|' -f3)
            ;;
        esac
      fi
  fi
  sleep "$POLL"
done
