"""Bounded continuation from our full-fleet experimental checkpoint; no reset."""
import argparse
import json
from pathlib import Path
import sys
from contextlib import contextmanager

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint, save_fleet_checkpoint
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def recorded_context(samples, numerical):
    """Resume exactly the recorded solver; never silently substitute defaults."""
    if numerical['solver'] == 'newton_analytic_time_error':
        from src.evaluation.error_controlled_mechanics import candidate
        context = candidate(samples, **numerical['settings'])
        if 'release_budget_guard' in numerical.get('source_sha256', {}):
            return with_recorded_release_guard(context)
        return context
    if numerical['solver'] == 'newton_analytic':
        return coupled_candidate(samples, numerical_solver=numerical['solver'],
                                 **numerical['settings'])
    raise ValueError('Unsupported recorded experimental solver')


@contextmanager
def with_recorded_release_guard(numerical_context):
    from src.evaluation.release_budget_guard import candidate
    with numerical_context, candidate():
        yield


def main():
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('Positive continuation budget required')
    env, manifest = load_fleet_checkpoint(args.state_dir)
    numerical = manifest['numerical']
    if numerical['solver'] not in ('newton_analytic', 'newton_analytic_time_error'):
        raise ValueError('Unsupported recorded experimental solver')
    origin = json.loads((args.state_dir/'result.json').read_text(encoding='utf-8'))
    env.max_steps = max(env.max_steps, env.steps + args.steps + 1)
    for train in env.trains:
        train.max_steps = max(train.max_steps, train.steps + args.steps + 1)
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = build_metadata(str(Path.cwd()), 'official',
        official_world_config(env_cfg=origin['metadata']['env_cfg']), 0, __file__, extra={
            'env_cfg': origin['metadata']['env_cfg'], 'initial_fleet_manifest': manifest,
            'numerical': numerical, 'steps_budget': args.steps,
            'scope': 'Zero-RL bounded fleet continuation, not route or training acceptance'})
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    samples, rows, commands, positions, speeds, forces, pressure, clock = [], [], [], [], [], [], [], []
    air_forces, physical_ed, heads, rear_centers, gaps, safety, modes, holds = [], [], [], [], [], [], [], []
    actuator_inputs = [{} for _ in env.trains]
    for ti, tr in enumerate(env.trains):
        original_step = tr.dynamics.step_vehicles_ed_ab
        def record_inputs(throttle, ed_throttle, ab_command, *positional,
                          _ti=ti, _tr=tr, _original=original_step, **kwargs):
            actuator_inputs[_ti] = np.asarray(ed_throttle)[_tr.loco_indices].copy()
            return _original(throttle, ed_throttle, ab_command, *positional, **kwargs)
        tr.dynamics.step_vehicles_ed_ab = record_inputs
    reason, error = 'step_budget', None
    try:
        with recorded_context(samples, numerical):
            for step in range(args.steps):
                if (args.output/'STOP').exists():
                    reason = 'requested_stop_file'
                    break
                before = len(samples)
                _, _, terminated, truncated, info = env.step(np.zeros((env.num_agents, 2)))
                velocity = np.asarray([t.dynamics.vel.copy() for t in env.trains])
                cf = np.asarray([t.dynamics.coupler_interface_forces().copy() for t in env.trains])
                mean = velocity.mean(axis=1)
                micropeak = max((s['peak_interface_n'] for s in samples[before:]), default=0.)
                rows.append([env.trains[0].dynamics.time, np.abs(cf).max(), velocity.max(),
                             velocity.min(), mean.min(), micropeak])
                commands.append(np.asarray(info['executed_actions']).copy())
                positions.append([t.dynamics.pos.copy() for t in env.trains])
                speeds.append(velocity)
                forces.append(cf)
                pressure.append([t.dynamics._brake_pressure * t.dynamics._air_brake_release_frac
                                 * t.dynamics._air_brake_active for t in env.trains])
                clock.append([c._ab_step for c in env.multi_loco_controllers])
                air_forces.append([t.dynamics._air_braking_forces().copy() for t in env.trains])
                physical_ed.append([a.copy() for a in actuator_inputs])
                heads.append([float(t.dynamics.pos[0]) for t in env.trains])
                rear_centers.append([float(t.dynamics.pos[-1]) for t in env.trains])
                gaps.append(float(info.get('gap_min_m', float('inf'))))
                safety.append(int(info.get('safety_events', 0)))
                modes.append([c._cyclic_braking for c in env.multi_loco_controllers])
                holds.append([c._ed_hold_steps for c in env.multi_loco_controllers])
                if step % 100 == 0:
                    print(f't={rows[-1][0]:.1f} peak={micropeak/1000:.1f}', flush=True)
                if not np.all(np.isfinite(rows[-1])):
                    reason = 'nonfinite'
                    break
                if max(micropeak, np.abs(cf).max()) > env.coupler_force_limit_n:
                    reason = 'coupler_threshold'
                    break
                if velocity.max() >= env.v_max - 1e-6:
                    reason = 'speed_ceiling'
                    break
                if mean.min() < env.v_min - 1e-6:
                    reason = 'speed_floor'
                    break
                if velocity.min() < env.v_min - 1e-6:
                    reason = 'vehicle_speed_floor'
                    break
                if float(info.get('gap_min_m', float('inf'))) < 0:
                    reason = 'negative_gap'
                    break
                if terminated or truncated:
                    reason = 'environment_ended'
                    break
    except BaseException as exc:
        reason, error = 'exception_incomplete', repr(exc)
        raise
    finally:
        if reason not in ('exception_incomplete', 'nonfinite'):
            save_fleet_checkpoint(env, args.output, numerical)
        np.savez_compressed(args.output/'trajectory.npz', rows=np.asarray(rows),
            commands=np.asarray(commands), vehicle_positions_m=np.asarray(positions),
            vehicle_speeds_mps=np.asarray(speeds), coupler_interface_force_n=np.asarray(forces),
            effective_pressure_coefficient=np.asarray(pressure), controller_steps=np.asarray(clock))
        np.savez_compressed(args.output/'telemetry.npz', vehicle_air_force_n=np.asarray(air_forces),
            physical_loco_ed=np.asarray(physical_ed), heads=np.asarray(heads),
            last_vehicle_centers=np.asarray(rear_centers), gap_min_m=np.asarray(gaps),
            safety_events=np.asarray(safety), cyclic_braking=np.asarray(modes),
            ed_hold_steps=np.asarray(holds))
        summary = dict(stop_reason=reason, error=error, steps=len(rows),
            last_time_s=rows[-1][0] if rows else manifest['elapsed_s'][0],
            internal_peak_kn=max((s['peak_interface_n'] for s in samples), default=0)/1000,
            max_force_residual_n=max((s['max_force_residual_n'] for s in samples), default=0),
            accepted_microsteps=sum(s['accepted'] for s in samples),
            min_train_mean_kmh=min((r[4]*3.6 for r in rows), default=None),
            min_gap_m=min(gaps, default=None), safety_event_count=sum(safety),
            actual_air_force_peak_n=max((float(np.max(np.abs(f))) for f in air_forces), default=0.),
            vehicle_speed_floor_stop_enabled=True,
            min_vehicle_kmh=min((r[3]*3.6 for r in rows), default=None),
            max_vehicle_kmh=max((r[2]*3.6 for r in rows), default=None))
        (args.output/'result.json').write_text(json.dumps(dict(summary=summary, metadata=metadata),
            indent=2), encoding='utf-8')
        env.close()
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
