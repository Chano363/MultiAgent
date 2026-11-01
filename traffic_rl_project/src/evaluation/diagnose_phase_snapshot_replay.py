"""Instrument a native warm replay with immutable phase observations only."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation import fleet_checkpoint
from src.evaluation.brake_phase_snapshot import snapshot


def main():
    output = Path(sys.argv[sys.argv.index('--output')+1])
    original_load, original_step = fleet_checkpoint.load_fleet_checkpoint, TrainFleetEnv.step
    records = []

    def load(directory):
        env, manifest = original_load(directory)
        for name in ('brake_phase_snapshot', 'diagnose_phase_snapshot_replay'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    def observed_step(self, *args, **kwargs):
        result = original_step(self, *args, **kwargs)
        records.append(dict(time_s=float(self.trains[0].dynamics.time),
            trains=[asdict(snapshot(ctrl, train.dynamics,
                mechanical_air_force_n=train.dynamics._air_braking_forces()))
                for ctrl, train in zip(self.multi_loco_controllers, self.trains)]))
        return result

    fleet_checkpoint.load_fleet_checkpoint = load
    TrainFleetEnv.step = observed_step
    try:
        runpy.run_path('src/evaluation/diagnose_release_feasibility.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original_load
        TrainFleetEnv.step = original_step
        if output.exists():
            for name in ('brake_phase_snapshot', 'diagnose_phase_snapshot_replay'):
                (output/(name+'_source.py')).write_bytes(Path('src/evaluation', name+'.py').read_bytes())
            (output/'phase_observations.json').write_text(json.dumps(dict(
                scope='Observation only; native actuator and ATP retain action authority',
                records=records), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
