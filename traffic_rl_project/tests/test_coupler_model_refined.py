"""R0 车钩模型地基改进的文献值验证 + 整段物理曲线自动核查（2026-09-06）。

改进项（于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》，中国铁道科学
46(2):192-202；李蔚2023表1）：
    A 卸载刚度软化 unload_stiffness_ratio=0.4（"阻抗在卸载初期较小"）；
    B Stribeck 速度相关摩擦（式(2)：|v|=0 静摩擦 → |v|≥v_er 动摩擦，线性过渡；
      "MT-2 运动速度越慢，摩擦力越大"）；
    D 循环制动段间衰减（赵紫宁表5-5 C_β）为 official 基线物理；
    E 缓解排气时间常数 exp(-t/τ)（替代线性 release_frac 渐变）。

    【2026-09-07 ADR】原 C 机车 QKX100 弹性胶泥分区（式(3)(4)）已按决策统一回
    MT-2（A 范式，成熟论文"分车型归一对"），本测试随 QKX100 移除删除相关用例。

    【2026-10-11 速度法重建】A/B 已被容嘉欣2025 图4(b) fl/fu 查表 + 速度法
    sign(Δv) 选支取代（装载缓释曲线失真修复，见 coupler.py 模块头与
    DIAGNOSTICS_2026-10.md「诊断-2026-10-11-外部反馈两问」问②）：
    - 摩擦幅值不再随速度大小衰减（Stribeck 幅值调制废止）→ 原
      test_mt2_stribeck_slow_speed_higher_impedance 改写为"分支由方向决定、
      幅值与速度大小无关 + 对齐文献 fl 读点"；
    - 加载/卸载阻抗不再用解析式 F0±F_fric+k·x，改查 fl/fu 表 → 相关断言
      改为对齐数字化读点（±30 kN 读数误差，rel 容差 0.03~0.05）。

文献硬锚点：
    - MT-2：最大阻抗 2270 kN、行程 83 mm、预压力 ~200 kN（于宗泽/李蔚表1）
    - 容嘉欣2025 图4(b)：fl/fu 迟滞曲线数字化读点（40mm: fl≈1182 / fu≈345 kN）
    - 张二田 S3：循环制动峰值车钩力出现在缓解阶段

其余为标定约束，本测试把标定约束固化成回归门禁。
"""

import os
import sys

import numpy as np
import pytest


from src.train_dynamics.coupler import coupler_force, RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N
from src.train_dynamics.params import (
    VehicleParams, LocomotiveParams, CouplerParams, TrainConsist,
)
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch

K_MT2 = 1.89e7
PRELOAD_MT2 = 2.0e5
FRIC_DYN_MT2 = 5.0e5
STROKE = 0.083


def _mt2(**kw):
    base = dict(stiffness=K_MT2, preload_n=PRELOAD_MT2, friction_n=FRIC_DYN_MT2)
    base.update(kw)
    return base


def _lit(x_m: float, branch: str) -> float:
    """按行程查容嘉欣图4(b) 数字化表（牛顿）。branch ∈ {'fl', 'fu'}。"""
    tbl = RONG2025_FL_N if branch == 'fl' else RONG2025_FU_N
    return float(np.interp(x_m, RONG2025_X_M, tbl))


# ---------------------------------------------------------------------------
# 文献锚点：MT-2 加载阻抗
def test_mt2_loading_impedance_at_stroke_2270kn():
    """加载、行程打满：阻抗 ≈ 2270 kN（于宗泽/李蔚表1 = 图4(b) fl(83mm) 锚点）。"""
    kw = _mt2()
    # x_back 取 stroke+gap：x_el = |e|−gap 恰 = 行程 83mm（无刚性限位）
    f = coupler_force(0.0, 0.0, -1.0 + STROKE + 0.01, 1.0, kw['stiffness'], 0.0, 1.0,
                      preload_n=kw['preload_n'], friction_n=kw['friction_n'])
    assert f == pytest.approx(2.27e6, rel=0.03)


def test_mt2_unloading_impedance_smaller_everywhere():
    """【速度法】同行程下卸载阻抗 fu < 加载阻抗 fl（容嘉欣："阻抗在卸载初期较小"）。

    【2026-10-11】行程坐标修正：e = gap + x_mm（原版漏加 gap，x_el 实为 0，
    断言靠 unload 被 clip 到 0 而非真实曲线分离）。现直接断言查表口径：
    fu/fl 比值 = 文献读点比。"""
    kw = _mt2()
    ratios = []
    for x_mm in (10, 20, 40, 60, 80):
        x = 0.01 + x_mm / 1000.0   # e = gap + 行程 → x_el = 行程
        load = coupler_force(0.0, 0.0, -1.0 + x, 1.0, kw['stiffness'], 0.0, 1.0,
                             preload_n=kw['preload_n'], friction_n=kw['friction_n'])
        unload = coupler_force(0.0, 1.0, -1.0 + x, 0.0, kw['stiffness'], 0.0, 1.0,
                               preload_n=kw['preload_n'], friction_n=kw['friction_n'])
        assert unload < load, f"x={x_mm}mm 卸载阻抗未低于加载阻抗"
        # 对齐文献读点（±30 kN 读数误差）。10mm 点额外含符号平滑因子
        # s_e=tanh(e/gap)=tanh(2)=0.964 + 接触渐入 0.993 → 合计 −4.2%（协议效应，
        # 非表读数偏差），故该点容差放宽；20mm 起 s_e≥0.995，用常规容差。
        rel = 0.06 if x_mm == 10 else 0.03
        assert load == pytest.approx(_lit(x_mm / 1000.0, 'fl'), rel=rel)
        assert unload == pytest.approx(_lit(x_mm / 1000.0, 'fu'), rel=max(rel, 0.05))
        ratios.append(unload / max(load, 1.0))
    # 卸载初期（小行程）阻抗最小：fu(10)/fl(10) = 87/332 ≈ 0.26 ≤ 0.5
    assert ratios[0] <= 0.5


def test_mt2_branch_by_dv_sign_speed_magnitude_independent():
    """【2026-10-11 容嘉欣速度法】摩擦幅值**不随速度大小衰减**，仅 sign(Δv) 选支。

    旧 Stribeck 幅值调制（f_slow > f_fast）已废止：其与方向 tanh 相乘造成
    准静态双重削减（0.01 m/s 只剩 19.7%），是装载缓释曲线失真根因。现断言：
    1) 准静态 0.01 m/s 与快速 1 m/s 加载阻抗一致（幅值与速度大小无关）；
    2) 加载支 = 文献 fl(40mm) ≈ 1182 kN（±30 kN 读数误差）；
    3) 换向（卸载支）= 文献 fu(40mm) ≈ 345 kN。"""
    kw = _mt2()
    x = 0.05  # e=0.05 → x_el = 0.04 = 40mm
    f_slow = coupler_force(0.0, 0.0, -1.0 + x, 0.01, kw['stiffness'], 0.0, 1.0,
                           preload_n=kw['preload_n'], friction_n=kw['friction_n'])
    f_fast = coupler_force(0.0, 0.0, -1.0 + x, 1.0, kw['stiffness'], 0.0, 1.0,
                           preload_n=kw['preload_n'], friction_n=kw['friction_n'])
    assert f_slow == pytest.approx(f_fast, rel=0.01)
    assert f_fast == pytest.approx(_lit(0.04, 'fl'), rel=0.03)
    # 换向：v_front>v_back 卸载
    f_unload = coupler_force(0.0, 1.0, -1.0 + x, 0.0, kw['stiffness'], 0.0, 1.0,
                             preload_n=kw['preload_n'], friction_n=kw['friction_n'])
    assert f_unload == pytest.approx(_lit(0.04, 'fu'), rel=0.05)
    assert f_unload < f_fast


def test_mt2_hysteresis_loop_dissipative():
    """整段迟滞环核查：加载→卸载一个循环，⟳ 力·位移积分 > 0（净耗能，无注能）。"""
    kw = _mt2()
    xs = np.linspace(0.011, STROKE, 40)
    # 加载（dv=-0.5，压缩加深）→ 卸载（dv=+0.5）
    f_load = [coupler_force(0.0, 0.0, -1.0 + x, 0.5, kw['stiffness'], 0.0, 1.0,
                            preload_n=kw['preload_n'], friction_n=kw['friction_n'])
              for x in xs]
    # 卸载：v_front>v_back（dv=+0.5，松脱方向）
    f_unload = [coupler_force(0.0, 0.5, -1.0 + x, 0.0, kw['stiffness'], 0.0, 1.0,
                              preload_n=kw['preload_n'], friction_n=kw['friction_n'])
                for x in xs[::-1]][::-1]
    f_load = np.array(f_load)
    f_unload = np.array(f_unload)
    assert np.all(f_load >= f_unload - 1.0), "迟滞环出现交叉（卸载高于加载）"
    # 循环净耗能 = ∮(f_load − f_unload)dx > 0
    energy = np.trapz(f_load - f_unload, xs)
    assert energy > 0.0


def test_default_dispatch_all_mt2():
    """【2026-09-07 ADR】齐次默认全列统一 MT-2（含机车-货车连挂），无 QKX100 分区。
    原 R0-C test_loco_coupler_dispatch_qkx100_mt2 已随 QKX100 移除而改写。"""
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(5)])
    td = TrainDynamics(consist, dt=0.1)
    # 全列逐耦合 max_impulse 均为 MT-2 2270 kN（机车相邻耦合不再用 QKX100 2500）
    assert np.all(td._cp['max_impulse_n'] == pytest.approx(2.27e6))
    # 多次齐次构造逐位一致（无分区、无类型差异）
    consist2 = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(5)])
    td2 = TrainDynamics(consist2, dt=0.1)
    for name, arr in td._cp.items():
        assert np.allclose(arr, td2._cp[name]), f"齐次默认应全列 MT-2 全等: {name}"
    # 纯货车列同样全 MT-2
    consist_f = TrainConsist([VehicleParams() for _ in range(4)])
    td_f = TrainDynamics(consist_f, dt=0.1)
    assert np.all(td_f._cp['max_impulse_n'] == pytest.approx(2.27e6))


# ---------------------------------------------------------------------------
# 两处实现一致性（标量 coupler.py ↔ 向量化 train.py）
def test_vector_matches_scalar_mt2():
    """向量化实现与标量实现在随机状态网格上数值一致（MT-2）。"""
    rng = np.random.default_rng(42)
    params = CouplerParams()
    consist = TrainConsist([VehicleParams() for _ in range(3)])
    td = TrainDynamics(consist, coupler=params, dt=0.1)
    for _ in range(50):
        e = rng.uniform(-0.15, 0.15, size=2)
        dv = rng.uniform(-2.0, 2.0, size=2)
        f_vec = td._coupler_interface_forces_vec(e=e, dv=dv)
        f_sca = np.array([
            coupler_force(
                0.0, 0.0, e[i] - 1.0, -dv[i],
                params.stiffness, 0.0, 1.0,
                coupler_gap=params.coupler_gap_m,
                max_impulse=params.max_impulse_n,
                preload_n=params.preload_n, friction_n=params.friction_n,
                friction_v_eps=params.friction_v_eps,
                stroke_m=params.stroke_m,
                rigid_stiffness_nm=params.rigid_stiffness_nm,
                unload_stiffness_ratio=params.unload_stiffness_ratio,
                friction_static_n=params.friction_static_n,
                friction_v_er=params.friction_v_er,
            ) for i in range(2)])
        # 标量约定：dv = v_front − v_back；此处构造 e=x_back−x_front+1
        # v_front=0、v_back=−dv → dv_scalar = 0−(−dv) = dv ✓
        assert np.allclose(f_vec, f_sca, rtol=1e-9, atol=1.0), \
            f"标量/向量化不一致: {f_vec} vs {f_sca}"


# ---------------------------------------------------------------------------
# 【R0-E】缓解排气时间常数
def test_release_exhaust_exponential_not_instant():
    """缓解后头车制动力按 exp(-t/τ) 衰减（不再瞬时归零），且约 4τ 后彻底缓解。"""
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(5)])
    tau = 2.0
    td = TrainDynamics(consist, dt=0.1, simcase='debug', release_exhaust_tau_s=tau)
    td.set_grade(0.0)
    td.set_initial_speed(20.0)
    n = consist.num_vehicles
    for _ in range(50):
        td.step_vehicles_ed_ab(np.zeros(n), np.zeros(n), AirBrakeNotch.SERVICE)
    assert td._air_brake_active[0]
    f_brake = abs(td._air_braking_forces()[0])
    assert f_brake > 0.0
    # 发缓解指令：头车立即开始排气（不再瞬时归零）
    td._advance_control_once(np.zeros(n), np.zeros(n), AirBrakeNotch.RELEASE,
                             0, None, False, 0.01, apply_command=True)
    td._advance_air_brake_propagation(0.01)
    f0 = abs(td._air_braking_forces()[0])
    assert f0 > 0.0, "头车缓解制动力瞬时归零（R0-E 未生效）"
    # 推进 τ：力衰减到 ≈ exp(-1)·f0
    for _ in range(int(tau / 0.01)):
        td._advance_air_brake_propagation(0.01)
    f_tau = abs(td._air_braking_forces()[0])
    assert f_tau == pytest.approx(f0 * np.exp(-1.0), rel=0.15)
    # 4τ 后彻底缓解
    for _ in range(int(3.0 * tau / 0.01) + 5):
        td._advance_air_brake_propagation(0.01)
    assert not td._air_brake_active[0]
    assert td._air_brake_release_frac[0] == 0.0


# ---------------------------------------------------------------------------
# 【R0.5】整段物理曲线自动核查（跨工况随机扫描，防"锚点外失真"再现）
def _run_cyclic(n_vehicles, grade_permille, v0, seed, n_cycles=3):
    """确定性循环制动场景：SERVICE→RELEASE 循环，返回逐段记录。"""
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(n_vehicles - 1)])
    td = TrainDynamics(consist, dt=0.1)
    td.set_grade(grade_permille / 1000.0)
    td.set_initial_speed(v0)
    n = n_vehicles
    rng = np.random.default_rng(seed)
    rec = {'f': [], 'f_tension': [], 'v': [], 'phase': [], 't': []}
    v_hi, v_lo = v0, 0.6 * v0
    for cyc in range(n_cycles):
        guard = 0
        while float(np.mean(td.vel)) > v_lo and guard < 2000:
            guard += 1
            td.step_vehicles_ed_ab(np.zeros(n), np.full(n, 0.2),
                                   AirBrakeNotch.SERVICE)
            rec['f'].append(float(np.max(np.abs(td.coupler_interface_forces()))))
            rec['f_tension'].append(float(np.min(td.coupler_interface_forces())))
            rec['v'].append(float(np.mean(td.vel)))
            rec['phase'].append(0)
            rec['t'].append(td.time)
        guard = 0
        while float(np.mean(td.vel)) < v_hi and guard < 3000:
            guard += 1
            td.step_vehicles_ed_ab(np.zeros(n), np.full(n, 0.1),
                                   AirBrakeNotch.RELEASE)
            rec['f'].append(float(np.max(np.abs(td.coupler_interface_forces()))))
            rec['f_tension'].append(float(np.min(td.coupler_interface_forces())))
            rec['v'].append(float(np.mean(td.vel)))
            rec['phase'].append(1)
            rec['t'].append(td.time)
        _ = rng.uniform()  # 保持 seed 参与确定性
    return rec


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("v0", [50 / 3.6, 65 / 3.6])
def test_cyclic_braking_whole_curve_physical_checks(seed, v0):
    """跨工况整段核查（R0.5）：量纲有界、无 NaN、缓解期出现拉钩力峰值（张二田 S3）、
    速度物理有界。"""
    rec = _run_cyclic(21, -10.2, v0, seed)
    f = np.array(rec['f'])
    v = np.array(rec['v'])
    assert np.all(np.isfinite(f)) and np.all(np.isfinite(v)), "出现 NaN/Inf"
    # 量纲有界：单钩力不超过缓冲器饱和 + 刚性限位合理余量（< 3000 kN）
    assert np.all(f < 3.0e6), f"车钩力超物理上界: max={np.max(f)/1e3:.0f} kN"
    # 速度物理有界：非负、不超过初速 +10%（下坡重力被制动控制的能量有界性）
    assert np.all(v >= -1e-9)
    assert np.all(v <= v0 * 1.10 + 0.5), f"速度超界: max={np.max(v):.2f}"
    # 行为判据（张二田 S3：最大拉钩力主要在缓解后出现）：峰值**拉钩力**（最负
    # 断面力）应出现在缓解阶段。制动阶段的峰值是压钩力——制动波前堵后涌，
    # 属施闸物理，与 S3 不冲突（张二田判据针对拉钩力/纵向加速度）。
    tension = np.array(rec['f_tension'])
    i_tension_peak = int(np.argmin(tension))
    assert rec['phase'][i_tension_peak] == 1, \
        f"峰值拉钩力出现在制动阶段（phase={rec['phase'][i_tension_peak]}），与实车规律不符"
    # 方向 + 相对判据（幅值随编组长度/τ 变化：21 节小编组波延迟 ~1.2s，
    # 缓解近同步，拉钩力绝对量级小；长度效应由 test_consist_length_effect 覆盖）
    assert tension.min() < -5e3, "缓解拉钩力未呈拉伸方向（前拉后拽物理缺失）"
    braking_min = tension[np.array(rec['phase']) == 0].min()
    assert tension.min() < braking_min, "缓解段拉钩力未深于制动段（S3 方向性缺失）"
    assert f.max() > 50e3, "车钩力量级异常偏低"


def test_grade_direction_and_energy_consistency():
    """能量趋势核查：恒下坡惰行动能增量 ≈ 重力功 − 阻功耗（有界、方向正确）。"""
    consist = TrainConsist([VehicleParams(mass_t=100.0)])
    td = TrainDynamics(consist, dt=0.1, simcase='debug', enable_cyclic_degrade=False)
    td.set_grade(-0.0102)
    td.set_initial_speed(10.0)
    e0 = 0.5 * 100e3 * 10.0 ** 2
    for _ in range(100):
        td.step(0.0, 0.0)
    e1 = 0.5 * 100e3 * float(td.vel[0]) ** 2
    assert e1 > e0, "下坡惰行动能未增加（坡度方向或阻力双重计算）"
    m = 100e3
    grav_work = m * 9.81 * 0.0102 * float(td.pos[0])
    assert e1 - e0 <= grav_work * 1.05, "动能增量超过重力功（能量不守恒）"


if __name__ == '__main__':
    import pytest as _p
    _p.main([__file__, '-q'])
