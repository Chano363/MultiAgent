# -*- coding: utf-8 -*-
"""
仿真场景（论文 4.2/4.3 节）
- 平缓坡道场景（图1）：加减速 + 缓坡
- 长大下坡场景（图3）：持续长大下坡 + 循环空气制动（文献[22]策略）
坡道数据与目标速度曲线原图为图片不可提取，按论文文字描述重构（记为 [ASM]）：
  平缓坡道：18 -> 22.22 m/s(80km/h) 加速、巡航、600-800s 减速至 10 m/s、巡航
  长大下坡：平直道巡航 18 m/s，进入约 -11‰ 长大下坡，循环制动维持 18 m/s
"""
import numpy as np

G = 9.81

def _piecewise(s, knots):
    s = np.asarray(s, dtype=float)
    val = np.full_like(s, knots[0][1])
    for (s0, g0), (s1, g1) in zip(knots[:-1], knots[1:]):
        m = (s > s0) & (s <= s1)
        val[m] = g0 + (g1 - g0) * (s[m] - s0) / max(s1 - s0, 1e-9)
    val[s > knots[-1][0]] = knots[-1][1]
    return val

# 平缓坡道（图1重构 [ASM]）：缓上坡+2‰ / 平坡 / 缓下坡-2‰ / 平坡 / 缓上坡+3‰
GENTLE_KNOTS = [(0, 2.0), (3000, 2.0), (3100, 0.0), (8000, 0.0),
                (8100, -2.0), (12000, -2.0), (12100, 0.0), (16000, 0.0),
                (16100, 3.0), (22000, 3.0)]

# 长大下坡（图3重构 [ASM]）：1.5 km 后过渡到 -11‰ 持续下坡，16 km 后缓和至 -4‰
DOWNHILL_KNOTS = [(0, 0.0), (1500, 0.0), (2000, -11.0), (15000, -11.0),
                  (16000, -11.0), (16500, -4.0), (22000, -4.0)]

def gradient_permille(s, scenario):
    knots = GENTLE_KNOTS if scenario == "gentle" else DOWNHILL_KNOTS
    return _piecewise(np.asarray(s, dtype=float), knots)

# ---------------- 目标速度曲线（smoothstep 斜坡，加速度连续） ----------------
_SEG_GENTLE = [(0.0, 250.0, 18.0, 80.0 / 3.6),
               (600.0, 800.0, 80.0 / 3.6, 10.0)]
_SEG_DOWN   = [(1000.0, 1100.0, 18.0, 14.0)]

def _seg(t, scenario):
    return _SEG_GENTLE if scenario == "gentle" else _SEG_DOWN

def target_speed(t, scenario):
    v = _seg(t, scenario)[0][2]
    for (t0, t1, v0, v1) in _seg(t, scenario):
        if t >= t1:
            v = v1
        elif t > t0:
            tau = (t - t0) / (t1 - t0)
            v = v0 + (v1 - v0) * (3 * tau ** 2 - 2 * tau ** 3)
            break
    return v

def target_accel(t, scenario):
    for (t0, t1, v0, v1) in _seg(t, scenario):
        if t0 < t < t1:
            T = t1 - t0
            tau = (t - t0) / T
            return (v1 - v0) / T * (6 * tau - 6 * tau ** 2)
    return 0.0

def target_position(t, scenario):
    """s_ref(t) = S_INIT[0] + ∫v dt（闭式积分，smoothstep 原函数 τ³-τ⁴/2）"""
    from params import S_INIT
    segs = _seg(t, scenario)
    s = float(S_INIT[0])
    last_t, last_v = 0.0, segs[0][2]
    for (t0, t1, v0, v1) in segs:
        if t >= t1:                       # 整段完成：巡航 + 完整变速段
            s += last_v * (t0 - last_t)
            T = t1 - t0
            s += v0 * T + (v1 - v0) * T / 2.0
            last_t, last_v = t1, v1
        elif t > t0:                      # 变速段内：巡航 + 部分变速
            s += last_v * (t0 - last_t)
            T = t1 - t0
            tau = (t - t0) / T
            s += v0 * (t - t0) + (v1 - v0) * T * (tau ** 3 - 0.5 * tau ** 4)
            return s
        else:                             # 尚未进入该段
            break
    s += last_v * (t - last_t)
    return s
