#!/usr/bin/env bash
# instance_watchdog.sh 离线 mock：self_stop 失败时不得 OS poweroff
# （2026-11-18 nincr ep10 缺口：poweroff 不停费且让 closer 读不到标记）。
# 不碰真实实例、不调用真实 poweroff。
set -uo pipefail
ROOT_REAL="$(cd "$(dirname "$0")/.." && pwd)"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
# Windows checkout 的 .sh 可能是 CRLF：先转 LF 副本再跑（老坑：set:pipefail invalid）
SCRIPT="$TMP/instance_watchdog.sh"
sed 's/\r$//' "$ROOT_REAL/scripts/cloud/instance_watchdog.sh" > "$SCRIPT"
PASS=0; FAIL=0
ok() { echo "  PASS $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL $1"; FAIL=$((FAIL+1)); }

mkdir -p "$TMP/bin" "$TMP/results"
cat > "$TMP/fail_self_stop.sh" <<'EOF'
#!/usr/bin/env bash
echo "FAIL CLI_MISSING mock" >&2
exit 1
EOF
chmod +x "$TMP/fail_self_stop.sh"
cat > "$TMP/bin/poweroff" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> /tmp/PLACEHOLDER/poweroff.called
EOF
cat > "$TMP/bin/shutdown" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> /tmp/PLACEHOLDER/poweroff.called
EOF
sed -i "s|/tmp/PLACEHOLDER|$TMP|" "$TMP/bin/poweroff" "$TMP/bin/shutdown"
chmod +x "$TMP/bin/poweroff" "$TMP/bin/shutdown"

echo "== 场景 C：训练进程消失且无 exit_code =="
SELF_STOP_SCRIPT="$TMP/fail_self_stop.sh" \
timeout 15 env PATH="$TMP/bin:$PATH" bash "$SCRIPT" \
  --results-dir "$TMP/results" --train-pid 999999 --grace-s 0 \
  --ledger "$TMP/ledger.txt" >"$TMP/out.log" 2>&1
ls "$TMP"/results/DEAD_*.txt >/dev/null 2>&1 && ok "写 DEAD 标记（closer abort-glob 可读）" || bad "未写 DEAD 标记"
[ ! -f "$TMP/poweroff.called" ] && ok "self_stop 失败后不 OS poweroff" || bad "仍调用 poweroff（ssh 断→closer 空等到点）"
grep -q '等本地 closer API 停机' "$TMP/ledger.txt" && ok "留痕交本地 closer 收账" || bad "未留痕 closer 收账"

echo "== 场景 B：训练退出有 exit_code =="
: > "$TMP/results/exit_code.txt"
SELF_STOP_SCRIPT="$TMP/fail_self_stop.sh" \
timeout 15 env PATH="$TMP/bin:$PATH" bash "$SCRIPT" \
  --results-dir "$TMP/results" --train-pid 999999 --grace-s 0 \
  --ledger "$TMP/ledger2.txt" >"$TMP/out2.log" 2>&1
[ ! -f "$TMP/poweroff.called" ] && ok "exit_code 路径也不 poweroff" || bad "exit_code 路径仍 poweroff"

echo "---- PASS=$PASS FAIL=$FAIL ----"
[ "$FAIL" -eq 0 ]
