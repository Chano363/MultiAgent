"""Static native force budget scan, not a trajectory or coupler-force test."""
import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
from src.train_dynamics.braking import AirBrakeNotch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.state_dir.resolve()
    if not directory.is_relative_to((Path.cwd()/'outputs/sim_validation/phys_validation').resolve()):
        raise ValueError('Only trusted local checkpoint exports may be inspected')
    manifest = json.loads((directory/'native_release_state.json').read_text(encoding='utf-8'))
    payload = (directory/'native_release_state.pkl').read_bytes()
    if (hashlib.sha256(payload).hexdigest() != manifest['sha256']
            or native_source_hashes() != manifest['native_source_sha256']):
        raise ValueError('Checkpoint source or payload changed')
    train = pickle.loads(payload)['train_env']
    dyn = train.dynamics
    override = dyn._brake_reduction_override_kpa
    if override is not None and not np.isclose(override, 50):
        raise ValueError('Checkpoint has a non-50kPa pressure override')
    # Synthetic fully established current-notch cylinder state, in this local
    # copy only. Do not claim this proves reservoir charge or safe transients.
    dyn._air_brake_notch[:] = AirBrakeNotch.CYCLIC
    dyn._air_brake_active[:] = True
    dyn._air_brake_releasing[:] = False
    dyn._air_brake_release_frac[:] = 1
    dyn._brake_pressure[:] = 1
    offset = dyn.pos-dyn.pos[0]
    total_mass = float(dyn.masses_kg.sum())
    ed = np.zeros(dyn.num_vehicles)
    ed[train.loco_indices] = 1
    rows = []
    try:
        for head in np.arange(0, 49600.1, 100):
            dyn.pos = head+offset
            dyn._update_grade_from_profile()
            gravity = float(dyn._grade_forces().sum())
            for speed in (40, 50, 65, 80):
                dyn.vel[:] = speed/3.6
                resistance = float(dyn._resistance_forces().sum())
                electric = -float(dyn._electric_braking_forces(ed).sum())
                air = -float(dyn._air_braking_forces().sum())
                net_ed = gravity-resistance-electric
                net_all = net_ed-air
                rows.append([head, speed, gravity/1000, resistance/1000,
                             electric/1000, air/1000, net_ed/1000,
                             net_all/1000, net_all/total_mass])
    finally:
        train.close()
    rows = np.asarray(rows)
    assert np.all(np.isfinite(rows))
    np.testing.assert_allclose(rows[:, 7], rows[:, 2]-rows[:, 3]-rows[:, 4]-rows[:, 5], atol=1e-10)
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output/'force_budget.npz', rows=rows)
    np.savetxt(args.output/'force_budget.csv', rows, delimiter=',', comments='',
        header='head_m,speed_kmh,gravity_kn,resistance_kn,ED_max_kn,AB50_full_kn,net_ED_only_kn,net_ED_AB50_kn,net_ED_AB50_accel_mps2')
    summary = {}
    for speed in (40, 50, 65, 80):
        sample = rows[rows[:, 1] == speed]
        worst = sample[np.argmax(sample[:, 7])]
        summary[str(speed)] = {'sample_points': len(sample),
            'points_still_accelerating_with_full_ED_AB50': int((sample[:, 7] > 0).sum()),
            'worst_head_m': float(worst[0]), 'worst_net_force_kn': float(worst[7]),
            'worst_acceleration_mps2': float(worst[8])}
    report = {'scope': 'Static fully established 50 kPa + maximum native ED; no delay, air recharge or coupler safety claim',
        'columns': 'head_m,speed_kmh,gravity_kn,resistance_kn,ED_max_kn,AB50_full_kn,net_ED_only_kn,net_ED_AB50_kn,net_ED_AB50_accel_mps2'.split(','),
        'positive_net_sign': 'accelerates downhill despite maximum tested brakes',
        'head_grid_spacing_m': 100, 'input_state_sha256': manifest['sha256'],
        'physical_source_sha256': manifest['native_source_sha256'],
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'mass_t': total_mass/1000, 'cyclic_degradation_enabled': dyn.enable_cyclic_degrade,
        'fixed_brake_segment': dyn._brake_segment, 'tail_pressure_kpa': dyn.tail_pressure_kpa,
        'summary': summary}
    (args.output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (args.output/'source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
