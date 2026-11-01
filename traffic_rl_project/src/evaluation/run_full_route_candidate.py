"""Fixed zero-RL candidate from cold reset, with bounded restartable stages."""
import argparse
import copy
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint, save_fleet_checkpoint
from src.environments.train_fleet_env import TrainFleetEnv
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stage-steps', type=int, default=250)
    p.add_argument('--max-steps', type=int, default=60000)
    args = p.parse_args()
    if args.stage_steps < 1 or args.max_steps < 1:
        p.error('Positive budgets required')
    args.output.mkdir(parents=True, exist_ok=False)
    template = Path('outputs/sim_validation/phys_validation/fleet_gap_aware_air980s_20261025_round92')
    old, inherited = load_fleet_checkpoint(template)
    origin = json.loads((template/'metadata.json').read_text(encoding='utf-8'))
    cfg = copy.deepcopy(origin['env_cfg'])
    cfg.update(max_steps=args.max_steps+1, num_trains=3,
               start_randomization={'enabled': False})
    old.close()
    env = TrainFleetEnv(cfg)
    env.reset(seed=0, options={'speed': 70./3.6})
    for i, c in enumerate(env.multi_loco_controllers):
        c.anticipate_etcs = True
        c._following_rule_margin_mps = .5
        c._phase_release_floor_enabled = True
        c._refill_chase_pause_enabled = True
        c.cyclic_release_kmh = 54. if i == 0 else 50.
        if i > 0:
            c._held_air_balance_enabled = True
            c._held_air_gap_reference_m = env._dynamic_gap()
            c._held_air_smooth_handoff_enabled = True
        if i == 2:
            c._gap_aware_air_enabled = True
    numerical = copy.deepcopy(inherited['numerical'])
    stage_script = Path('src/evaluation/continue_fleet_numerics.py')
    stage_hash = hashlib.sha256(stage_script.read_bytes()).hexdigest()
    metadata = build_metadata(str(Path.cwd()), 'official', official_world_config(env_cfg=cfg),
        0, __file__, extra={'env_cfg': cfg, 'numerical': numerical,
        'scope': 'Fixed experimental zero-RL candidate from 70km/h reset; full-route diagnostic attempt',
        'finish_m': 49600., 'stage_steps': args.stage_steps, 'max_steps': args.max_steps,
        'continuation_source_sha256': stage_hash,
        'candidate': {'leader_release_kmh': 54., 'follower_release_kmh': 50.,
                      'held_air_trains': [2, 3], 'gap_aware_train': 3}})
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    (args.output/'continuation_source.py').write_bytes(stage_script.read_bytes())
    initial = args.output/'initial'
    initial.mkdir()
    save_fleet_checkpoint(env, initial, numerical)
    (initial/'result.json').write_text(json.dumps({'metadata': metadata,
        'summary': {'stop_reason': 'initial_state', 'steps': 0}}), encoding='utf-8')
    env.close()
    state, stages, used = initial, [], 0
    started = time.time()
    result = {'status': 'running', 'full_route_completed': False, 'stages': stages}
    def progress():
        result['elapsed_wall_s'] = time.time()-started
        (args.output/'progress.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    progress()
    try:
        while used < args.max_steps:
            if (args.output/'STOP').exists():
                result['status'] = 'requested_stop_between_stages'
                break
            if hashlib.sha256(stage_script.read_bytes()).hexdigest() != stage_hash:
                raise RuntimeError('Continuation source changed during diagnostic')
            steps = min(args.stage_steps, args.max_steps-used)
            output = args.output/f'stage_{len(stages)+1:04d}'
            subprocess.run([sys.executable, '-u', str(stage_script), '--state-dir', str(state),
                '--output', str(output), '--steps', str(steps), '--finish-m', '49600',
                '--stop-on-safety-event'], check=True)
            summary = json.loads((output/'result.json').read_text(encoding='utf-8'))['summary']
            used += summary['steps']
            stages.append({'directory': str(output), 'summary': summary})
            result.update(last_time_s=summary['last_time_s'], steps=used,
                          full_route_completed=summary['full_route_completed'])
            state = output
            progress()
            if summary['stop_reason'] != 'step_budget':
                result['status'] = summary['stop_reason']
                break
        else:
            result['status'] = 'max_step_budget'
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        progress()
        (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
