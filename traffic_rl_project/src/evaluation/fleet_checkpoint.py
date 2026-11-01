"""Trusted local full-fleet checkpoints with explicit numerical provenance."""
import copy
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes


def save_fleet_checkpoint(env, directory, numerical):
    directory = Path(directory)
    if any(getattr(ctrl, '_release_probe_active', False) for ctrl in env.multi_loco_controllers):
        raise ValueError('Forecast state cannot become a live fleet restart')
    clone = copy.deepcopy(env)
    for train in clone.trains:
        hook = train.dynamics.__dict__.pop('step_vehicles_ed_ab', None)
        if hook is not None and getattr(hook, '__name__', '') != 'record_inputs':
            raise ValueError('Unknown actuator hook in fleet checkpoint')
    payload = pickle.dumps(clone, protocol=pickle.HIGHEST_PROTOCOL)
    if (directory/'fleet_state.pkl').exists():
        raise FileExistsError('Do not overwrite an existing checkpoint')
    manifest = dict(format='trusted-local-fleet-v1', sha256=hashlib.sha256(payload).hexdigest(),
        native_source_sha256=native_source_hashes(), numerical=numerical,
        elapsed_s=[float(t.dynamics.time) for t in env.trains],
        num_trains=env.num_trains, numpy_version=np.__version__, python_version=list(sys.version_info[:2]),
        scope='Complete fleet/controller/air/history state; requires matching numerical context')
    (directory/'fleet_state.pkl').write_bytes(payload)
    (directory/'fleet_state.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def load_fleet_checkpoint(directory):
    directory = Path(directory).resolve()
    root = (Path.cwd()/'outputs/sim_validation/phys_validation').resolve()
    if not directory.is_relative_to(root):
        raise ValueError('Only our trusted local diagnostic archive may be deserialized')
    manifest = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
    payload = (directory/'fleet_state.pkl').read_bytes()
    if (manifest['format'] != 'trusted-local-fleet-v1'
            or manifest['sha256'] != hashlib.sha256(payload).hexdigest()
            or manifest['native_source_sha256'] != native_source_hashes()
            or manifest['numpy_version'] != np.__version__
            or manifest['python_version'] != list(sys.version_info[:2])):
        raise ValueError('Fleet checkpoint provenance differs')
    for name, digest in manifest['numerical'].get('source_sha256', {}).items():
        if hashlib.sha256(Path('src/evaluation', name+'.py').read_bytes()).hexdigest() != digest:
            raise ValueError('Numerical checkpoint implementation differs')
    env = pickle.loads(payload)
    if (env.num_trains != manifest['num_trains']
            or not np.allclose([t.dynamics.time for t in env.trains], manifest['elapsed_s'], rtol=0, atol=1e-9)
            or any(getattr(c, '_release_probe_active', False) for c in env.multi_loco_controllers)):
        raise ValueError('Fleet checkpoint contents are inconsistent')
    return env, manifest
