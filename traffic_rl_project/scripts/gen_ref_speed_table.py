"""从规则基线全程归档派生"里程 → 参考速度"表（v7 奖励跟踪项的数据源）。

用法（WSL traffic_rl）：
    python scripts/gen_ref_speed_table.py \
        --npz outputs/sim_validation/phys_validation/fleet3_gap800_strict_production_70kmh_full_20261105/run/trajectory.npz

产出（时间戳归档，不覆盖）：
    outputs/sim_validation/phys_validation/refspeed_baseline_<时间戳>/
        ref_speed_table.npz    # s_m / v_mps（线路**绝对里程**、已排序去重、仅 clamp 上界 ≤ v_max）
        ref_speed_meta.json    # 溯源：源归档、点数、里程范围、clamp 点数、速度统计

为什么是"领航列头位 → 领航列头速"：
    奖励跟踪项只作用于领航列（ti==0），跟随列走 rel_anchor 相对镜像，故参考表只需
    领航列自身的 (里程, 速度) 关系；这等价于"单列规则基线在同一条线路位置的速度"。

与仿真无关：本脚本只读归档、零仿真，可反复重跑（数据与绘图分离纪律）。
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

V_MIN_MPS = 40.0 / 3.6   # 仅用于统计"基线有多少步低于下缘"，**不作 clamp 下界**
V_MAX_MPS = 80.0 / 3.6


def build_table(npz_path: Path, train_index: int = 0):
    with np.load(npz_path) as z:
        pos = np.asarray(z['vehicle_positions_m'], dtype=np.float64)  # (T, n_train, n_veh)
        spd = np.asarray(z['head_speed'], dtype=np.float64)           # (T, n_train)
    s = pos[:, train_index, 0]        # 领航列头车（车头）位置，m
    v = spd[:, train_index]           # 领航列头车速度，m/s

    order = np.argsort(s, kind='stable')
    s, v = s[order], v[order]
    keep = np.concatenate([[True], np.diff(s) > 1e-6])
    s, v = s[keep], v[keep]
    # 【2026-11-08 修订】保留**线路绝对里程**（不归零）。
    # 起因：band 值按"已行驶里程"查表需要 env 侧记 `_ref_origin_m`，一旦起点前移
    # （修队尾负里程）就必须同步改原点；且同一张表无法同时服务两种起点。
    # 改绝对里程后，训练/评估只要"编队起点 ≥ 队尾所需里程"，查表即与线路位置一一对应，
    # 起点怎么挪都不用重建表。表覆盖 [4 291.9, 49 358.2] m（= 基线实际驶过区间），
    # 越界由 np.interp 自动 clamp 到首/末点。
    s_origin_m = float(s[0])

    n_clamped = int(np.count_nonzero(v > V_MAX_MPS))
    n_below_vmin = int(np.count_nonzero(v < V_MIN_MPS))
    v = np.minimum(v, V_MAX_MPS)
    stats = {
        'n_points': int(s.size),
        's_basis': 'absolute_profile_m',
        's_origin_m_in_source': s_origin_m,
        'pos_min_m': float(s[0]),
        'pos_max_m': float(s[-1]),
        'speed_min_kmh': float(v.min() * 3.6),
        'speed_max_kmh': float(v.max() * 3.6),
        'speed_mean_kmh': float(v.mean() * 3.6),
        'n_clamped_above_vmax': n_clamped,
        'frac_below_vmin': float(n_below_vmin / max(s.size, 1)),
        'n_dropped_duplicate': int(len(pos) - s.size),
    }
    return s, v, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--npz', required=True, help='基线归档 trajectory.npz 路径')
    ap.add_argument('--train-index', type=int, default=0, help='取哪一列作参考（默认 0=领航列）')
    ap.add_argument('--out-root', default='outputs/sim_validation/phys_validation')
    args = ap.parse_args()

    npz_path = Path(args.npz)
    if not npz_path.is_file():
        raise FileNotFoundError(npz_path)

    s, v, stats = build_table(npz_path, args.train_index)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(args.out_root) / f'refspeed_baseline_{stamp}'
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez(out_dir / 'ref_speed_table.npz', s_m=s, v_mps=v)
    meta = {
        'created_at': stamp,
        'source_npz': str(npz_path),
        'train_index': args.train_index,
        'source_columns': 'vehicle_positions_m[:,train,0] + head_speed[:,train]',
        'clamp_upper_mps': V_MAX_MPS,
        'train_dt_s': 0.1,
        **stats,
    }
    (out_dir / 'ref_speed_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'[ref-speed] 归档目录: {out_dir}')
    print(f'[ref-speed] 点数 {stats["n_points"]}（丢重复 {stats["n_dropped_duplicate"]}，'
          f'超 v_max 被 clamp {stats["n_clamped_above_vmax"]}，'
          f'低于 v_min 占比 {stats["frac_below_vmin"]:.1%}）')
    print(f'[ref-speed] 里程 {stats["pos_min_m"]:.1f}–{stats["pos_max_m"]:.1f} m')
    print(f'[ref-speed] 参考速度 {stats["speed_min_kmh"]:.2f}–{stats["speed_max_kmh"]:.2f} km/h '
          f'（均值 {stats["speed_mean_kmh"]:.2f}）')


if __name__ == '__main__':
    main()
