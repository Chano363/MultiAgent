"""
线路坡度剖面建模验证测试（P1.5 第12条，长大下坡场景）。

验证目标：
- GradeProfile 按位置查询坡度正确
- 3 种预置剖面（樊运新：长大下坡/缓坡变陡坡/V型坡）合理
- 列车在变坡剖面上运行时，每节车坡度随位置实时更新
- 长大下坡场景下环境能跑通（循环制动场景前置）
"""

import os
import sys

import pytest
import numpy as np


from src.train_dynamics.grade_profile import (
    GradeProfile, GradeSegment,
    profile_long_downhill, profile_gradual_to_steep, profile_v_shape, PROFILES,
)
from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist
from src.train_dynamics.train import TrainDynamics


# ---------------------------------------------------------------------------
# 1. 坡度剖面查询
def test_grade_at_segment_boundaries():
    """坡度查询在段边界处正确切换。"""
    profile = GradeProfile(segments=[
        GradeSegment(0.0, -2.0),
        GradeSegment(500.0, -10.2),
        GradeSegment(3000.0, -2.0),
    ])
    assert profile.grade_at(0.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(499.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(500.0) == pytest.approx(-10.2 / 1000.0)
    assert profile.grade_at(2999.0) == pytest.approx(-10.2 / 1000.0)
    assert profile.grade_at(3000.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(5000.0) == pytest.approx(-2.0 / 1000.0)


def test_grade_for_positions_batch():
    """批量查询多节车坡度。"""
    profile = GradeProfile(segments=[
        GradeSegment(0.0, -2.0),
        GradeSegment(500.0, -10.2),
    ])
    pos = np.array([0.0, 300.0, 600.0, 1000.0])
    grades = profile.grades_for_positions(pos)
    assert grades[0] == pytest.approx(-2.0 / 1000.0)
    assert grades[1] == pytest.approx(-2.0 / 1000.0)
    assert grades[2] == pytest.approx(-10.2 / 1000.0)
    assert grades[3] == pytest.approx(-10.2 / 1000.0)


def test_empty_profile_zero_grade():
    """空剖面返回 0 坡度。"""
    profile = GradeProfile()
    assert profile.grade_at(100.0) == 0.0


# ---------------------------------------------------------------------------
# 2. 3 种预置剖面（樊运新）
def test_three_preset_profiles_exist():
    """3 种预置剖面存在且含长大下坡段。"""
    p_a = profile_long_downhill()
    p_b = profile_gradual_to_steep()
    p_c = profile_v_shape()
    assert len(p_a.segments) >= 2
    assert len(p_b.segments) >= 2
    assert len(p_c.segments) >= 2
    # 长大下坡段坡度应 <= -5‰（陡下坡）
    has_steep = any(s.grade_permille <= -5.0 for s in p_a.segments)
    assert has_steep, "长大下坡剖面应含陡下坡段(<=-5‰)"


def test_v_shape_has_large_grade_difference():
    """V 型坡坡度差应较大（~10.5‰）。"""
    p_c = profile_v_shape()
    grades = [s.grade_permille for s in p_c.segments]
    grade_diff = max(grades) - min(grades)
    assert grade_diff >= 10.0, f"V型坡坡度差应>=10‰，实际{grade_diff}"


# ---------------------------------------------------------------------------
# 3. 列车在变坡剖面上运行时坡度实时更新
def test_grade_updates_with_position():
    """列车运行时，每节车坡度随位置实时更新。"""
    consist = TrainConsist([LocomotiveParams()] + [VehicleParams() for _ in range(3)])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(20.0)
    td.set_grade_profile(profile_long_downhill())
    # 初始位置在 -2‰ 段
    g0 = td.grade.copy()
    assert all(abs(g - (-2.0 / 1000.0)) < 1e-6 for g in g0)
    # 跑一段时间让列车进入 -10.2‰ 段（500m 后）
    for _ in range(500):  # 50s @ 20m/s = 1000m
        td.step_vehicles(np.zeros(4), np.zeros(4))
    g1 = td.grade.copy()
    # 至少部分车应进入 -10.2‰ 段
    assert any(abs(g - (-10.2 / 1000.0)) < 1e-6 for g in g1), \
        f"列车进入长大下坡段后坡度应更新，实际{g1}"


def test_downhill_accelerates_train():
    """长大下坡（-10.2‰段）应使列车加速（重力分量助力大于阻力）。"""
    consist = TrainConsist([LocomotiveParams()] + [VehicleParams() for _ in range(3)])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(15.0)
    td.set_grade_profile(profile_long_downhill())
    # 把列车放到 -10.2‰ 陡坡段（起点位置 500m 之后）
    td.pos = td.pos + 600.0
    td._update_grade_from_profile()
    # 确认当前在陡坡段
    assert all(abs(g - (-10.2 / 1000.0)) < 1e-6 for g in td.grade)
    v0 = td.vel.mean()
    # 在长大下坡段滑行（无牵引无制动）
    for _ in range(200):  # 20s
        td.step_vehicles(np.zeros(4), np.zeros(4))
    v1 = td.vel.mean()
    assert v1 > v0, f"长大下坡(-10.2‰)应使列车加速: v0={v0}, v1={v1}"


# ---------------------------------------------------------------------------
# 4. 环境集成：长大下坡场景能跑通
def test_env_with_grade_profile_runs():
    """环境配置长大下坡剖面能跑通（循环制动场景前置）。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'num_vehicles': 4,
        'grade_profile': 'long_downhill',
        'max_steps': 100,
    })
    obs, _ = env.reset()
    for _ in range(100):
        obs, r, t, tr, info = env.step(np.zeros(4))
        if t or tr:
            break
    assert info.get('speed') is not None


def test_env_invalid_profile_raises():
    """未知坡度剖面名应报错。"""
    from src.environments.train_env import TrainFormationEnv
    with pytest.raises(ValueError, match="未知坡度剖面"):
        TrainFormationEnv({'grade_profile': 'nonexistent'})


# ---------------------------------------------------------------------------
# 5. 万吨级 1+0 编组（P1.5 第13条，论文研究对象）
def test_10kt_consist_preset():
    """万吨级 1+0 编组预设：1 机 + 100 货，总重约 10188 t。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({'consist_preset': '10kt_1plus0', 'max_steps': 10})
    assert env.num_vehicles == 101  # 1 机 + 100 货
    total_mass = sum(v.mass_t for v in env.dynamics.consist.vehicles)
    assert 9500 <= total_mass <= 11000, f"万吨级总重应≈10000t，实际{total_mass}t"


def test_10kt_runs_with_downhill():
    """万吨级编组在长大下坡剖面下能跑通（论文场景）。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 50,
    })
    env.reset(options={'speed': 20.0})
    for _ in range(50):
        obs, r, t, tr, info = env.step(np.full(101, -0.3))
        if t or tr:
            break
    assert info['speed'] > 0
    # 万吨级在制动下车钩力应合理（不一定超限）
    assert info['coupler_force_peak'] >= 0


# ---------------------------------------------------------------------------
# 6. 【ADR-060 线路数据全量入模】分段限速 / 曲线半径表 + xlsx 重新读取比对
_K0_KM = 15.9  # 宁武西→北大牛剖面重基点（K15.9 = 0 m）
try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

from pathlib import Path as _Path
_XLSX_PATH = (_Path(__file__).resolve().parents[1]
              / 'reference' / 'simulation' / 'data_line'
              / '朔黄铁路_完整线路信息表_表3表4补充版.xlsx')
_XLSX_AVAILABLE = _HAS_OPENPYXL and _XLSX_PATH.exists()


def _read_unified_line_rows():
    """读「统一线路表」K15.9–65.5 段行（header=第2行，数据从第3行起）。"""
    wb = openpyxl.load_workbook(str(_XLSX_PATH), data_only=True, read_only=True)
    ws = wb['统一线路表']
    hdr = [c.value for c in ws[2]]
    idx = {}
    for name in ('公里标', '限速', '曲线状态', '曲线半径', '曲线起点', '曲线终点'):
        if name in hdr:
            idx[name] = hdr.index(name)
        else:
            matches = [h for h in hdr if h is not None and str(h).startswith(name)]
            assert len(matches) == 1, f'{name}: {matches}'
            idx[name] = hdr.index(matches[0])
    rows = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        km = r[idx['公里标']]
        if km is None or not (_K0_KM - 1e-9 <= float(km) <= 65.5 + 1e-9):
            continue
        rows.append(r)
    wb.close()
    return rows, idx


@pytest.mark.skipif(not _XLSX_AVAILABLE, reason='openpyxl 或线路 xlsx 源数据不可用')
def test_adr060_limit_table_matches_xlsx():
    """内置限速段表与 xlsx 逐行比对（0.1km 行全量），并校验关键点。"""
    from src.train_dynamics.grade_profile import (
        PROFILES, SHUOZHOU_49KM_LIMIT_SEGMENTS)
    profile = PROFILES['shuozhou_ningwuxi_beidaniu_49km']()
    rows, idx = _read_unified_line_rows()
    assert len(rows) > 400
    # 逐行比对：限速列与 limit_at(相对里程) 完全一致
    for r in rows:
        km = float(r[idx['公里标']])
        lim = r[idx['限速']]
        if lim is None:
            continue
        rel_m = (km - _K0_KM) * 1000.0
        assert profile.limit_at(rel_m) == pytest.approx(float(lim)), \
            f'K{km} 限速不符: xlsx={lim}, limit_at={profile.limit_at(rel_m)}'
    # 关键点：限速 70 段起终点（K15.9–20.15 与 K39.85–41.35）
    limits = [seg.limit_kmh for seg in SHUOZHOU_49KM_LIMIT_SEGMENTS]
    assert limits == [70.0, 75.0, 70.0, 75.0]
    assert SHUOZHOU_49KM_LIMIT_SEGMENTS[0].start_m == pytest.approx(0.0)
    assert SHUOZHOU_49KM_LIMIT_SEGMENTS[1].start_m == pytest.approx(4250.0)
    assert SHUOZHOU_49KM_LIMIT_SEGMENTS[2].start_m == pytest.approx(23950.0)
    assert SHUOZHOU_49KM_LIMIT_SEGMENTS[3].start_m == pytest.approx(25450.0)
    # 无覆盖返回语义：有表时全程命中（首段之前沿用首段，与 grade_at 同语义）
    assert profile.limit_at(-1.0) == pytest.approx(70.0)
    assert profile.limit_at(49599.0) == pytest.approx(75.0)


@pytest.mark.skipif(not _XLSX_AVAILABLE, reason='openpyxl 或线路 xlsx 源数据不可用')
def test_adr060_curve_table_matches_xlsx():
    """内置曲线表与 xlsx 去重比对（32 处），并校验最小半径 400 与中点查询。"""
    from src.train_dynamics.grade_profile import (
        PROFILES, SHUOZHOU_49KM_CURVE_SEGMENTS)
    profile = PROFILES['shuozhou_ningwuxi_beidaniu_49km']()
    rows, idx = _read_unified_line_rows()
    # 去重提取（0.1km 行重复同一曲线）
    xlsx_curves = []
    seen = set()
    for r in rows:
        if r[idx['曲线状态']] != '曲线':
            continue
        cs, ce, cr = r[idx['曲线起点']], r[idx['曲线终点']], r[idx['曲线半径']]
        assert cs is not None and ce is not None and cr is not None
        key = (round(float(cs), 3), round(float(ce), 3), float(cr))
        if key in seen:
            continue
        seen.add(key)
        xlsx_curves.append(key)
    assert len(SHUOZHOU_49KM_CURVE_SEGMENTS) == len(xlsx_curves) == 32
    for seg, (cs_km, ce_km, cr_val) in zip(SHUOZHOU_49KM_CURVE_SEGMENTS, xlsx_curves):
        assert seg.start_m == pytest.approx((cs_km - _K0_KM) * 1000.0, abs=0.5)
        assert seg.end_m == pytest.approx((ce_km - _K0_KM) * 1000.0, abs=0.5)
        assert seg.radius_m == pytest.approx(cr_val)
    # 关键点：最小半径 400
    min_r = min(seg.radius_m for seg in SHUOZHOU_49KM_CURVE_SEGMENTS)
    assert min_r == pytest.approx(400.0)
    # 每条曲线中点查表 = 该曲线半径；批量接口与单点接口一致
    mids = np.array([0.5 * (seg.start_m + seg.end_m)
                     for seg in SHUOZHOU_49KM_CURVE_SEGMENTS])
    for m, seg in zip(mids, SHUOZHOU_49KM_CURVE_SEGMENTS):
        assert profile.curve_radius_at(m) == pytest.approx(seg.radius_m)
    batch = profile.curve_radii_for_positions(mids)
    assert np.allclose(batch, [seg.radius_m for seg in SHUOZHOU_49KM_CURVE_SEGMENTS])
    # 直线点（K30 = 14100 m，首曲线 980 前 / 3350 后无曲线）→ None
    assert profile.curve_radius_at(14100.0) is None


def test_adr060_limit_curve_interface_semantics():
    """接口语义：有表命中 / 直线 None / 无表（恒坡）恒 None（零回归前提）。"""
    profile = PROFILES['shuozhou_ningwuxi_beidaniu_49km']()
    assert profile.limit_at(1000.0) == pytest.approx(70.0)     # K16.9（70 段）
    assert profile.limit_at(20000.0) == pytest.approx(75.0)    # K35.9（75 段）
    assert profile.limit_at(24500.0) == pytest.approx(70.0)    # K40.4（第二 70 段）
    assert profile.curve_radius_at(1200.0) == pytest.approx(400.0)   # K17.1 曲线
    assert profile.curve_radius_at(10000.0) is None                  # 直线
    # 恒坡（无表）剖面：limit_at / curve_radius_at 恒 None
    bare = GradeProfile(segments=[GradeSegment(0.0, -5.0)])
    assert bare.limit_at(100.0) is None
    assert bare.curve_radius_at(100.0) is None
    assert bare.curve_radii_for_positions(np.array([0.0, 100.0])).tolist() == [np.inf, np.inf]


def test_adr060_curve_resistance_force():
    """曲线阻力 w_r=600/(R−55) N/kN：R=400 段量值正确、直线恒 0（零回归）。"""
    from src.train_dynamics.resistance import G
    consist = TrainConsist([LocomotiveParams()] + [VehicleParams() for _ in range(3)])
    profile = PROFILES['shuozhou_ningwuxi_beidaniu_49km']()
    td = TrainDynamics(consist, dt=0.1)
    td.set_grade_profile(profile)
    # 全列置于 R=400 曲线（K17.1 = 1200 m），以 20 m/s 正向运行
    td.pos = np.full(4, 1200.0)
    td.vel = np.full(4, 20.0)
    td._update_grade_from_profile()
    assert np.all(td.curve_radius == pytest.approx(400.0))
    f_curve = td._curve_resistance_forces()
    w_r = 600.0 / (400.0 - 55.0)          # ≈1.739 N/kN
    expected = np.array([v.mass_t * 1000.0 * G * w_r / 1000.0
                         for v in consist.vehicles])
    assert np.allclose(f_curve, expected)
    assert np.all(f_curve > 0)            # 正向运行 → 阻力为正（阻碍项，net 取负）
    # net_forces 合成：与去掉曲线项相比应更小（额外减速）
    net_with = td.net_forces(0.0, 0.0)
    td2_curve_backup = td.curve_radius.copy()
    td.curve_radius = np.full(4, np.inf)
    net_without = td.net_forces(0.0, 0.0)
    td.curve_radius = td2_curve_backup
    assert np.all(net_with < net_without)
    # 直线（恒坡无表）→ 曲线阻力恒 0
    td_bare = TrainDynamics(consist, dt=0.1)
    td_bare.set_grade_profile(GradeProfile(segments=[GradeSegment(0.0, -5.0)]))
    td_bare.vel = np.full(4, 20.0)
    td_bare._update_grade_from_profile()
    assert np.all(td_bare.curve_radius == np.inf)
    assert np.all(td_bare._curve_resistance_forces() == 0.0)


def test_adr060_env_linkage_zero_regression_on_bare_profile():
    """无表剖面 env 联动自动关闭（lookup 调用返回 None、安全层零回归）。

    lookup 为动态代理（恒非 None）：联动以"调用返回 None"判定，保证
    set_grade_profile 运行时换剖面（如 diagnose 的恒坡覆盖）后联动正确关闭。
    """
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'num_vehicles': 4,
        'grade_profile': 'long_downhill',
        'max_steps': 10,
    })
    assert env.line_limit_lookup_kmh(100.0) is None
    assert env.safety.speed_limit_lookup(100.0) is None
    obs, _ = env.reset()
    obs, r, t, tr, info = env.step(np.zeros(4))
    assert info.get('speed') is not None


@pytest.mark.skipif(not _XLSX_AVAILABLE, reason='openpyxl 或线路 xlsx 源数据不可用')
def test_adr060_env_linkage_active_on_shuozhou():
    """shuozhou 49km 剖面 env：限速联动激活，70 段查表返回 70 km/h。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'num_vehicles': 4,
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'max_steps': 10,
    })
    assert env.line_limit_lookup_kmh is not None
    assert env.line_limit_lookup_kmh(1000.0) == pytest.approx(70.0)
    assert env.line_limit_lookup_kmh(20000.0) == pytest.approx(75.0)
    assert env.safety.speed_limit_lookup is not None
    obs, _ = env.reset()
    obs, r, t, tr, info = env.step(np.zeros(4))
    assert info.get('speed') is not None
