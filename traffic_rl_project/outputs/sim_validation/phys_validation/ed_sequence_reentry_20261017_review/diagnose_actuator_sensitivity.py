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
from pathlib import Path
import sys

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


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
    ap.add_argument('--ed-ramp-per-s', type=float, default=0.5,
                    help='Engineering trial command slew, not a physical parameter')
    args = ap.parse_args()
    if (not np.all(np.isfinite([args.start_m, args.speed_kmh, args.horizon_s, *args.times_s]))
            or not np.isfinite(args.ed_ramp_per_s) or args.ed_ramp_per_s <= 0
            or args.horizon_s <= 0 or min(args.times_s) <= 0):
        ap.error('Finite inputs and positive horizon/checkpoint times required')
    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg']
    cfg.update(num_trains=1, max_steps=10000, start_randomization={'enabled': False}, eval_mode=True)
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.controller_source.read_text(encoding='utf-8')
    (args.output / 'controller_source.py').write_text(source, encoding='utf-8')
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
            variants = {'baseline_hold': actions[:, 0], 'coast': [0, 0],
                        'both_full': [1, 1], 'head_only': [1, 0], 'middle_only': [0, 1]}
            if args.sequence_grid:
                if len(actions) != 2:
                    raise ValueError('Sequence grid requires exactly two locomotives')
                depths = list(itertools.product((0.0, 0.5, 1.0), repeat=2))
                variants = {f'sequence_{a}_{b}': np.asarray([first, second])
                            for a, first in enumerate(depths)
                            for b, second in enumerate(depths)}
            checkpoint = {'time_s': k * env.dt,
                          'initial_peak_kn': float(np.abs(dyn.coupler_interface_forces()).max()/1000),
                          'variants': {}}
            for name, depths in variants.items():
                branch = copy.deepcopy(env.trains[0])
                action = actions.copy()
                if not args.sequence_grid:
                    action[:, 0] = depths
                previous_ed = actions[:, 0].copy()
                rows = []
                commands = []
                for j in range(horizon):
                    if args.sequence_grid:
                        target = depths[min(1, (2 * j) // horizon)]
                        delta = args.ed_ramp_per_s * env.dt
                        previous_ed += np.clip(target - previous_ed, -delta, delta)
                        action[:, 0] = previous_ed
                    commands.append(action.copy())
                    branch.step(action)
                    d = branch.dynamics
                    rows.append([(j + 1) * env.dt,
                                 np.abs(d.coupler_interface_forces()).max(),
                                 d.vel.max(), d.vel.mean()])
                branch.close()
                rows = np.asarray(rows)
                np.savez_compressed(args.output / f'step{k}_{name}.npz', rows=rows,
                                    actions=np.asarray(commands))
                checkpoint['variants'][name] = {
                    'ED_depths': np.asarray(depths).tolist(),
                    'peak_kn': float(rows[:, 1].max()/1000),
                    'end_peak_kn': float(rows[-1, 1]/1000),
                    'max_vehicle_kmh': float(rows[:, 2].max()*3.6),
                    'end_mean_kmh': float(rows[-1, 3]*3.6)}
            result['checkpoints'].append(checkpoint)
            out.write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(checkpoint), flush=True)
    finally:
        env.close()


if __name__ == '__main__':
    main()
