"""Read-only release-state screen using native grade, resistance and ED curves."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint
from src.evaluation.screen_fleet_release import project_full_ed
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.train import AIR_BRAKE_PROPAGATION_SPEED_SERVICE


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    env, manifest = load_fleet_checkpoint(args.state_dir)
    args.output.mkdir(parents=True, exist_ok=False)
    dyn = copy.deepcopy(env.trains[0].dynamics)
    ctrl = env.multi_loco_controllers[0]
    mass = float(dyn.masses_kg.sum())
    velocity = float(np.dot(dyn.vel, dyn.masses_kg)/mass)
    throttle = np.array([float(v.is_locomotive) for v in dyn.consist.vehicles])
    elapsed, records = 0., []
    remaining = [54., 53., 52., 51., 50., 49., 48., 46., 44., 42., 40.]
    reserve = float(dyn.brake_rise_time_by_notch[AirBrakeNotch.CYCLIC]
                    +(dyn.pos[0]-dyn.pos[-1])/AIR_BRAKE_PROPAGATION_SPEED_SERVICE)
    while remaining and elapsed < 600.:
        dyn.vel = np.full(dyn.num_vehicles, velocity)
        if dyn._grade_profile is not None:
            dyn.grade = dyn._grade_profile.grades_for_positions(dyn.pos)
        while remaining and velocity*3.6 <= remaining[0]:
            target = remaining.pop(0)
            projected = project_full_ed(dyn, ctrl.ab_min_refill_s+reserve, .1)
            before_refill = projected[:, 0] <= ctrl.ab_min_refill_s+1e-8
            crossing = np.flatnonzero(projected[:, 2] >= env.v_max)
            records.append(dict(target_kmh=target, predicted_holding_s=elapsed,
                predicted_release_head_m=float(dyn.pos[0]),
                predicted_release_kmh=velocity*3.6,
                max_until_refill_kmh=float(projected[before_refill, 2].max()*3.6),
                max_with_zero_air_build_reserve_kmh=float(projected[:, 2].max()*3.6),
                first_80_after_release_s=None if not len(crossing) else float(projected[crossing[0],0])))
        if not remaining:
            break
        # Quasi-rigid hold: keep the current established AB coefficients; no air-clock reset.
        force = float((dyn._grade_forces()-dyn._resistance_forces()
                       +dyn._air_braking_forces()+dyn._electric_braking_forces(throttle)).sum())
        next_velocity = max(0., velocity+.1*force/mass)
        dyn.pos += .05*(velocity+next_velocity)
        velocity = next_velocity
        elapsed += .1
        if velocity*3.6 < env.v_min*3.6-.1:
            break
    result = dict(scope='Centroid forecast on isolated copy, not a live trajectory or acceptance',
        assumptions=['Holding: full ED and fixed established AB coefficients, translating vehicle positions',
            'After release: instantaneous full ED, zero residual air and zero new air over entire forecast',
            'No coupler motion, actuator transition or following-train trajectory prediction',
            'Zero-air build reserve is a deliberately pessimistic auxiliary screen, not a pneumatic simulation'],
        state_sha256=manifest['sha256'], native_source_sha256=manifest['native_source_sha256'],
        refill_assumption_s=ctrl.ab_min_refill_s, extra_zero_air_build_reserve_s=reserve,
        candidates=records, unreached_targets_kmh=remaining,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'screen.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    env.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
