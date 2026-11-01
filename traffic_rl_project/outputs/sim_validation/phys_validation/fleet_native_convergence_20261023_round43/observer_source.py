"""Observe controller inputs without replacing decisions or native physics."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import runpy
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.controllers.multi_loco_controller import MultiLocoController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observe-mechanics', action='store_true')
    args = parser.parse_args()
    records = []
    original = MultiLocoController.get_action_decomposed

    def observe(ctrl, train, actions, *positional, **kwargs):
        controls = dict(zip(('v_max', 'v_min', 'ed_mod_coef', 'v_max_adj', 'v_min_adj'), positional))
        controls.update(kwargs)
        record = [float(train.dynamics.time), float(train.dynamics.pos[0]),
            float(train.dynamics.vel[0]), float(controls.get('v_max_adj', 0.)),
            float(controls.get('v_min_adj', 0.)),
            float(np.abs(train.dynamics.coupler_interface_forces()).max())]
        final, baseline = original(ctrl, train, actions, *positional, **kwargs)
        records.append(record + [float(final[0, 0]), float(final[0, 1]),
                                 float(baseline[0, 0]), float(baseline[0, 1])])
        return final, baseline

    saved_argv = sys.argv
    mechanical_samples = []
    MultiLocoController.get_action_decomposed = observe
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config',
            'configs/experiments/formation_ed_ab_3train_1plus108.yaml',
            '--trains', '3', '--speed', '70', '--profile',
            'shuozhou_ningwuxi_beidaniu_49km', '--steps', '300',
            '--stop-on-coupler-kn', '1000', '--output', str(args.output)]
        from src.evaluation.newmark_observer import observe_newmark
        context = observe_newmark(mechanical_samples) if args.observe_mechanics else nullcontext()
        with context:
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    finally:
        MultiLocoController.get_action_decomposed = original
        sys.argv = saved_argv
    rows = np.asarray(records).reshape(-1, 3, 10)
    np.savez_compressed(args.output/'controller_inputs.npz', rows=rows)
    raw = Path(__file__).read_bytes()
    (args.output/'observer_source.py').write_bytes(raw)
    path = args.output/'result.json'
    result = json.loads(path.read_text(encoding='utf-8'))
    result['metadata']['read_only_controller_observer'] = dict(
        sha256=hashlib.sha256(raw).hexdigest(),
        columns=['time_s', 'head_m', 'head_speed_mps', 'v_max_adj_mps', 'v_min_adj_mps',
                 'predecision_peak_n', 'requested_ed', 'requested_ab', 'baseline_ed', 'baseline_ab'],
        scope='Records base controller inputs and outputs; no control or physical state mutation')
    if args.observe_mechanics:
        values = np.asarray(mechanical_samples)
        np.savez_compressed(args.output/'mechanical_observations.npz', rows=values)
        result['metadata']['native_mechanical_observer'] = dict(
            intervals=len(values), nonconverged_intervals=int(np.sum(values[:, 5] == 0)),
            max_displacement_residual_m=float(values[:, 3].max()),
            columns=['start_s', 'dt_s', 'iterations', 'displacement_residual_m',
                     'tolerance_m', 'native_converged'],
            source_sha256=hashlib.sha256(Path('src/evaluation/newmark_observer.py').read_bytes()).hexdigest(),
            scope='Read-only native stopping criterion, not a rigorous trajectory error bound')
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
