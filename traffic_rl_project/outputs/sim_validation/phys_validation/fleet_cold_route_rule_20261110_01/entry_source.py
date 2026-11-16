"""Restartable zero-RL cold-start route validation of the current fleet config."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint, save_fleet_checkpoint
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--numerical-state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial-speed-kmh', type=float, default=70.0)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--stage-steps', type=int, default=250)
    parser.add_argument('--max-steps', type=int, default=40000)
    args = parser.parse_args()
    if args.stage_steps < 1 or args.max_steps < 1 or args.initial_speed_kmh <= 0:
        parser.error('Positive steps and initial speed required')
    _, source = load_fleet_checkpoint(args.numerical_state)
    numerical = source['numerical']
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg'].copy()
    config['max_steps'] = args.max_steps + 1
    config['start_randomization'] = {'enabled': False}
    args.output.mkdir(parents=True, exist_ok=False)
    continuation = Path('src/evaluation/continue_fleet_numerics.py')
    frozen_hash = hashlib.sha256(continuation.read_bytes()).hexdigest()
    metadata = build_metadata(str(Path.cwd()), 'official', official_world_config(env_cfg=config),
        args.seed, __file__, extra=dict(env_cfg=config, numerical=numerical,
        initial_speed_kmh=args.initial_speed_kmh, stage_steps=args.stage_steps,
        max_steps=args.max_steps, finish_m=49600.0, continuation_source_sha256=frozen_hash,
        scope='Zero-RL cold-start route validation; no training or robustness claim'))
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    (args.output/'continuation_source.py').write_bytes(continuation.read_bytes())
    env = TrainFleetEnv(config)
    env.reset(seed=args.seed, options={'speed': args.initial_speed_kmh / 3.6})
    initial = args.output/'initial'
    initial.mkdir()
    save_fleet_checkpoint(env, initial, numerical)
    (initial/'result.json').write_text(json.dumps(dict(metadata=metadata,
        summary=dict(stop_reason='initial_state', steps=0))), encoding='utf-8')
    env.close()
    state, stages, used = initial, [], 0
    status = dict(status='running', stages=stages, steps=0, full_route_completed=False)
    def persist():
        (args.output/'result.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    persist()
    try:
        while used < args.max_steps:
            if (args.output/'STOP').exists():
                status['status'] = 'requested_stop_between_stages'
                break
            if hashlib.sha256(continuation.read_bytes()).hexdigest() != frozen_hash:
                raise RuntimeError('Continuation source changed during validation')
            stage = args.output/f'stage_{len(stages)+1:04d}'
            subprocess.run([sys.executable, '-u', str(continuation), '--state-dir', str(state),
                '--output', str(stage), '--steps', str(min(args.stage_steps, args.max_steps-used)),
                '--finish-m', '49600', '--route-scoped-speed-check'], check=True)
            summary = json.loads((stage/'result.json').read_text(encoding='utf-8'))['summary']
            used += summary['steps']
            stages.append(dict(directory=str(stage), summary=summary))
            status.update(steps=used, last_time_s=summary['last_time_s'],
                          full_route_completed=summary['full_route_completed'])
            state = stage
            persist()
            if summary['stop_reason'] != 'step_budget':
                status['status'] = summary['stop_reason']
                break
        else:
            status['status'] = 'max_step_budget'
    except BaseException as exc:
        status.update(status='failed', error=repr(exc))
        raise
    finally:
        persist()


if __name__ == '__main__':
    main()
