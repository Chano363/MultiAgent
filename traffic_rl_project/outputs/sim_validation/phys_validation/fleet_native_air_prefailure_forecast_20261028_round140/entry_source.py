"""Copied fleet with native control/pneumatics and approximate centroid motion.

Reuses the complete native air transaction instead of reimplementing valve,
propagation, pressure-rise or release equations. Relative vehicle geometry is
frozen: coupler feedback and safety predictions are therefore approximate.
This forecast must never be saved as a restart or certified as a safe action.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import MethodType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.brake_phase_snapshot import snapshot
from src.evaluation.continue_fleet_numerics import recorded_context
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint


def centroid_mechanics(self, control_forces, dt, max_iter=None, tol=None):
    mass = float(self.masses_kg.sum())
    velocity = float(np.dot(self.vel, self.masses_kg)/mass)
    acceleration = float((control_forces+self._grade_forces()
                          -self._resistance_forces()).sum()/mass)
    next_velocity = velocity+dt*acceleration
    self.pos += .5*(velocity+next_velocity)*dt
    self.vel = np.full(self.num_vehicles, next_velocity)
    self._acc0 = np.full(self.num_vehicles, acceleration)
    self.time += dt


def forecast(env, manifest, steps):
    if steps < 1:
        raise ValueError('Positive control-step horizon required')
    speeds = np.concatenate([train.dynamics.vel for train in env.trains])
    if (not np.isfinite(speeds).all() or np.max(speeds) >= env.v_max
            or np.min(speeds) < env.v_min):
        raise ValueError('Forecast origin is already outside the validated speed band')
    branch = copy.deepcopy(env)
    original_advances = []
    for train in branch.trains:
        dyn = train.dynamics
        observer = dyn.__dict__.pop('step_vehicles_ed_ab', None)
        if observer is not None and getattr(observer, '__name__', '') != 'record_inputs':
            raise ValueError('Unknown instance actuator override')
        if '_step_newmark' in dyn.__dict__ or '_advance_control_once' in dyn.__dict__:
            raise ValueError('Unknown instance mechanical override')
        # Capture native air transaction before numerical context installs its
        # rollback wrapper. On this isolated approximation no mechanical trial
        # can fail, so that wrapper must not deepcopy the whole fleet each .01s.
        original_advances.append(dyn._advance_control_once.__func__)
        dyn._step_newmark = MethodType(centroid_mechanics, dyn)
    branch.max_steps = max(branch.max_steps, branch.steps+steps+1)
    for train, ctrl in zip(branch.trains, branch.multi_loco_controllers):
        train.max_steps = max(train.max_steps, train.steps+steps+1)
        ctrl._release_probe_active = True  # Native checkpoint guard rejects this state.
    times, means, heads, commands, sources, waits, air, coefficients, events = ([] for _ in range(9))
    initial_safety = sum(train._safety_events for train in branch.trains)
    reason = 'horizon_completed'
    began = time.monotonic()
    try:
        with recorded_context([], manifest['numerical']):
            for train, native in zip(branch.trains, original_advances):
                train.dynamics._advance_control_once = MethodType(native, train.dynamics)
            for i in range(steps):
                _, _, terminated, truncated, info = branch.step(np.zeros((branch.num_agents, 2)))
                phases = []
                forces = []
                for train, ctrl in zip(branch.trains, branch.multi_loco_controllers):
                    force = train.dynamics._air_braking_forces()
                    forces.append(force.copy())
                    phases.append(snapshot(ctrl, train.dynamics, mechanical_air_force_n=force))
                times.append(float(branch.trains[0].dynamics.time))
                means.append([float(train.dynamics.vel.mean()) for train in branch.trains])
                heads.append([float(train.dynamics.pos[0]) for train in branch.trains])
                commands.append(np.asarray(info['executed_actions']).copy())
                sources.append([phase.source_on for phase in phases])
                waits.append([phase.refill_remaining_s for phase in phases])
                air.append(forces)
                coefficients.append([[phase.effective_coefficient_min, phase.effective_coefficient_max]
                                     for phase in phases])
                events.append(sum(train._safety_events for train in branch.trains)-initial_safety)
                if i % 500 == 0:
                    print(f'air_centroid step={i}/{steps} time={times[-1]:.1f}', flush=True)
                if not np.isfinite(means[-1]).all():
                    reason = 'nonfinite'
                    break
                if max(means[-1]) >= branch.v_max:
                    reason = 'predicted_speed_ceiling'
                    break
                if min(means[-1]) < branch.v_min:
                    reason = 'predicted_speed_floor'
                    break
                if events[-1] > 0:
                    reason = 'predicted_native_safety_event'
                    break
                if terminated or truncated:
                    reason = 'environment_ended'
                    break
    finally:
        branch.close()
    return dict(time=np.asarray(times), mean_mps=np.asarray(means), heads_m=np.asarray(heads),
        commands=np.asarray(commands), ab_source_on=np.asarray(sources),
        refill_remaining_s=np.asarray(waits), vehicle_air_force_n=np.asarray(air),
        effective_coefficient_min_max=np.asarray(coefficients), safety_count=np.asarray(events)), dict(
            stop_reason=reason, simulated_s=len(times)*env.dt, steps=len(times),
            wall_s=time.monotonic()-began, forecast_state_restart_prohibited=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, required=True)
    args = p.parse_args()
    env, manifest = load_fleet_checkpoint(args.state_dir)
    import pickle
    before = hashlib.sha256(pickle.dumps(env)).hexdigest()
    data, summary = forecast(env, manifest, args.steps)
    if before != hashlib.sha256(pickle.dumps(env)).hexdigest():
        raise RuntimeError('Forecast mutated its source fleet')
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output/'forecast.npz', **data)
    result = dict(scope='Native air/control, approximate centroid mechanics; no safety certificate',
        assumptions=['Native air equations, controller clocks, source admission and ATP reused',
            'Fixed relative geometry and uniform per-train velocity; coupler feedback approximate',
            'No future archived commands, positions or safety events used as inputs',
            'Forecast never becomes a live checkpoint'], source_manifest=manifest, summary=summary,
        source_fleet_unchanged=True, entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    env.close()
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
