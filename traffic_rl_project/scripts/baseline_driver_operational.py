"""表3 司机操纵基线（ADR-060）：按朔黄实录 (制动开始km, 缓解km, 减压50kPa) 序列
在 shuozhou 49.6km 剖面上跑 1+108 单列，里程锚定触发循环制动。

目的（ADR-060 任务 D）：
  用实录司机操纵序列（表3_制动缓解位置）复现基线运行，产出
  速度轨迹 vs xlsx「实际速度」列的对照（RMSE / 最大偏差），
  作为物理入模（限速逐段联动 + 曲线阻力）后的运营一致性参照。

动作通道（TrainFormationEnv decompose）：
  - 每步动作 (1, 2) = [ed_frac, ab_frac]
  - 头车里程 ∈ [制动开始km, 缓解km) → ab_frac = -0.05
    （notch_from_throttle 哨兵带 (0, 0.1) → AirBrakeNotch.CYCLIC = 50 kPa 循环档，
      与 cyclic_notch_50 / 表3 减压量 50 kPa 口径一致）
  - 区间外 → [0.0, 0.0]（惰行 + 空气制动缓解，表3 无 ED 记录 ⇒ 电制动全程 0）
  - 里程锚定 = 直接按表3 实录公里标（相对里程 = (km − 15.9) × 1000 m），
    不叠加 ab_min_refill_s（充风最小间隔是规则层保守约束，实录序列本身就是
    发生过的操纵，基线忠实回放实录）。

env 配置（单列）：与 configs/experiments/formation_ed_ab_3train_1plus108.yaml
env_cfg 的单列参数同款（10kt_1plus108 / shuozhou_ningwuxi_beidaniu_49km /
v_max 80 / coupler 1000 kN / cyclic_notch_50 等逐键对齐，BC 同款编组口径）。

落盘（时间戳归档，不覆盖）：
  outputs/sim_validation/phys_validation/driver_baseline_<tag>_<时间戳>/
    result.json              权威 metadata（build_metadata）+ 指标 + 每循环明细
    actual_speed_profile.csv xlsx「实际速度」列（同段全点）
    sim_vs_actual.csv        仿真轨迹（头车里程-速度）+ 插值对齐的实际速度

用法（WSL，traffic_rl 环境）：
    python scripts/baseline_driver_operational.py --steps 3000 --out_tag smoke
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

XLSX_PATH = (ROOT / 'reference' / 'simulation' / 'data_line'
             / '朔黄铁路_完整线路信息表_表3表4补充版.xlsx')
K0_KM = 15.9          # 剖面重基点（宁武西，K15.9 = 0 m）
K1_KM = 65.5          # 剖面终点（北大牛）
CYCLIC_AB_SENTINEL = -0.05   # notch_from_throttle → CYCLIC（50 kPa 循环档）
ZONE_KEYWORDS = ('宁武西', '龙宫', '北大牛')


def load_table3_cycles(kpa: int = 50):
    """读表3_制动缓解位置，返回段内相关循环列表（相对里程 m）。"""
    import openpyxl
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=True, read_only=True)
    ws = wb['表3_制动缓解位置']
    hdr = [c.value for c in ws[2]]
    keys = ['制动循环编号', '制动开始km', '缓解位置km', '减压量kPa',
            '制动触发速度km/h', '所属区间']
    idx = {}
    for name in keys:
        if name in hdr:
            idx[name] = hdr.index(name)
        else:
            matches = [h for h in hdr
                       if h is not None and str(h).replace(' ', '').startswith(name)]
            assert len(matches) == 1, f'{name}: {matches}'
            idx[name] = hdr.index(matches[0])
    cycles = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        zone = r[idx['所属区间']]
        if zone is None:
            continue
        zs = str(zone)
        if not any(k in zs for k in ZONE_KEYWORDS):
            continue
        b_km, r_km = r[idx['制动开始km']], r[idx['缓解位置km']]
        if b_km is None or r_km is None:
            continue
        b_km, r_km = float(b_km), float(r_km)
        # 段内相关：制动开始落在剖面范围内（循环 6/7 起点在段外，剔除）
        if not (K0_KM - 1e-9 <= b_km <= K1_KM + 1e-9):
            continue
        kpa_v = r[idx['减压量kPa']]
        cycles.append({
            'no': r[idx['制动循环编号']],
            'zone': zs,
            'brake_km': b_km,
            'release_km': r_km,
            'brake_rel_m': (b_km - K0_KM) * 1000.0,
            'release_rel_m': (r_km - K0_KM) * 1000.0,
            'kpa': None if kpa_v is None else int(kpa_v),
            'v_trigger_kmh': r[idx['制动触发速度km/h']],
        })
    wb.close()
    return cycles


def load_actual_speed():
    """读统一线路表「实际速度」列（段内全点，按公里标升序）。"""
    import openpyxl
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=True, read_only=True)
    ws = wb['统一线路表']
    hdr = [c.value for c in ws[2]]
    idx = {}
    for name in ('公里标', '实际速度'):
        if name in hdr:
            idx[name] = hdr.index(name)
        else:
            matches = [h for h in hdr if h is not None and str(h).startswith(name)]
            assert len(matches) == 1, f'{name}: {matches}'
            idx[name] = hdr.index(matches[0])
    pts = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        km = r[idx['公里标']]
        v = r[idx['实际速度']]
        if km is None or v is None:
            continue
        km = float(km)
        if K0_KM - 1e-9 <= km <= K1_KM + 1e-9:
            pts.append((km, float(v)))
    wb.close()
    pts.sort(key=lambda t: t[0])
    return pts


def make_env(init_speed_kmh: float):
    """构造单列 env（配置与 formation_ed_ab_3train_1plus108.yaml env_cfg 单列参数同款）。"""
    from src.environments.train_env import TrainFormationEnv
    cfg = dict(
        consist_preset='10kt_1plus108',            # YAML env_cfg.consist_preset（1 机车 + 108 货车）
        grade_profile='shuozhou_ningwuxi_beidaniu_49km',   # YAML env_cfg.grade_profile
        v_max=22.22222222222222,                   # 80 km/h（YAML env_cfg.v_max）
        v_min=11.111,                              # 40 km/h
        target_gap=100.0,
        route_end_m=49600,                         # 剖面真实末端（YAML env_cfg.route_end_m）
        use_coupler_constraint=True,
        coupler_force_limit_n=1000000.0,           # 1000 kN 验收（ADR-040）
        coupler_force_limit_emergency_n=2250000.0, # 仅安全层紧急保护（ADR-036）
        coupler_override='min_brake',
        decompose='loco_ed_ab',                    # 机车级 ED/AB（单列 1 台机车）
        cyclic_notch_50=True,                      # 50 kPa 循环档（表3 口径）
        max_steps=31500,
    )
    env = TrainFormationEnv(cfg)
    env.reset(options={'speed': init_speed_kmh / 3.6})
    return env


def main():
    p = argparse.ArgumentParser(
        description='表3 司机操纵基线：里程锚定 50kPa 循环制动回放（单列 1+108）')
    p.add_argument('--steps', type=int, default=31500,
                   help='步数上限（dt=0.1s；正式=全程 31500，冒烟=3000）')
    p.add_argument('--init_speed_kmh', type=float, default=70.0,
                   help='初速 km/h（与 YAML init_speed_kmh / 基线归档 v0≈69.2 对齐）')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--out_tag', default='shuozhou49',
                   help='归档语义前缀（自动加时间戳）')
    args = p.parse_args()

    cycles = load_table3_cycles()
    actual = load_actual_speed()
    print(f'[表3] 段内相关循环 {len(cycles)} 个:')
    for c in cycles:
        print(f"  循环{c['no']} {c['zone']}: K{c['brake_km']}→K{c['release_km']} "
              f"{c['kpa']}kPa 触发v={c['v_trigger_kmh']}")
    print(f'[实际速度] 段内点数 {len(actual)}')

    env = make_env(args.init_speed_kmh)

    # ---------------- 主循环（里程锚定驱动） ----------------
    rows = []            # 每步记录
    cycle_events = []    # 每循环明细
    active_cycle = None  # 当前所处循环 dict
    peak_coupler_kn = 0.0
    sum_coupler_kn, n_coupler_steps, n_over_limit = 0.0, 0, 0
    peak_speed_kmh = 0.0

    for step_i in range(args.steps):
        head_m = float(env.dynamics.pos[0])
        head_km = K0_KM + head_m / 1000.0
        v_head_kmh = float(env.dynamics.vel[0]) * 3.6

        # 里程锚定：头车进入 [制动开始, 缓解) → CYCLIC(50kPa)；否则惰行+缓解
        ab_frac = 0.0
        cur = None
        for c in cycles:
            if c['brake_rel_m'] <= head_m < c['release_rel_m']:
                cur = c
                break
        if cur is not None:
            ab_frac = CYCLIC_AB_SENTINEL
            if active_cycle is None or active_cycle['no'] != cur['no']:
                active_cycle = {**cur, 'enter_step': step_i, 'v_enter_kmh': v_head_kmh,
                                'v_max_in_kmh': v_head_kmh, 'v_min_in_kmh': v_head_kmh}
                cycle_events.append(active_cycle)
        elif active_cycle is not None:
            # 离开循环（缓解锚定到达）
            active_cycle['release_step'] = step_i
            active_cycle['v_release_kmh'] = v_head_kmh
            active_cycle = None

        obs, reward, term, trunc, info = env.step(np.array([[0.0, ab_frac]], dtype=float))

        cpl_peak = float(info.get('coupler_force_peak', 0.0)) / 1e3
        peak_coupler_kn = max(peak_coupler_kn, cpl_peak)
        sum_coupler_kn += cpl_peak
        n_coupler_steps += 1
        if cpl_peak > 1000.0:
            n_over_limit += 1
        peak_speed_kmh = max(peak_speed_kmh, v_head_kmh)
        if active_cycle is not None:
            active_cycle['v_max_in_kmh'] = max(active_cycle['v_max_in_kmh'], v_head_kmh)
            active_cycle['v_min_in_kmh'] = min(active_cycle['v_min_in_kmh'], v_head_kmh)
            active_cycle['coupler_peak_in_kN'] = max(
                active_cycle.get('coupler_peak_in_kN', 0.0), cpl_peak)

        rows.append((step_i, env.dynamics.time, head_km, v_head_kmh,
                     float(np.mean(env.dynamics.vel)) * 3.6, cpl_peak,
                     1 if cur is not None else 0,
                     cur['no'] if cur is not None else ''))

        if term or trunc:
            print(f'[终止] step={step_i} t={env.dynamics.time:.0f}s head=K{head_km:.3f} '
                  f'terminated={term} truncated={trunc}')
            break

    # ---------------- 归档 ----------------
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = (ROOT / 'outputs' / 'sim_validation' / 'phys_validation'
              / f'driver_baseline_{args.out_tag}_{stamp}')
    outdir.mkdir(parents=True, exist_ok=True)

    # 实际速度剖面（同段全点）
    with open(outdir / 'actual_speed_profile.csv', 'w', newline='',
              encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['km', 'actual_speed_kmh'])
        for km, v in actual:
            w.writerow([f'{km:.3f}', f'{v:.2f}'])

    # 仿真轨迹 + 插值对齐实际速度
    a_km = np.array([t[0] for t in actual])
    a_v = np.array([t[1] for t in actual])
    s_km = np.array([r[2] for r in rows])
    s_v = np.array([r[3] for r in rows])
    a_on_s = np.interp(s_km, a_km, a_v)
    dev = s_v - a_on_s
    rmse = float(np.sqrt(np.mean(dev ** 2)))
    max_dev = float(np.max(np.abs(dev)))
    with open(outdir / 'sim_vs_actual.csv', 'w', newline='',
              encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['step', 't_s', 'head_km', 'sim_speed_kmh', 'v_mean_kmh',
                    'coupler_peak_kN', 'in_cycle', 'cycle_no',
                    'actual_speed_at_head_kmh', 'speed_dev_kmh'])
        for r, av, dv in zip(rows, a_on_s, dev):
            w.writerow([r[0], f'{r[1]:.1f}', f'{r[2]:.4f}', f'{r[3]:.3f}',
                        f'{r[4]:.3f}', f'{r[5]:.1f}', r[6], r[7],
                        f'{av:.2f}', f'{dv:.3f}'])

    over_ratio = n_over_limit / max(n_coupler_steps, 1)
    metrics = {
        'steps_run': len(rows),
        'sim_time_s': float(rows[-1][1]) if rows else 0.0,
        'head_km_end': float(rows[-1][2]) if rows else None,
        'peak_coupler_kN': peak_coupler_kn,
        'mean_coupler_peak_kN': sum_coupler_kn / max(n_coupler_steps, 1),
        'coupler_over_limit_ratio': over_ratio,   # 每步全列峰值>1000kN 的步占比
        'peak_speed_kmh': peak_speed_kmh,
        'fit_vs_actual': {'rmse_kmh': rmse, 'max_dev_kmh': max_dev,
                          'coverage_km': [float(s_km[0]), float(s_km[-1])] if len(s_km) else None},
        'cycles': [{k: v for k, v in c.items() if k != 'zone'} for c in cycle_events],
    }

    from src.metadata import build_metadata
    meta = build_metadata(
        project_root=str(ROOT), case='official',
        world_cfg={'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
                   'consist_preset': '10kt_1plus108',
                   'controller': 'table3_driver_replay(CYCLIC50kPa km-anchored)'},
        seed=args.seed, entry=__file__,
        extra={'baseline': 'table3_driver_operational', 'args': vars(args),
               'metrics': metrics, 'table3_cycles': cycles})
    (outdir / 'result.json').write_text(
        json.dumps({'metadata': meta, 'metrics': metrics},
                   ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')

    print(f'[归档] {outdir}')
    print(f"  峰值车钩 {peak_coupler_kn:.1f} kN / 均值 {metrics['mean_coupler_peak_kN']:.1f} kN"
          f" / 超限步占比 {over_ratio:.3%}")
    print(f"  末点 K{metrics['head_km_end']:.3f}  峰值速度 {peak_speed_kmh:.1f} km/h")
    print(f"  贴合度 RMSE={rmse:.2f} km/h  最大偏差={max_dev:.2f} km/h")


if __name__ == '__main__':
    main()
