"""起点口径一致性校验（ADR-067 决策一 / ADR-068 验收项①）。

只读配置与参考表，**零仿真**。把 `起点口径链` 写成断言，防止六个耦合量被单独改动：

    v_max → target_speed=(v_min+v_max)/2 → d_safe=target²/3+2·target
          → d_eff=1.1·d_safe=初始净空（reset 时 gaps 直接取 _formation_ref_gap）
          → init_speed 必须满足 d_safe(init) ≤ d_eff

用法：
    python scripts/check_start_conditions.py \
        --experiment configs/experiments/formation_ed_ab_3train_1plus108.yaml

退出码：0 = 全过；1 = 有断言失败（终端会打印 [FAIL] 行）。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

GAP_EFF_MARGIN = 1.1       # src/environments/train_fleet_env.py:99
A_REF_MPS2 = 1.5           # _fallback_d_safe 的参考减速度
T_REACT_S = 2.0            # 制动建立与反应余量
REF_SPEED_TOL_KMH = 5.0    # ref 表首点与初速的允许差（沿用「5 km/h 带宽」口径）


def d_safe(speed_mps: float) -> float:
    """简化制动安全距离（与 _fallback_d_safe 同源）。"""
    v = max(float(speed_mps), 1.0)
    return v * v / (2.0 * A_REF_MPS2) + v * T_REACT_S


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--experiment', required=True)
    p.add_argument('--repo-root', default='.')
    args = p.parse_args()

    root = Path(args.repo_root).resolve()
    cfg_path = Path(args.experiment)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8'))
    env = cfg.get('env_cfg', cfg)

    v_max_kmh = float(env['v_max']) * 3.6
    v_min_kmh = float(env['v_min']) * 3.6
    init_kmh = float(cfg.get('init_speed_kmh', env.get('init_speed_kmh', 65.0)))
    target_kmh = (v_min_kmh + v_max_kmh) / 2.0
    if 'target_speed' in env:                      # 显式值必须与派生值一致
        target_kmh_cfg = float(env['target_speed']) * 3.6
    else:
        target_kmh_cfg = None

    ds_target = d_safe(target_kmh / 3.6)
    d_eff = GAP_EFF_MARGIN * ds_target
    ds_init = d_safe(init_kmh / 3.6)
    margin_m = d_eff - ds_init
    margin_pct = margin_m / d_eff * 100.0

    print(f'[配置] {cfg_path.relative_to(root) if cfg_path.is_relative_to(root) else cfg_path}')
    print(f'  v_max={v_max_kmh:.1f}  v_min={v_min_kmh:.1f}  target_speed={target_kmh:.2f}  '
          f'init_speed={init_kmh:.1f}  (km/h)')
    print(f'  d_safe(target)={ds_target:.1f} m  →  d_eff=初始净空={d_eff:.1f} m')
    print(f'  d_safe(init)  ={ds_init:.1f} m  →  起步裕量 {margin_m:+.1f} m ({margin_pct:+.1f}%)')

    fails = []

    if margin_m < 0:
        fails.append(f'起步欠裕量：initial 速度需要 {ds_init:.1f} m 制动距离，'
                     f'而初始净空只有 {d_eff:.1f} m（欠 {-margin_m:.1f} m）⇒ 后列起步即 ATP 满制动')
    elif margin_pct < 2.0:
        print(f'  [WARN] 起步裕量仅 {margin_pct:.1f}%（<2%），须由冒烟实测守住')

    if init_kmh >= v_max_kmh:
        fails.append(f'init_speed {init_kmh:.1f} ≥ v_max {v_max_kmh:.1f}：t=0 即计入超速（ADR-049 决策 1）')

    if target_kmh_cfg is not None and abs(target_kmh_cfg - target_kmh) > 1e-6:
        fails.append(f'YAML 显式 target_speed={target_kmh_cfg:.2f} 与派生值 '
                     f'(v_min+v_max)/2={target_kmh:.2f} 不一致')

    # 起点：固定起点配置下，ref 表在起点处的速度应与初速同量级
    start = env.get('start_randomization') or {}
    start_m = start.get('min_m') if start.get('enabled') else None
    table_rel = env.get('speed_ref_table')
    if start_m is not None and table_rel:
        table = Path(table_rel)
        if not table.is_absolute():
            table = root / table
        if table.exists():
            with np.load(table) as z:
                s_m = np.asarray(z['s_m'], dtype=float)
                v_kmh = np.asarray(z['v_mps'], dtype=float) * 3.6
            # 口径同源：表必须由同一 v_max 生成（否则 env 加载期会直接报错，此处提前拦）
            meta_path = table.with_name('ref_speed_meta.json')
            if not meta_path.is_file():
                fails.append(f'ref 表缺 {meta_path.name}，无法校验口径（env 加载期会拒绝）')
            else:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                src_vmax = meta.get('clamp_upper_mps')
                if src_vmax is None:
                    fails.append(f'{meta_path.name} 缺 clamp_upper_mps 字段')
                elif abs(float(src_vmax) * 3.6 - v_max_kmh) > 1e-6:
                    fails.append(f'ref 表由 v_max={float(src_vmax) * 3.6:.1f} km/h 生成，'
                                 f'与配置 {v_max_kmh:.1f} 不一致 ⇒ 须重生成')
            v_ref = float(np.interp(float(start_m), s_m, v_kmh))
            diff = v_ref - init_kmh
            print(f'  [ref 表] 起点 {start_m:.0f} m → v_ref={v_ref:.1f} km/h | '
                  f'与 init 差 {diff:+.1f} km/h（容差 ±{REF_SPEED_TOL_KMH:.0f}）')
            if abs(diff) > REF_SPEED_TOL_KMH:
                fails.append(f'ref 表在起点处 {v_ref:.1f} km/h 与初速 {init_kmh:.1f} 相差 '
                             f'{abs(diff):.1f} km/h（> {REF_SPEED_TOL_KMH:.0f}）⇒ 表与口径不同源，须重生成')
        else:
            print(f'  [ref 表] 缺失：{table_rel}')
    else:
        print('  [ref 表] 未配置 start_randomization 或 speed_ref_table，跳过')

    if fails:
        print('\n[FAIL]')
        for f in fails:
            print(f'  - {f}')
        return 1
    print('\n[PASS] 起点口径链一致')
    return 0


if __name__ == '__main__':
    sys.exit(main())
