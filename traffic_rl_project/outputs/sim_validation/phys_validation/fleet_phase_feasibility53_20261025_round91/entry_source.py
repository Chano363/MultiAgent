"""Read-only centroid screening of a release; never a live safety controller.

Uses native grade, Davis and ED curves on isolated copies. Omits residual air,
coupler motion and ED ramping. Archived leader motion is hindsight, not an
available online prediction. A passing screen is not physical acceptance.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint
from src.train_dynamics.etcs_braking import EbdTarget


def project_full_ed(dynamics, duration_s, dt):
    if not np.isfinite([duration_s, dt]).all() or duration_s <= 0 or dt <= 0:
        raise ValueError('Positive finite horizon and step required')
    dyn = copy.deepcopy(dynamics)
    mass = float(dyn.masses_kg.sum())
    velocity = float(np.dot(dyn.vel, dyn.masses_kg) / mass)
    positions = dyn.pos.copy()
    throttle = np.zeros(dyn.num_vehicles)
    throttle[[i for i, v in enumerate(dyn.consist.vehicles) if v.is_locomotive]] = 1.
    rows = []
    elapsed = 0.
    while elapsed < duration_s - 1e-10:
        dyn.pos = positions.copy()
        dyn.vel = np.full(dyn.num_vehicles, velocity)
        if dyn._grade_profile is not None:
            dyn.grade = dyn._grade_profile.grades_for_positions(dyn.pos)
        net_grade = float(dyn._grade_forces().sum() - dyn._resistance_forces().sum())
        capacity = -float(dyn._electric_braking_forces(throttle).sum())
        acceleration = (net_grade - capacity) / mass
        h = min(dt, duration_s - elapsed)
        next_velocity = max(0., velocity + h * acceleration)
        positions += .5 * (velocity + next_velocity) * h
        velocity = next_velocity
        elapsed += h
        rows.append([elapsed, positions[0], velocity, net_grade, capacity, acceleration])
    return np.asarray(rows)


def read_reference(directories, native_hashes):
    blocks = []
    hashes = {}
    for directory in directories:
        directory = Path(directory)
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        inherited = metadata.get('initial_fleet_manifest', {}).get('native_source_sha256')
        if inherited != native_hashes:
            raise ValueError('Leader reference uses different physical/controller sources')
        with np.load(directory / 'trajectory.npz') as trajectory, np.load(directory / 'telemetry.npz') as telemetry:
            blocks.append(np.column_stack((trajectory['rows'][:, 0], telemetry['last_vehicle_centers'],
                                           trajectory['vehicle_speeds_mps'][:, :, 0])))
        for name in ('trajectory.npz', 'telemetry.npz'):
            path = directory / name
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    data = np.concatenate(blocks)
    data = data[np.argsort(data[:, 0])]
    if np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError('Reference times must not overlap')
    return data, hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, nargs='+', required=True)
    parser.add_argument('--dt', type=float, default=.2)
    parser.add_argument('--horizon-s', type=float, default=None)
    args = parser.parse_args()
    env, manifest = load_fleet_checkpoint(args.state_dir)
    if env.num_trains != 3:
        raise ValueError('This reference layout requires exactly three trains')
    reference, hashes = read_reference(args.reference, manifest['native_source_sha256'])
    origin = float(env.trains[0].dynamics.time)
    args.output.mkdir(parents=True, exist_ok=False)
    projections, summaries = {}, []
    for j, (train, ctrl) in enumerate(zip(env.trains, env.multi_loco_controllers)):
        duration = (float(ctrl.ab_min_refill_s) if args.horizon_s is None
                    else args.horizon_s)
        rows = project_full_ed(train.dynamics, duration, args.dt)
        absolute = origin + rows[:, 0]
        sbi = np.full(len(rows), np.nan)
        distance = np.full(len(rows), np.nan)
        if j > 0:
            valid = (absolute >= reference[0, 0]) & (absolute <= reference[-1, 0])
            for k in np.flatnonzero(valid):
                tail = np.interp(absolute[k], reference[:, 0], reference[:, j])
                speed = np.interp(absolute[k], reference[:, 0], reference[:, 3 + j])
                distance[k] = tail - rows[k, 1]
                target = EbdTarget(position_m=float(tail), speed_mps=float(speed), kind='gap')
                _, limit = train.safety._etcs_check(float(rows[k, 1]), float(rows[k, 2]),
                                                  train.etcs_curve, [target])
                if limit is not None:
                    sbi[k] = limit
        ceiling = np.flatnonzero(rows[:, 2] >= env.v_max)
        floor = np.flatnonzero(rows[:, 2] < env.v_min)
        crossing = np.flatnonzero(rows[:, 2] > sbi + 1e-6)
        overrun = np.flatnonzero(distance <= 0)
        projections[f'train_{j+1}'] = np.column_stack((absolute, rows[:, 1:], sbi, distance))
        summaries.append(dict(train_one_based=j+1, projection_start_s=origin,
            horizon_s=duration,
            existing_refill_remaining_s=[max(0., ctrl.ab_min_refill_s-
                (ctrl._ab_step-int(last))*ctrl.dt) for last in ctrl._ab_last_release_step],
            existing_ab_source_on=list(map(bool, ctrl._ab_on)),
            initial_mass_mean_kmh=float(np.dot(train.dynamics.vel, train.dynamics.masses_kg)
                                       / train.dynamics.masses_kg.sum()*3.6),
            max_projected_kmh=float(rows[:, 2].max()*3.6),
            min_projected_kmh=float(rows[:, 2].min()*3.6),
            first_route_ceiling_s=float(absolute[ceiling[0]]) if ceiling.size else None,
            first_floor_s=float(absolute[floor[0]]) if floor.size else None,
            first_hindsight_sbi_s=float(absolute[crossing[0]]) if crossing.size else None,
            first_hindsight_target_overrun_s=float(absolute[overrun[0]]) if overrun.size else None,
            hindsight_sbi_points=int(np.isfinite(sbi).sum()),
            initial_net_downhill_kn=float(rows[0, 3]/1000),
            initial_full_ed_kn=float(rows[0, 4]/1000)))
    np.savez_compressed(args.output/'projection.npz', **projections)
    result = dict(scope='Diagnostic centroid screen only, not controller or safety acceptance',
        assumptions=['Immediate full ED, zero traction and zero residual air',
                     'Fixed relative vehicle positions; native grade/resistance/ED curves',
                     'Leader reference is archived future motion, unavailable online',
                     'No SBI extrapolation outside archived reference; no coupler prediction'],
        state_manifest=manifest, reference_sha256=hashes, dt_s=args.dt,
        metadata=json.loads((args.state_dir/'result.json').read_text(encoding='utf-8'))['metadata'],
        horizon_s=[t['horizon_s'] for t in summaries],
        columns=['absolute_time_s', 'head_m', 'speed_mps', 'net_downhill_n', 'ed_n',
                 'acceleration_mps2', 'hindsight_sbi_mps', 'hindsight_target_distance_m'], trains=summaries,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
