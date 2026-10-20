"""Diagnostic consistent tangent of the existing MT-2/Davis force law.

This differentiates the native piecewise law, including its velocity switch.
It changes no envelope, parameter, history, pressure or physical force.
At table/contact kinks the right-hand branch is used; Newton line search and
step rejection must still check the original force residual.
"""
import numpy as np

from src.train_dynamics.coupler import (
    RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N, STIFFNESS_BASE_N_PER_M,
)


def interpolation_slope(x, values):
    index = np.clip(np.searchsorted(RONG2025_X_M, x, side='right') - 1,
                    0, len(RONG2025_X_M) - 2)
    slope = np.diff(values)[index] / np.diff(RONG2025_X_M)[index]
    return np.where((x >= RONG2025_X_M[0]) & (x < RONG2025_X_M[-1]), slope, 0.0)


def interface_tangent(dyn, position, velocity):
    """Return dF/de and dF/d(v_front-v_back), in N/m and N/(m/s)."""
    cp = dyn._cp
    e = position[1:] - position[:-1] + dyn.coupler.free_length_m
    dv = velocity[:-1] - velocity[1:]
    gap = np.maximum(cp['coupler_gap_m'], 1e-9)
    s = np.tanh(e / gap)
    ds = (1 - s*s) / gap
    d = np.abs(e) - gap
    displacement = np.maximum(d, 0.0)
    dx = np.where(d > 0, np.sign(e), 0.0)
    z = np.tanh(d / 0.004)
    contact = 0.5 * (1 + z)
    dc = 0.5 * (1 - z*z) * np.sign(e) / 0.004
    gain = cp['stiffness'] / STIFFNESS_BASE_N_PER_M
    fl = np.interp(displacement, RONG2025_X_M, RONG2025_FL_N)
    fu = np.interp(displacement, RONG2025_X_M, RONG2025_FU_N)
    dfl = interpolation_slope(displacement, RONG2025_FL_N) * dx
    dfu = interpolation_slope(displacement, RONG2025_FU_N) * dx
    mid, half = 0.5*(fl+fu)*gain, 0.5*(fl-fu)*gain
    dmid, dhalf = 0.5*(dfl+dfu)*gain, 0.5*(dfl-dfu)*gain
    direction = np.tanh(s * dv / cp['friction_v_eps'])
    common = (1 - direction*direction) / cp['friction_v_eps']
    raw = contact * (mid - direction*half)
    active = (raw > 0) & (raw < cp['max_impulse_n'])
    rigid = cp['rigid_stiffness_nm'] * np.maximum(displacement-cp['stroke_m'], 0)
    magnitude = np.clip(raw, 0, cp['max_impulse_n']) + rigid
    de = ds*magnitude + s*(active*(dc*(mid-direction*half)
         + contact*(dmid-common*ds*dv*half-direction*dhalf))
         + cp['rigid_stiffness_nm']*dx*(displacement > cp['stroke_m']))
    ddv = -s*active*contact*common*s*half
    return de, ddv


def acceleration_jacobian(dyn, position, velocity, h):
    """Banded derivative of M*a - F(x(a),v(a)), beta=.25, gamma=.5.

    Grade is frozen during the native mechanical interval, as in _state_forces.
    Both displacement and velocity derivatives contribute to every interface.
    """
    de, ddv = interface_tangent(dyn, position, velocity)
    edge = 0.25*h*h*de - 0.5*h*ddv
    vehicles = dyn.consist.vehicles
    weight = np.asarray([v.mass_t for v in vehicles]) * 1.10231
    area = np.asarray([v.frontal_area_m2 for v in vehicles]) * 10.7639
    drag = np.asarray([v.drag_coef for v in vehicles])
    dr = (0.03*weight*2.23694 + 0.0036*area*drag*np.abs(velocity)*2.23694**2)*4.44822
    dr = np.where(np.abs(velocity) > 1e-6, dr, 0.0)
    band = np.zeros((3, len(velocity)))
    band[1] = dyn.masses_kg + 0.5*h*dr
    band[1, :-1] += edge
    band[1, 1:] += edge
    band[0, 1:] = -edge
    band[2, :-1] = -edge
    return band
