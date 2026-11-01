"""Bounded continuation from our full-fleet experimental checkpoint; no reset."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint, save_fleet_checkpoint
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


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
    if numerical['solver'] != 'newton_analytic':
        raise ValueError('Only the explicitly recorded experimental solver is supported')
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
    reason, error = 'step_budget', None
    try:
        with coupled_candidate(samples, numerical_solver=numerical['solver'], **numerical['settings']):
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
        summary = dict(stop_reason=reason, error=error, steps=len(rows),
            last_time_s=rows[-1][0] if rows else manifest['elapsed_s'][0],
            internal_peak_kn=max((s['peak_interface_n'] for s in samples), default=0)/1000,
            max_force_residual_n=max((s['max_force_residual_n'] for s in samples), default=0),
            accepted_microsteps=sum(s['accepted'] for s in samples),
            min_vehicle_kmh=min((r[3]*3.6 for r in rows), default=None),
            max_vehicle_kmh=max((r[2]*3.6 for r in rows), default=None))
        (args.output/'result.json').write_text(json.dumps(dict(summary=summary, metadata=metadata),
            indent=2), encoding='utf-8')
        env.close()
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
