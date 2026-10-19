"""Native diagnostic lookahead; no training-time or production safety guarantee."""
import copy

import numpy as np


def clone_native_prediction_env(train_env):
    """Copy all native history, discarding only the diagnostic actuator observer.

    Python function closures are not deep-copied: leaving record_inputs attached
    would call the ORIGINAL dynamics from a copied environment.
    """
    branch = copy.deepcopy(train_env)
    hook = branch.dynamics.__dict__.get('step_vehicles_ed_ab')
    if hook is not None:
        if getattr(hook, '__name__', '') != 'record_inputs':
            raise ValueError('Unknown instance dynamics override in prediction state')
        del branch.dynamics.__dict__['step_vehicles_ed_ab']
    return branch


def evaluate_native_release(train_env, controller, control_kwargs, horizon_s,
                            singleton_leader_offset_mps=None):
    """Run a copied zero-RL controller and native physics through a refill window.

    Caller must set its wrapper to skip recursive guards when probe_active is
    true. Both native source admission and ATP remain enabled in the copy.
    """
    if not np.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError('Positive finite prediction horizon required')
    branch = clone_native_prediction_env(train_env)
    ctrl = copy.deepcopy(controller)
    ctrl._release_probe_active = True
    ceiling = float(control_kwargs.get('v_max', 80.0 / 3.6))
    floor = float(control_kwargs.get('v_min', 40.0 / 3.6))
    limit = float(ctrl.coupler_force_limit_n)
    count = int(np.ceil(horizon_s / ctrl.dt))
    # A forecast is not a training rollout. Its time budget must not expire at
    # the live episode's cutoff; only extend the copied administrative limit.
    original_max_steps = branch.max_steps
    branch.max_steps = max(branch.max_steps, branch.steps + count + 1)
    rows = []
    reason = 'horizon_completed'
    try:
        for step in range(count):
            if step % 500 == 0:
                print(f'release_lookahead step={step}/{count}', flush=True)
            step_controls = dict(control_kwargs)
            if singleton_leader_offset_mps is not None:
                # Reproduce TrainFleetEnv's SINGLE-train leader update every
                # step. A frozen offset from the origin is a different policy.
                cap = float(np.clip(ceiling, 0.0,
                                    float(branch.dynamics.vel[0]) + singleton_leader_offset_mps))
                step_controls['v_max_adj'] = cap - ceiling
                step_controls['v_min_adj'] = 0.0
            action, _ = ctrl.get_action_decomposed(
                branch, np.zeros((ctrl.num_locomotives, 2)), **step_controls)
            _, _, terminated, truncated, info = branch.step(action)
            ctrl.record_executed_ed(info['actual_loco_ed'])
            peak = float(np.abs(branch.dynamics.coupler_interface_forces()).max())
            speed = float(branch.dynamics.vel.max())
            rows.append([(step + 1) * ctrl.dt, peak, speed,
                         float(branch.dynamics.vel.mean()), float(action[0, 1]),
                         float(step_controls.get('v_max_adj', 0.0))])
            if not np.all(np.isfinite(rows[-1])):
                reason = 'nonfinite'
                break
            if peak > limit:
                reason = 'coupler_limit'
                break
            if speed >= ceiling - 1e-6:
                reason = 'speed_ceiling'
                break
            if float(branch.dynamics.vel.mean()) < floor - 1e-6:
                reason = 'speed_floor'
                break
            if terminated or truncated:
                reason = 'environment_ended'
                break
        rows = np.asarray(rows)
        return {
            'feasible': reason == 'horizon_completed',
            'reason': reason,
            'horizon_s': float(horizon_s),
            'simulated_s': float(rows[-1, 0]),
            'peak_kn': float(rows[:, 1].max() / 1000),
            'max_vehicle_kmh': float(rows[:, 2].max() * 3.6),
            'live_max_steps': int(original_max_steps),
            'prediction_max_steps': int(branch.max_steps),
            'singleton_leader_offset_mps': singleton_leader_offset_mps,
            'trajectory_columns': ['elapsed_s', 'peak_interface_N', 'max_vehicle_mps',
                                   'mean_vehicle_mps', 'AB_request', 'v_max_adj_mps'],
            'trajectory': rows,
        }
    finally:
        branch.close()
