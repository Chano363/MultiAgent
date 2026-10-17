"""Compare native continuation with a kinematically matched fresh reset.

This diagnostic never injects cylinder pressure or discards warm-up violations.
The warm branch keeps the entire live environment, including integration,
coupler, pneumatic, controller and safety histories. The cold branch is a fresh
environment with exactly the same vehicle positions and velocities. It is a
history ablation, not a comparison differing only in cylinder pressure.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def cold_from_kinematics(warm, config):
    """Fresh history, identical kinematics; never restore from incomplete NPZs."""
    cold = TrainFleetEnv(config)
    cold.reset(seed=0, options={'speed': 0.0})
    for i, (source, target) in enumerate(zip(warm.trains, cold.trains)):
        target.dynamics.set_initial(pos=source.dynamics.pos.copy(),
                                    vel=source.dynamics.vel.copy())
        cold._train_heads[i] = float(target.dynamics.pos[0])
    return cold


def physical_sample(env):
    return {
        'positions_m': np.array([t.dynamics.pos for t in env.trains]),
        'velocities_mps': np.array([t.dynamics.vel for t in env.trains]),
        'pressure_coefficient': np.array([t.dynamics._brake_pressure for t in env.trains]),
        'air_active': np.array([t.dynamics._air_brake_active for t in env.trains]),
        'air_release_fraction': np.array([t.dynamics._air_brake_release_frac for t in env.trains]),
        'air_force_n': np.array([t.dynamics._air_braking_forces() for t in env.trains]),
        'coupler_force_n': np.array([t.dynamics.coupler_interface_forces() for t in env.trains]),
        'brake_segment': np.array([t.dynamics._brake_segment for t in env.trains]),
        'overspeed_count': np.array([t._overspeed_violations for t in env.trains]),
        'safety_count': np.array([t._safety_events for t in env.trains]),
    }


def record(env, steps, target_kn, finish_head_m=None):
    """Include the starting state and every actual step, including failed ones."""
    samples = [physical_sample(env)]
    commands = []
    terminated = truncated = False
    reason = None
    for k in range(steps):
        _, _, terminated, truncated, info = env.step(np.zeros((env.num_agents, 2)))
        commands.append(np.array(info['executed_actions']))
        sample = physical_sample(env)
        samples.append(sample)
        if not all(np.all(np.isfinite(a)) for a in sample.values()):
            raise RuntimeError('Nonfinite physical trajectory')
        if np.max(np.abs(sample['coupler_force_n'])) > target_kn * 1000:
            reason = 'coupler_target'
        elif finish_head_m is not None and sample['positions_m'][0, 0] >= finish_head_m:
            reason = 'head_target'
        if k % 100 == 0:
            print(f'step={k + 1} head={sample["positions_m"][0, 0]:.1f}m', flush=True)
        if reason or terminated or truncated:
            break
    arrays = {name: np.array([s[name] for s in samples]) for name in samples[0]}
    arrays['commands'] = np.array(commands)
    arrays['time_s'] = np.arange(len(samples)) * env.dt
    velocity = arrays['velocities_mps']
    return arrays, {
        'steps': len(commands), 'elapsed_s': len(commands) * env.dt,
        'peak_kn_including_initial': float(np.max(np.abs(arrays['coupler_force_n'])) / 1000),
        'max_vehicle_speed_kmh_including_initial': float(np.max(velocity) * 3.6),
        'mean_train_speed_kmh': float(np.mean(velocity[1:]) * 3.6),
        'min_train_mean_speed_kmh': float(np.min(velocity[1:].mean(axis=2)) * 3.6),
        'overspeed_train_steps': int(np.sum(arrays['overspeed_count'][-1]
                                           - arrays['overspeed_count'][0])),
        'safety_events': int(np.sum(arrays['safety_count'][-1] - arrays['safety_count'][0])),
        'coupler_section_time_violations': int(np.count_nonzero(
            np.abs(arrays['coupler_force_n'][1:]) > env.coupler_force_limit_n)),
        'stop_reason': reason or ('terminated' if terminated else 'truncated' if truncated else None),
    }


def main():
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start-m', type=float, default=20000)
    parser.add_argument('--speed-kmh', type=float, default=65)
    parser.add_argument('--warmup-steps', type=int, default=600)
    parser.add_argument('--warmup-until-head-m', type=float,
                        help='Run physically to this position, within warmup-steps budget')
    parser.add_argument('--compare-steps', type=int, default=1200)
    parser.add_argument('--target-kn', type=float, default=1350)
    args = parser.parse_args()
    if (min(args.warmup_steps, args.compare_steps) < 1
            or not np.all(np.isfinite([args.start_m, args.speed_kmh, args.target_kn]))
            or args.speed_kmh < 0 or args.target_kn <= 0):
        parser.error('Finite physical inputs and positive step counts/target required')
    if args.warmup_until_head_m is not None and (
            not np.isfinite(args.warmup_until_head_m) or args.warmup_until_head_m <= args.start_m):
        parser.error('warmup-until-head-m must be finite and beyond start-m')
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg']
    config.update(num_trains=1, max_steps=args.warmup_steps + args.compare_steps + 1,
                  start_randomization={'enabled': False},
                  formation_start_randomization={'enabled': False}, eval_mode=True)
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    sources = ['src/environments/train_fleet_env.py', 'src/environments/train_env.py',
               'src/controllers/multi_loco_controller.py', 'src/train_dynamics/train.py',
               'src/train_dynamics/braking.py', 'src/train_dynamics/coupler.py',
               'src/train_dynamics/etcs_braking.py', str(Path(__file__).relative_to(Path.cwd()))]
    hashes = {}
    for name in sources:
        source = Path(name).read_text(encoding='utf-8')
        hashes[name] = hashlib.sha256(source.encode('utf-8')).hexdigest()
        (output / Path(name).name).write_text(source, encoding='utf-8')
    metadata = build_metadata(str(Path.cwd()), 'official', official_world_config(env_cfg=config),
                              0, __file__, extra={'env_cfg': config, 'source_sha256': hashes,
                              'protocol': {k: str(v) if isinstance(v, Path) else v
                                           for k, v in vars(args).items()},
                              'scope': 'single-train diagnostic; no RL training',
                              'history_ablation': 'all hidden history reset; position and velocity matched'})
    result = {'metadata': metadata, 'summary': {}}
    result_path = output / 'result.json'
    result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    warm = TrainFleetEnv(config)
    cold = None
    try:
        warm.reset(seed=0, options={'speed': args.speed_kmh / 3.6})
        for i, train in enumerate(warm.trains):
            train.dynamics.set_initial(pos=train.dynamics.pos + args.start_m,
                                       vel=train.dynamics.vel.copy())
            warm._train_heads[i] = float(train.dynamics.pos[0])
        trajectory, summary = record(warm, args.warmup_steps, args.target_kn,
                                     finish_head_m=args.warmup_until_head_m)
        np.savez_compressed(output / 'warmup.npz', **trajectory)
        result['summary']['warmup'] = summary
        result['summary']['warmup_accepted'] = bool(
            summary['stop_reason'] in (None, 'head_target') and summary['overspeed_train_steps'] == 0
            and (args.warmup_until_head_m is None or summary['stop_reason'] == 'head_target')
            and summary['peak_kn_including_initial'] <= args.target_kn)
        # Persist warm-up failure too. Never advertise its continuation as a safe start.
        result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        if not result['summary']['warmup_accepted']:
            print(json.dumps(result['summary'], indent=2), flush=True)
            return
        cold = cold_from_kinematics(warm, config)
        np.testing.assert_array_equal(warm.trains[0].dynamics.pos, cold.trains[0].dynamics.pos)
        np.testing.assert_array_equal(warm.trains[0].dynamics.vel, cold.trains[0].dynamics.vel)
        # No reset/deepcopy is needed on the warm branch: it is the actual running instance.
        for name, env in [('warm_continuation', warm), ('cold_kinematics_only', cold)]:
            trajectory, summary = record(env, args.compare_steps, args.target_kn)
            np.savez_compressed(output / f'{name}.npz', **trajectory)
            result['summary'][name] = summary
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result['summary'], indent=2), flush=True)
    finally:
        warm.close()
        if cold is not None:
            cold.close()


if __name__ == '__main__':
    main()
