#!/usr/bin/env bash
# cover_quick_eval_watch.sh 离线 mock 测试：不跑真实评估、不碰实例。
# 验证 ckpt ep 解析 + EVERY 倍率门控 + 破线触发 self_stop。
set -uo pipefail
ROOT_REAL="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT_REAL/scripts/cloud/cover_quick_eval_watch.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { echo "  PASS $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL $1"; FAIL=$((FAIL+1)); }

# 造 mock 环境目录
export ROOT="$TMP/root"
CK="$ROOT/outputs/checkpoints/formation_10kt_1plus108/w4cover_full_20261118"
RD="$ROOT/outputs/results/formation_10kt_1plus108/w4cover_full_20261118"
DE="$ROOT/outputs/results/decompose"
mkdir -p "$CK" "$RD" "$DE" "$TMP/bin" "$ROOT/scripts/cloud"
# 造 ep10 ckpt 快照（文件名按 logger.py 命名规则）
touch "$CK/mappo_fleet_last_ep10_w4cover_full_20261118_seed0.pt"
# mock python：拦截 evaluate_decompose 调用 → 直接写破线 JSON；普通 python 调用（judge）透传给真 python
cat > "$TMP/bin/python" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "src.evaluation.evaluate_decompose" ]; then
    # 从 --out_suffix 取 tag，写对应产物 JSON（破线：band 0.80）
    suffix=""; prev=""
    for x in "$@"; do [ "$prev" = "--out_suffix" ] && suffix="$x"; prev="$x"; done
    out="/tmp/PLACEHOLDER/outputs/results/decompose/eval_decompose_decompose_m1_ms31500${suffix}.json"
    echo '{"results":{"peak_coupler_kN":1300.0,"band_rate":0.80,"rear_end_steps":0}}' > "$out"
    exit 0
  fi
done
exec /usr/bin/env python3 "$@"
EOF
sed -i "s|/tmp/PLACEHOLDER|$ROOT|" "$TMP/bin/python"
chmod +x "$TMP/bin/python"
# mock self_stop：记录调用
cat > "$ROOT/scripts/cloud/self_stop_ecs.sh" <<'EOF'
#!/usr/bin/env bash
echo "$*" > /tmp/PLACEHOLDER/selfstop.called
EOF
sed -i "s|/tmp/PLACEHOLDER|$TMP|" "$ROOT/scripts/cloud/self_stop_ecs.sh"
chmod +x "$ROOT/scripts/cloud/self_stop_ecs.sh"

export SELF_STOP_SCRIPT="$ROOT/scripts/cloud/self_stop_ecs.sh"
export EVERY=10 EVAL_STEPS=31500 POLL=1

echo "== 破线场景（ep10 band 0.80 < 0.85）=="
timeout 20 env PATH="$TMP/bin:$PATH" bash "$SCRIPT" >"$TMP/watch.log" 2>&1; rc=$?
grep -q 'BREAK_LINE 触发自停机' "$TMP/watch.log" && ok "识别破线" || bad "未识别破线: $(tail -5 "$TMP/watch.log")"
[ -f "$TMP/selfstop.called" ] && ok "调用 self_stop" || bad "未调 self_stop"
grep -q 'BREAK_LINE_ep10' "$TMP/selfstop.called" && ok "reason 含 ep10" || bad "reason 错"
[ -f "$RD/BREAK_LINE.txt" ] && ok "写 BREAK_LINE 标记" || bad "未写标记"

echo "== ep 非倍率门控场景（ep5 不触发）=="
rm -rf "$ROOT"; mkdir -p "$CK" "$RD" "$DE" "$ROOT/scripts/cloud"
touch "$CK/mappo_fleet_last_ep5_w4cover_full_20261118_seed0.pt"
cp "$TMP/../$(basename $TMP)/bin/python" "$TMP/bin/python" 2>/dev/null || true
# 重建 mock self_stop（上一步 rm 掉了）
cat > "$ROOT/scripts/cloud/self_stop_ecs.sh" <<'EOF'
#!/usr/bin/env bash
echo "$*" > /tmp/PLACEHOLDER/selfstop2.called
EOF
sed -i "s|/tmp/PLACEHOLDER|$TMP|" "$ROOT/scripts/cloud/self_stop_ecs.sh"; chmod +x "$ROOT/scripts/cloud/self_stop_ecs.sh"
timeout 4 env PATH="$TMP/bin:$PATH" bash "$SCRIPT" >"$TMP/watch2.log" 2>&1 || true
[ ! -f "$TMP/selfstop2.called" ] && ok "ep5 不触发" || bad "ep5 误触发"

echo "---- PASS=$PASS FAIL=$FAIL ----"
[ "$FAIL" -eq 0 ]
