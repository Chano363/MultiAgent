"""Native short-horizon actuator counterfactuals at matched running states.

These are open-loop actuator holds, not controller performance measurements.
Each branch preserves the same pneumatic, integration and safety history.
"""
import argparse
import copy
import hashlib
import inspect
import itertools
import json
import re
from pathlib import Path
import sys

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def capture_vehicle_state(dynamics, forces=None):
    """Read-only numerical signals, not a complete pneumatic replay checkpoint."""
    return {
        'vehicle_positions_m': dynamics.pos.copy(),
        'vehicle_speeds_mps': dynamics.vel.copy(),
        'integration_acceleration_mps2': dynamics._acc0.copy(),
        'coupler_interface_force_n': (dynamics.coupler_interface_forces()
                                      if forces is None else forces).copy(),
        'vehicle_grade': np.asarray(dynamics.grade).copy(),
        'brake_pressure_coefficient': dynamics._brake_pressure.copy(),
        'air_release_fraction': dynamics._air_brake_release_frac.copy(),
        'ab_active': dynamics._air_brake_active.copy(),
    }


def load_sequence_plan(path, horizon_s, num_locomotives=2):
    """Validate diagnostic requests; arbitrary file contents are not executed."""
    entries = json.loads(Path(path).read_text(encoding='utf-8'))['sequences']
    result = {}
    for entry in entries:
        name = entry['name']
        depths = np.asarray(entry['ED_depths'], dtype=float)
        durations = np.asarray(entry['durations_s'], dtype=float)
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in result:
            raise ValueError('Unique safe sequence names required')
        if (depths.ndim != 2 or depths.shape[1] != num_locomotives
                or durations.shape != (len(depths),) or not len(depths)
                or not np.all(np.isfinite(depths)) or np.any((depths < 0) | (depths > 1))
                or not np.all(np.isfinite(durations)) or np.any(durations <= 0)
                or not np.isclose(durations.sum(), horizon_s, rtol=0, atol=1e-8)):
            raise ValueError('Finite bounded ED blocks and positive durations covering horizon required')
        result[name] = (depths, durations)
    if not result:
        raise ValueError('At least one sequence required')
    return result


def main():
    official_entry_guard(__file__)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--controller-source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--start-m', type=float, default=26633.5)
    ap.add_argument('--speed-kmh', type=float, default=70)
    ap.add_argument('--times-s', type=float, nargs='+', default=[10, 11, 12])
    ap.add_argument('--horizon-s', type=float, default=2)
    ap.add_argument('--sequence-grid', action='store_true',
                    help='Two ED blocks over the horizon; native safety and AB retained')
    ap.add_argument('--sequence-grid-mode', choices=('full', 'corner_probes'), default='full',
                    help='corner_probes: 16 extremes plus centre and two prior transfer probes')
    ap.add_argument('--ed-ramp-per-s', type=float, default=0.5,
                    help='Engineering trial command slew, not a physical parameter')
    ap.add_argument('--record-vehicle-state', action='store_true',
                    help='Save per-vehicle and per-interface numerical signals')
    ap.add_argument('--sequence-file', type=Path,
                    help='JSON diagnostic ED blocks with explicit durations, replacing the grid')
    args = ap.parse_args()
    if args.sequence_file and args.sequence_grid:
        ap.error('Use either a sequence file or a sequence grid')
    if args.sequence_grid_mode != 'full' and not args.sequence_grid:
        ap.error('A sequence probe mode requires --sequence-grid')
    if (not np.all(np.isfinite([args.start_m, args.speed_kmh, args.horizon_s, *args.times_s]))
            or not np.isfinite(args.ed_ramp_per_s) or args.ed_ramp_per_s <= 0
            or args.horizon_s <= 0 or min(args.times_s) <= 0):
        ap.error('Finite inputs and positive horizon/checkpoint times required')
    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg']
    custom_sequences = load_sequence_plan(args.sequence_file, args.horizon_s) if args.sequence_file else None
    sequenced = args.sequence_grid or custom_sequences is not None
    cfg.update(num_trains=1, max_steps=10000, start_randomization={'enabled': False}, eval_mode=True)
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.controller_source.read_text(encoding='utf-8')
    (args.output / 'controller_source.py').write_text(source, encoding='utf-8')
    if args.sequence_file:
        (args.output / 'sequence_plan.json').write_bytes(args.sequence_file.read_bytes())
    namespace = {'__name__': 'sensitivity_frozen_controller'}
    exec(compile(source, '<sensitivity_controller>', 'exec'), namespace)
    cls = namespace['MultiLocoController']
    hashes = {}
    for filename in ['src/environments/train_fleet_env.py', 'src/environments/train_env.py',
                     'src/train_dynamics/train.py', 'src/train_dynamics/braking.py',
                     'src/safety_layer.py', 'src/train_dynamics/grade_profile.py', __file__]:
        code = Path(filename).read_text(encoding='utf-8')
        hashes[str(filename)] = hashlib.sha256(code.encode()).hexdigest()
        (args.output / Path(filename).name).write_text(code, encoding='utf-8')
    metadata = build_metadata(str(Path.cwd()), 'official', official_world_config(env_cfg=cfg), 0,
                              __file__, extra={'env_cfg': cfg, 'source_sha256': hashes,
                              'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                              'sequence_plan_sha256': (hashlib.sha256(args.sequence_file.read_bytes()).hexdigest()
                                                       if args.sequence_file else None),
                              'protocol': {k: str(v) if isinstance(v, Path) else v
                                           for k, v in vars(args).items()},
                              'scope': 'open-loop actuator sensitivity, not a policy evaluation'})
    result = {'metadata': metadata, 'checkpoints': []}
    out = args.output / 'result.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    env = TrainFleetEnv(cfg)
    try:
        original = env.multi_loco_controllers[0]
        env.multi_loco_controllers[0] = cls(**{k: getattr(original, k)
                                               for k in inspect.signature(cls).parameters})
        env.reset(seed=0, options={'speed': args.speed_kmh / 3.6})
        dyn = env.trains[0].dynamics
        dyn.set_initial(pos=dyn.pos + args.start_m, vel=dyn.vel.copy())
        env._train_heads[0] = float(dyn.pos[0])
        checkpoints = {int(round(t / env.dt)) for t in args.times_s}
        horizon = int(np.ceil(args.horizon_s / env.dt))
        for k in range(1, max(checkpoints) + 1):
            _, _, _, _, info = env.step(np.zeros((env.num_agents, 2)))
            if k not in checkpoints:
                continue
            actions = np.asarray(info['executed_actions']).copy()
            if args.record_vehicle_state:
                np.savez_compressed(args.output / f'step{k}_initial_vehicle_state.npz',
                                    **capture_vehicle_state(dyn), vehicle_masses_kg=dyn.masses_kg)
            variants = {'baseline_hold': actions[:, 0], 'coast': [0, 0],
                        'both_full': [1, 1], 'head_only': [1, 0], 'middle_only': [0, 1]}
            if args.sequence_grid:
                if len(actions) != 2:
                    raise ValueError('Sequence grid requires exactly two locomotives')
                depths = list(itertools.product((0.0, 0.5, 1.0), repeat=2))
                variants = {f'sequence_{a}_{b}': np.asarray([first, second])
                            for a, first in enumerate(depths)
                            for b, second in enumerate(depths)}
                if args.sequence_grid_mode == 'corner_probes':
                    probes = set(itertools.product((0.0, 1.0), repeat=4))
                    probes.update([(0.5, 0.5, 0.5, 0.5), (0.0, 1.0, 0.5, 0.5),
                                   (1.0, 0.0, 0.5, 0.0)])
                    variants = {name: value for name, value in variants.items()
                                if tuple(value.ravel()) in probes}
            if custom_sequences is not None:
                variants = {name: item[0] for name, item in custom_sequences.items()}
            checkpoint = {'time_s': k * env.dt,
                          'initial_peak_kn': float(np.abs(dyn.coupler_interface_forces()).max()/1000),
                          'variants': {}}
            result['checkpoints'].append(checkpoint)
            for name, depths in variants.items():
                branch = copy.deepcopy(env.trains[0])
                action = actions.copy()
                if not sequenced:
                    action[:, 0] = depths
                ends = None
                if custom_sequences is not None:
                    durations = custom_sequences[name][1]
                    steps = np.rint(durations / env.dt).astype(int)
                    if np.any(steps < 1) or not np.allclose(steps * env.dt, durations, atol=1e-8, rtol=0):
                        raise ValueError('Sequence durations must be positive multiples of native dt')
                    if steps.sum() != horizon:
                        raise ValueError('Sequence steps must cover the native diagnostic horizon')
                    ends = np.cumsum(steps)
                previous_ed = actions[:, 0].copy()
                rows = []
                commands = []
                histories = {}
                for j in range(horizon):
                    if sequenced:
                        block = int(np.searchsorted(ends, j, side='right')) if ends is not None else min(1, (2 * j) // horizon)
                        target = depths[block]
                        delta = args.ed_ramp_per_s * env.dt
                        previous_ed += np.clip(target - previous_ed, -delta, delta)
                        action[:, 0] = previous_ed
                    commands.append(action.copy())
                    branch.step(action)
                    d = branch.dynamics
                    forces = d.coupler_interface_forces()
                    if args.record_vehicle_state:
                        for key, value in capture_vehicle_state(d, forces).items():
                            histories.setdefault(key, []).append(value)
                    rows.append([(j + 1) * env.dt,
                                 np.abs(forces).max(),
                                 d.vel.max(), d.vel.mean()])
                branch.close()
                rows = np.asarray(rows)
                np.savez_compressed(args.output / f'step{k}_{name}.npz', rows=rows,
                                    actions=np.asarray(commands),
                                    **{key: np.stack(value) for key, value in histories.items()})
                checkpoint['variants'][name] = {
                    'ED_depths': np.asarray(depths).tolist(),
                    'peak_kn': float(rows[:, 1].max()/1000),
                    'end_peak_kn': float(rows[-1, 1]/1000),
                    'max_vehicle_kmh': float(rows[:, 2].max()*3.6),
                    'end_mean_kmh': float(rows[-1, 3]*3.6)}
                if custom_sequences is not None:
                    checkpoint['variants'][name]['block_durations_s'] = durations.tolist()
                out.write_text(json.dumps(result, indent=2), encoding='utf-8')
                print(f'checkpoint={k} completed={len(checkpoint["variants"])}/{len(variants)}', flush=True)
            print(json.dumps(checkpoint), flush=True)
    finally:
        env.close()


if __name__ == '__main__':
    main()
