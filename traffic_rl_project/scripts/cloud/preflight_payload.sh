#!/usr/bin/env bash
# 上云预检（payload 级）——开实例前必须在本地 WSL 全部 PASS。
#
# 与 preflight_aliyun_ecs.py（查 VPC/安全组/密钥对/镜像）互补：那个查"能不能下单"，
# 这个查"开机后能不能立刻跑、跑出来能不能判"。任一 FAIL 即 exit 1，且删除 .preflight_ok。
#
# 用法（本地 WSL）：
#   bash scripts/cloud/preflight_payload.sh --episodes 60 --seed 0 \
#        --ckpt-dir outputs/checkpoints/formation_10kt_1plus108/<run> \
#        [--resume <path/to/last_epN.pt>]
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT" || exit 1

CONFIG="configs/experiments/formation_ed_ab_3train_1plus108.yaml"
EPISODES=60; SEED=0; CKPT_DIR=""; RESUME=""
MARK="$ROOT/.preflight_ok"
while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2;;
    --episodes) EPISODES="$2"; shift 2;;
    --seed) SEED="$2"; shift 2;;
    --ckpt-dir) CKPT_DIR="$2"; shift 2;;
    --resume) RESUME="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 2;;
  esac
done

FAIL=0; WARN=0
ok()   { printf '  [PASS] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  [WARN] %s\n' "$*"; WARN=$((WARN+1)); }
hr()   { printf '%s\n' "------------------------------------------------------------"; }

hr; echo "上云预检 payload 级 | root=$ROOT"; hr

# 1) 代码快照 -------------------------------------------------------------
echo "1) 代码快照"
if git rev-parse --git-dir > /dev/null 2>&1; then
  COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo NA)
  DIRTY=$(git status --porcelain 2>/dev/null | wc -l)
  SNAP=$(find src configs run_training.py scripts -type f \
           \( -name '*.py' -o -name '*.yaml' -o -name '*.sh' \) -print0 \
         | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -c1-16)
  ok "commit=$COMMIT payload_sha=$SNAP dirty_files=$DIRTY"
  [ "$DIRTY" -eq 0 ] || warn "工作区有 $DIRTY 个未提交改动：上云按当前工作区打包，确认这份快照就是要用的口径"
else
  bad "不是 git 仓库，无法固定代码快照"
fi

# 2) 配置键值 -------------------------------------------------------------
echo "2) 配置键值与奖励分量通道"
CFG_OUT=$(${PY:-python} - "$CONFIG" "$EPISODES" <<'EOF' 2>&1
import sys, os, yaml
cfg_path, episodes = sys.argv[1], int(sys.argv[2])
errs = []
if not os.path.exists(cfg_path):
    print(f"FAIL 配置不存在 {cfg_path}"); sys.exit(0)
c = yaml.safe_load(open(cfg_path, encoding='utf-8')) or {}
env = c.get('env_cfg', {}) or {}
def need(cond, msg):
    if not cond: errs.append(msg)
need(int(c.get('n_env', 0)) >= 1, 'n_env 缺失/非法')
need(bool(c.get('n_env_parallel', False)), 'n_env_parallel 未开（否则 n_env 是单核串行）')
need(env.get('reward_term_log') is True, 'env.reward_term_log 未开 → 判据③无数据')
need(float(env.get('coupler_force_limit_n', 0)) == 1000000.0, 'coupler_force_limit_n != 1.0e6（验收口径被改）')
need(bool(env.get('route_end_m', 0)), 'route_end_m 缺失（截断口径未固定）')
need(str(env.get('speed_band_shape', '')) == 'ref', 'speed_band_shape != ref')
need(bool(env.get('decompose', '')), 'decompose 缺失（非机车级 ED/AB）')
need(int(c.get('log_interval', 0)) == 1, 'log_interval != 1（每集落 CSV / 每集 checkpoint 依赖它）')
ref = str(env.get('speed_ref_table', ''))
need(ref and os.path.exists(ref), f'参考速度表不存在 {ref}')
print(('FAIL ' + '; '.join(errs)) if errs else
      f"OK episodes_yaml={int(c.get('episodes', 0))} cli_episodes={episodes} "
      f"n_env={int(c.get('n_env', 0))} route_end_m={float(env.get('route_end_m', 0)):.0f} ref={ref}")
EOF
)
case "$CFG_OUT" in
  OK*) ok "$CFG_OUT";;
  *)   bad "${CFG_OUT:-配置检查无输出}";;
esac

# 3) 参考速度表可读 -------------------------------------------------------
echo "3) 参考速度表"
REF=$(${PY:-python} - "$CONFIG" <<'EOF' 2>&1
import sys, yaml, numpy as np
env = (yaml.safe_load(open(sys.argv[1], encoding='utf-8')) or {}).get('env_cfg', {}) or {}
p = env.get('speed_ref_table', '')
try:
    z = np.load(p)
    print('OK keys=' + ','.join(list(z.keys())[:6]))
except Exception as e:
    print('FAIL ' + str(e)[:120])
EOF
)
case "$REF" in OK*) ok "$REF";; *) bad "$REF";; esac

# 4) BC 权重 --------------------------------------------------------------
echo "4) BC 热启动权重"
if [ -z "$CKPT_DIR" ]; then
  warn "未给 --ckpt-dir，跳过 BC 权重检查"
else
  BC="$CKPT_DIR/bc_warmstart.pt"
  if [ -f "$BC" ]; then
    BCOK=$(${PY:-python} - "$BC" <<'EOF' 2>&1
import sys, torch
try:
    d = torch.load(sys.argv[1], map_location='cpu', weights_only=False)
    keys = list(d.keys()) if isinstance(d, dict) else []
    has_v = any('value_state_dict' in str(k) for k in keys) or (
        isinstance(d, dict) and isinstance(d.get('value'), dict))
    print(('OK' if has_v else 'WARN 缺 value_state_dict') + f" top_keys={keys[:4]}")
except Exception as e:
    print('FAIL ' + str(e)[:120])
EOF
)
    case "$BCOK" in
      OK*) ok "$BC $BCOK";;
      WARN*) warn "$BC $BCOK";;
      *) bad "$BCOK";;
    esac
  else
    bad "warm_start=true 但 $BC 不存在（--resume-weights-only 会读它）"
  fi
fi

# 5) 续训 checkpoint ------------------------------------------------------
echo "5) 续训 checkpoint"
if [ -z "$RESUME" ]; then
  warn "未指定 --resume：将从 BC 起步（60 集从 0 开始，与 40 集续跑的判据口径不同）"
else
  if [ ! -f "$RESUME" ]; then
    bad "续训权重不存在 $RESUME"
  else
    RSOUT=$(${PY:-python} - "$RESUME" <<'EOF' 2>&1
import sys, torch
try:
    d = torch.load(sys.argv[1], map_location='cpu', weights_only=False)
    if isinstance(d, dict) and isinstance(d.get('metadata'), dict):
        d = d['metadata']
    ep = None
    for k in ('done_ep', 'episode', 'global_ep'):
        if isinstance(d, dict) and d.get(k) is not None:
            ep = d.get(k); break
    print(f"OK done_ep={ep}")
except Exception as e:
    print('FAIL ' + str(e)[:120])
EOF
)
    case "$RSOUT" in OK*) ok "$RESUME $RSOUT";; *) bad "$RSOUT";; esac
  fi
fi

# 6) 依赖版本 -------------------------------------------------------------
echo "6) 依赖版本（须与镜像一致）"
DEP=$(${PY:-python} - <<'EOF' 2>&1
import sys
try:
    import numpy, numba, torch
    print(f"OK py={sys.version.split()[0]} numpy={numpy.__version__} "
          f"numba={numba.__version__} torch={torch.__version__}")
except Exception as e:
    print('FAIL ' + str(e)[:120])
EOF
)
case "$DEP" in
  OK*) ok "$DEP";;
  *) bad "$DEP";;
esac

# 7) 启动/看护脚本 --------------------------------------------------------
echo "7) 启动与看护脚本"
for f in scripts/cloud/instance_bootstrap.sh scripts/cloud/instance_watchdog.sh; do
  if [ ! -f "$f" ]; then bad "缺 $f"; continue; fi
  if bash -n "$f"; then ok "语法 OK $f"; else bad "语法错误 $f"; fi
done

# 8) 退出码与完成判据约定 -------------------------------------------------
echo "8) 退出码与完成判据"
grep -q 'exit_code.txt' scripts/cloud/instance_bootstrap.sh \
  && ok "bootstrap 落 exit_code.txt" || bad "bootstrap 未落 exit_code.txt"
grep -q '训练完成' run_training.py src/trainer/train_runner.py \
  && ok "训练入口含「训练完成」完成标记" || bad "无完成标记，完成判据不成立"
grep -q 'device=cpu' scripts/cloud/instance_bootstrap.sh \
  && ok "bootstrap 显式 device=cpu" || bad "bootstrap 未钉 device=cpu（有 GPU 会切 cuda 更慢）"
grep -q 'results_dir' scripts/cloud/instance_bootstrap.sh \
  && grep -q 'figures_dir' scripts/cloud/instance_bootstrap.sh \
  && ok "三输出目录均重定向" || bad "三输出目录未同时重定向（LRN-20261001-009）"

# 收口 --------------------------------------------------------------------
hr
if [ "$FAIL" -eq 0 ]; then
  {
    echo "preflight_ok_at=$(date -Is)"
    echo "commit=${COMMIT:-NA}"
    echo "payload_sha=${SNAP:-NA}"
    echo "config=$CONFIG"
    echo "episodes=$EPISODES seed=$SEED"
    echo "resume=${RESUME:-none}"
    echo "warn=$WARN"
  } > "$MARK"
  echo "结论：PASS（FAIL=0, WARN=$WARN）→ 已写 $MARK"
  echo "下一步：本文件随代码一起 rsync 上云，实例上 bootstrap 检到它才允许开跑。"
  exit 0
else
  rm -f "$MARK"
  echo "结论：FAIL=$FAIL, WARN=$WARN → 不许开实例（未写 $MARK）"
  exit 1
fi
