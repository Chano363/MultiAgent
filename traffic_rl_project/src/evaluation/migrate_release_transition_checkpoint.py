"""Explicitly migrate a trusted fleet checkpoint after adding disabled ED-transition state.

The migration is intentionally narrow: it neither advances the simulation nor changes
any existing controller setting.  It only supplies the three new, default-disabled
attributes required by the additive release-transition mechanism, then creates a new
checkpoint with current source provenance.
"""
import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import save_fleet_checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = (Path.cwd()/'outputs/sim_validation/phys_validation').resolve()
    state = args.state_dir.resolve()
    output = args.output.resolve()
    if not state.is_relative_to(root) or not output.is_relative_to(root):
        raise ValueError('Only trusted local diagnostic archives may be migrated')
    if output.exists():
        raise FileExistsError('Migration output must be a new directory')
    manifest = json.loads((state/'fleet_state.json').read_text(encoding='utf-8'))
    payload = (state/'fleet_state.pkl').read_bytes()
    if (manifest.get('format') != 'trusted-local-fleet-v1'
            or manifest.get('sha256') != hashlib.sha256(payload).hexdigest()
            or manifest.get('numpy_version') is None
            or manifest.get('python_version') != list(sys.version_info[:2])):
        raise ValueError('Source checkpoint integrity or runtime provenance is invalid')
    env = pickle.loads(payload)
    changed = []
    for index, controller in enumerate(env.multi_loco_controllers, start=1):
        for name, value in (
                ('ed_release_transition_s', 0.0),
                ('ed_release_transition_ed_mod', 0.0),
                ('_ed_release_transition_steps', 0)):
            if not hasattr(controller, name):
                setattr(controller, name, value)
                changed.append(dict(train_one_based=index, attribute=name, value=value))
        if not hasattr(controller, 'etcs_anticipation_level'):
            controller.etcs_anticipation_level = 'sbi'
            changed.append(dict(train_one_based=index,
                                attribute='etcs_anticipation_level', value='sbi'))
    output.mkdir(parents=True)
    new_manifest = save_fleet_checkpoint(env, output, manifest['numerical'])
    source_result = json.loads((state/'result.json').read_text(encoding='utf-8'))
    metadata = source_result['metadata']
    (output/'result.json').write_text(json.dumps({
        'metadata': metadata,
        'summary': {'stop_reason': 'additive_default_state_migration', 'steps': 0,
                    'source_time_s': manifest['elapsed_s']},
    }, indent=2), encoding='utf-8')
    (output/'migration.json').write_text(json.dumps({
        'source': str(state), 'source_sha256': manifest['sha256'],
        'migrated_sha256': new_manifest['sha256'], 'changes': changed,
        'scope': ('No dynamics/history/configuration advancement; added fields are disabled defaults. '
                  'A later replay must record any non-default rule configuration separately.'),
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
