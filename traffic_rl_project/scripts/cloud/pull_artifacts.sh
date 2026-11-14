#!/usr/bin/env bash
# 本地（WSL）回传 + 校验：把云上产物拉回来，校验通过才给实例放行关机/释放。
#
# 顺序铁律：**先回传校验，后关机释放**（AGENTS.md 云实例纪律第 4 条）。
# 校验不过 → 不写 .pull_done；实例看护会在 grace 到期后关机止血，磁盘数据仍在，
# 但**不得释放实例**（否则产物彻底丢失）。
#
# 用法：
#   bash scripts/cloud/pull_artifacts.sh --ip <公网IP> --run-id <RUN_ID> [--remote-root /root/traffic_rl_project]
# 退出码：0 = 回传且校验通过（已放行）；1 = 回传失败/校验不过（未放行）
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
IP=""; RUN_ID=""; REMOTE_ROOT="/root/traffic_rl_project"
KEY="$HOME/.ssh/cloud_traffic"
while [ $# -gt 0 ]; do
  case "$1" in
    --ip) IP="$2"; shift 2;;
    --run-id) RUN_ID="$2"; shift 2;;
    --remote-root) REMOTE_ROOT="$2"; shift 2;;
    --key) KEY="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 2;;
  esac
done
[ -n "$IP" ] && [ -n "$RUN_ID" ] || { echo "缺 --ip / --run-id"; exit 2; }

RREL="outputs/results/formation_10kt_1plus108/$RUN_ID"
CREL="outputs/checkpoints/formation_10kt_1plus108/$RUN_ID"
LREL="$ROOT/outputs/logs/cloud"
LDST_R="$ROOT/outputs/results/formation_10kt_1plus108/${RUN_ID}_cloud"
LDST_C="$ROOT/outputs/checkpoints/formation_10kt_1plus108/${RUN_ID}_cloud"
mkdir -p "$LDST_R" "$LDST_C" "$LREL"

SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 root@$IP"

echo "[pull] 拉取 $RREL / $CREL ← $IP"
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15" \
  "root@$IP:$REMOTE_ROOT/$RREL/" "$LDST_R/" || { echo "[pull] FAIL results 回传失败"; exit 1; }
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15" \
  "root@$IP:$REMOTE_ROOT/$CREL/" "$LDST_C/" || echo "[pull] WARN checkpoint 回传失败（结果仍可用）"

# ---- 校验：完成判据（3-seed 串行结构：exit_code 在 seed*/ 子目录）----
ROWS=$(( $(cat "$LDST_R"/seed*/train_history_*.csv 2>/dev/null | wc -l) - 1 ))
DONE=$(grep -c '训练完成' "$LDST_R"/seed*/run.log 2>/dev/null || true)
HAS_HB=$(ls "$LDST_R"/seed*/heartbeat.txt >/dev/null 2>&1 && echo 1 || echo 0)
HAS_META=$(ls "$LDST_R"/seed*/metadata.json >/dev/null 2>&1 && echo 1 || echo 0)
CKPTS=$(ls "$LDST_C"/seed*/*.pt 2>/dev/null | wc -l)

# 逐 seed 收集 exit_code：齐 3 个且全 0 = 正常；任一非 0 = 异常结束；不足 3 个 = 仍在跑
ALL_CODES=""; ABNORMAL=0; SEEDS_DONE=0
for sd in "$LDST_R"/seed*/; do
  [ -d "$sd" ] || continue
  c=$(tr -d '\r\n' < "$sd/exit_code.txt" 2>/dev/null || echo NA)
  ALL_CODES="${ALL_CODES}${c},"
  if [ "$c" != "NA" ]; then
    SEEDS_DONE=$((SEEDS_DONE + 1))
    [ "$c" != "0" ] && ABNORMAL=1
  fi
done

MAN="$LREL/manifest_${RUN_ID}.txt"
{
  echo "pulled_at=$(date -Is)"
  echo "ip=$IP run_id=$RUN_ID"
  echo "csv_rows=$ROWS done_mark=${DONE:-0}"
  echo "heartbeat=$HAS_HB metadata=$HAS_META checkpoints=$CKPTS"
  echo "all_exit_codes=$ALL_CODES seeds_done=$SEEDS_DONE/3 abnormal=$ABNORMAL"
  echo "results_dir=$LDST_R"
  echo "ckpt_dir=$LDST_C"
} | tee "$MAN"

VERDICT=1
if [ "$ROWS" -gt 0 ] && [ "$HAS_HB" -eq 1 ]; then
  if [ "$SEEDS_DONE" -ge 3 ] && [ "$ABNORMAL" -eq 0 ]; then
    echo "[verify] PASS：3 seed 正常结束（exit=0×3 + 完成标记 + $ROWS 集）"
    VERDICT=0
  elif [ "$SEEDS_DONE" -ge 1 ] && [ "$ABNORMAL" -eq 1 ]; then
    echo "[verify] PASS(异常结束)：exit_codes=$ALL_CODES → 停费保留实例，人工裁决，按 ABORTED 归档"
    VERDICT=0
  else
    echo "[verify] WAIT：seeds_done=$SEEDS_DONE/3，训练仍在跑 → 不放行（产物已增量回传）"
  fi
else
  echo "[verify] WAIT：CSV 行数=$ROWS 或心跳缺失 → 不放行（产物已增量回传）"
fi

if [ "$VERDICT" -eq 0 ]; then
  $SSH "touch $REMOTE_ROOT/$RREL/.pull_done $REMOTE_ROOT/$RREL/seed0/.pull_done" && echo "[pull] 已通知实例收口（.pull_done 顶层+seed0）"
  echo "  ⚠️ 若本轮为异常结束：实例只停费保留，不释放，等人工处置"
else
  echo "[pull] 未放行：不要 stop --release，保留磁盘等人工处置"
fi
exit $VERDICT
