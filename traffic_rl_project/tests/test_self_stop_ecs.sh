#!/usr/bin/env bash
# self_stop_ecs.sh 的离线 mock 测试（不连云、不碰实例）。
# 用本地 HTTP server 模拟 IMDS，用 PATH 前置的 mock aliyun 模拟 API。
# 验证：① 成功路径传 StopCharging + 复核回执；② aliyun 缺失 rc=2；
#       ③ API 失败 rc=1；④ 复核超时 rc=1。
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/cloud/self_stop_ecs.sh"
TMP=$(mktemp -d)
PORT=$((18000 + RANDOM % 1000))
SRV_PID=""
cleanup() { [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null; sleep 0.3; rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT
PASS=0; FAIL=0
ok() { echo "  PASS $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL $1"; FAIL=$((FAIL+1)); }

mkdir -p "$TMP/imds/latest/meta-data" "$TMP/bin"
echo "i-mock123456" > "$TMP/imds/latest/meta-data/instance-id"
echo "cn-heyuan"   > "$TMP/imds/latest/meta-data/region-id"
(cd "$TMP/imds" && python3 -m http.server "$PORT" >/dev/null 2>&1 & echo $! > "$TMP/srv.pid")
sleep 1
SRV_PID=$(cat "$TMP/srv.pid")
export SELF_STOP_IMDS="http://127.0.0.1:$PORT/latest/meta-data"
export SELF_STOP_LOG="$TMP/self_stop.log"
export SELF_STOP_VERIFY_RETRIES=2 SELF_STOP_VERIFY_SLEEP=0

make_mock_aliyun() {
  local scenario="$1"
  cat > "$TMP/bin/aliyun" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$TMP/aliyun.calls"
case "\$1 \$2" in
  "ecs StopInstance")
    [ "$scenario" = "stopfail" ] && { echo "mock stop error" >&2; exit 1; }
    echo '{"RequestId":"mock"}' ;;
  "ecs DescribeInstances")
    if [ "$scenario" = "verifytimeout" ]; then
      echo '{"Instances":{"Instance":[{"Status":"Running","StoppedMode":"KeepCharging"}]}}'
    else
      echo '{"Instances":{"Instance":[{"Status":"Stopped","StoppedMode":"StopCharging"}]}}'
    fi ;;
esac
EOF
  chmod +x "$TMP/bin/aliyun"
}

echo "== 场景1：成功路径 =="
make_mock_aliyun ok
PATH="$TMP/bin:$PATH" bash "$SCRIPT" DEAD_HEARTBEAT >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "rc=0" || bad "rc=$rc (expect 0)"
grep -q 'StopInstance.*--StoppedMode StopCharging' "$TMP/aliyun.calls" && ok "传 StopCharging" || bad "未传 StopCharging"
grep -q 'DEAD_HEARTBEAT' "$SELF_STOP_LOG" && ok "reason 入日志" || bad "reason 未入日志"
grep -q 'VERIFIED Status=Stopped StoppedMode=StopCharging' "$SELF_STOP_LOG" && ok "复核回执" || bad "无复核回执"

echo "== 场景2：aliyun 缺失（PATH 去掉 mock bin，保留系统）=="
rm -f "$TMP/bin/aliyun"
PATH="/usr/bin:/bin" bash "$SCRIPT" test >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "rc=2 前置失败" || bad "rc=$rc (expect 2)"

echo "== 场景3：API 调用失败 =="
make_mock_aliyun stopfail
PATH="$TMP/bin:$PATH" bash "$SCRIPT" test >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] && ok "rc=1 API 失败" || bad "rc=$rc (expect 1)"
grep -q 'STOP_API_ERROR' "$SELF_STOP_LOG" && ok "记录 API 错误" || bad "未记录 API 错误"

echo "== 场景4：复核超时 =="
make_mock_aliyun verifytimeout
PATH="$TMP/bin:$PATH" bash "$SCRIPT" test >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] && ok "rc=1 复核超时" || bad "rc=$rc (expect 1)"
grep -q 'VERIFY_TIMEOUT' "$SELF_STOP_LOG" && ok "记录复核超时" || bad "未记录超时"

echo "---- PASS=$PASS FAIL=$FAIL ----"
[ "$FAIL" -eq 0 ]
