"""Diagnostic banded Newton step for the existing nearest-neighbour force law.

No physical parameters are changed. Three-colour central differences exploit
the tridiagonal acceleration Jacobian; only native local train forces apply.
"""
import numpy as np
from scipy.linalg import solve_banded


def newton_trial(dyn, force, h, tol, max_iter, force_tol_n):
    x, v, a0 = dyn.pos.copy(), dyn.vel.copy(), dyn._acc0.copy()
    mass = dyn.masses_kg
    a = a0.copy()

    def state(acc):
        return (x + h * v + 0.25 * h * h * (a0 + acc),
                v + 0.5 * h * (a0 + acc))

    def residual(acc):
        position, velocity = state(acc)
        return mass * acc - force - dyn._state_forces(position, velocity)

    for iteration in range(1, max_iter + 1):
        r = residual(a)
        norm = float(np.max(np.abs(r)))
        if not np.isfinite(norm):
            return False, norm, iteration
        if norm <= force_tol_n and float(np.max(np.abs(0.25*h*h*r/mass))) <= tol:
            position, velocity = state(a)
            if np.any(velocity < 0):
                return False, norm, iteration
            dyn.pos, dyn.vel, dyn._acc0 = position, velocity, a.copy()
            dyn.time += h
            return True, norm, iteration
        # Resolve absolute position rounding while remaining within the smooth
        # velocity-switch region. This is a numerical FD scale, not a force-law parameter.
        eps = np.maximum(1e-4, 64 * np.spacing(np.maximum(np.abs(x), 1.0)) / (0.25*h*h))
        band = np.zeros((3, len(a)))
        for colour in range(3):
            cols = np.arange(colour, len(a), 3)
            if not len(cols):
                continue
            plus, minus = a.copy(), a.copy()
            plus[cols] += eps[cols]
            minus[cols] -= eps[cols]
            difference = residual(plus) - residual(minus)
            for offset in (-1, 0, 1):
                valid = cols[(cols + offset >= 0) & (cols + offset < len(a))]
                band[1 + offset, valid] = difference[valid + offset] / (2 * eps[valid])
        try:
            delta = solve_banded((1, 1), band, -r)
        except (ValueError, np.linalg.LinAlgError):
            return False, norm, iteration
        for power in range(8):
            proposal = a + delta * (0.5 ** power)
            trial_norm = float(np.max(np.abs(residual(proposal))))
            if np.isfinite(trial_norm) and trial_norm < norm:
                a = proposal
                break
        else:
            return False, norm, iteration
    return False, norm, max_iter
