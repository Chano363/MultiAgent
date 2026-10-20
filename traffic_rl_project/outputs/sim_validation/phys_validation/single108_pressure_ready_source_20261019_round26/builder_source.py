"""Build an isolated pressure-ready ED recovery candidate from a frozen policy.

No pneumatic or coupler parameter is calibrated here. The 0.05/s ED slew is
the existing release-candidate command slew, not a literature vehicle constant.
"""


def pressure_ready_source(source):
    old = '''    if enabled:
        # Experimental ED operating floor relaxation; native ATP remains downstream.
        final[:, 0] = np.minimum(final[:, 0], 0.25)
'''
    new = '''    if enabled:
        dyn = train_env.dynamics
        pressure_ready = bool(np.all(dyn._air_brake_active)
                              and not np.any(dyn._air_brake_releasing)
                              and np.all(dyn._brake_pressure >= 1.0 - 1e-12))
        previous = self._previous_ed
        if pressure_ready and previous is not None:
            # Experimental command slew only; do not raise the base ED request.
            cap = np.maximum(0.25, np.asarray(previous) + 0.05 * self.dt)
            final[:, 0] = np.minimum(final[:, 0], cap)
        else:
            final[:, 0] = np.minimum(final[:, 0], 0.25)
'''
    if source.count(old) != 1:
        raise ValueError('Frozen phase-cap policy changed; review before building')
    return source.replace(old, new, 1)
