"""Read-only end-sample force accounting for an archived native fleet branch."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--origin', type=Path, required=True)
    p.add_argument('--segments', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    env, manifest = load_fleet_checkpoint(args.origin)
    blocks, hashes, previous = [], {}, manifest
    for directory in args.segments:
        meta = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        initial = meta['initial_fleet_manifest']
        if (initial['sha256'] != previous['sha256']
                or initial['native_source_sha256'] != manifest['native_source_sha256']):
            raise ValueError('A same-source linked native branch is required')
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            blocks.append(dict(time=a['rows'][:, 0], pos=a['vehicle_positions_m'],
                vel=a['vehicle_speeds_mps'], air=b['vehicle_air_force_n'],
                ed=b['physical_loco_ed'], source=b['ab_source_on'],
                wait=b['ab_refill_remaining_s'], hold=b['ed_hold_steps']))
        previous = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'fleet_state.json', 'trajectory.npz', 'telemetry.npz'):
            hashes[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    data = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    ticks = np.rint(data['time']*10).astype(np.int64)
    if np.any(np.diff(ticks) != 1):
        raise ValueError('Continuous control grid required')
    means = data['vel'].mean(axis=2)*3.6
    peak = int(np.argmax(np.ptp(means, axis=1)))
    records = []
    # Exact sampled event plus a sparse neighbourhood; no rerun or plant mutation.
    indices = sorted(set([peak] + [int(np.argmin(abs(data['time']-t)))
        for t in np.arange(data['time'][peak]-40, data['time'][peak]+60.01, 10)]))
    for ix in indices:
        trains = []
        for j, (train, ctrl) in enumerate(zip(env.trains, env.multi_loco_controllers)):
            dyn = copy.copy(train.dynamics)
            dyn.pos, dyn.vel = data['pos'][ix, j].copy(), data['vel'][ix, j].copy()
            dyn.grade = dyn._grade_profile.grades_for_positions(dyn.pos)
            proxy = copy.copy(train)
            proxy.dynamics = dyn
            command = np.zeros(dyn.num_vehicles)
            command[ctrl.loco_indices] = data['ed'][ix, j]
            full = np.zeros(dyn.num_vehicles)
            full[ctrl.loco_indices] = 1.
            gravity = float(dyn._grade_forces().sum())
            resistance = float(dyn._resistance_forces().sum())
            air = float(data['air'][ix, j].sum())
            ed = float(dyn._electric_braking_forces(command).sum())
            cap = -float(dyn._electric_braking_forces(full).sum())/1000
            mass = float(dyn.masses_kg.sum())
            choices = []
            for target in (300., 400., 450., 600., 900.):
                fraction = ctrl._ed_frac_for_total_kn(proxy, target)
                full[ctrl.loco_indices] = fraction
                achieved = -float(dyn._electric_braking_forces(full).sum())/1000
                choices.append(dict(request_kn=target, command=fraction,
                    achieved_kn=achieved, infeasible=target > cap+1.e-5))
            measured = None
            if ix:
                measured = float(np.dot(data['vel'][ix, j]-data['vel'][ix-1, j],
                    dyn.masses_kg)/mass/.1)
            trains.append(dict(train=j+1, mass_t=mass/1000, head_m=float(dyn.pos[0]),
                mean_kmh=float(means[ix, j]),
                mass_weighted_grade_per_mille=float(np.dot(dyn.grade, dyn.masses_kg)/mass*1000),
                gravity_kn=gravity/1000, resistance_kn=resistance/1000,
                air_braking_kn=-air/1000, actual_ed_kn=-ed/1000, native_ed_capacity_kn=cap,
                ed_command=data['ed'][ix, j].tolist(),
                source_on=data['source'][ix, j].tolist(),
                refill_remaining_s=data['wait'][ix, j].tolist(),
                hold_steps=np.asarray(data['hold'][ix, j]).tolist(),
                end_sample_external_accel_mps2=(gravity-resistance+air+ed)/mass,
                measured_interval_cm_accel_mps2=measured,
                force_request_mapping=choices))
        records.append(dict(time_s=float(data['time'][ix]), trains=trains))
    result = dict(scope='Read-only sampled force attribution, not a causal control counterfactual',
        accounting='End-sample forces versus preceding 0.1s mass-weighted acceleration; not an exact microstep reconstruction',
        origin_manifest=manifest, native_source_sha256=manifest['native_source_sha256'],
        peak_spread_time_s=float(data['time'][peak]), peak_spread_kmh=float(np.ptp(means[peak])),
        controller_config=[dict(train=j+1, locomotives=c.num_locomotives,
            native_conversion=c.ed_native_force_conversion,
            release_boost_request_kn=c.ed_release_boost_kn, hold_s=c.ed_release_hold_s,
            coordination=c.ed_release_coordination) for j, c in enumerate(env.multi_loco_controllers)],
        samples=records, source_sha256=hashes,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.mkdir(exist_ok=False, parents=True)
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(peak_time_s=result['peak_spread_time_s'],
        peak_spread_kmh=result['peak_spread_kmh'],
        peak_record=next(r for r in records if r['time_s'] == result['peak_spread_time_s'])), indent=2))
    env.close()


if __name__ == '__main__':
    main()
