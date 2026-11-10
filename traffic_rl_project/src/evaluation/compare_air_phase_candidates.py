"""Compare candidate forecasts as a screening step, never coupler acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint


def score(data, indices, lengths, reference, dt):
    speeds = data['mean_mps'][indices]
    heads = data['heads_m'][indices]
    gaps = heads[:, :-1]-lengths[:-1]-heads[:, 1:]
    power = np.maximum(0., -data['vehicle_air_force_n'][indices]*speeds[:, :, None])
    return dict(min_predicted_mean_kmh=float(speeds.min()*3.6),
        max_predicted_mean_kmh=float(speeds.max()*3.6),
        gap_mae_m=float(abs(gaps-reference).mean()),
        mean_speed_spread_kmh=float(np.ptp(speeds*3.6, axis=1).mean()),
        min_gap_m=float(gaps.min()), end_gaps_m=gaps[-1].tolist(),
        end_mean_kmh=(speeds[-1]*3.6).tolist(),
        air_work_mj_by_train=(power.sum(axis=(0, 2))*dt/1e6).tolist(),
        air_work_mj_total=float(power.sum()*dt/1e6),
        native_safety_events=int(data['safety_count'][indices].max()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--origin', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    env, origin = load_fleet_checkpoint(args.origin)
    lengths = np.asarray([t.dynamics.pos[0]-t.dynamics.pos[-1] for t in env.trains])
    reference, dt = env._formation_ref_gap(), env.dt
    env.close()
    results = [json.loads((d/'result.json').read_text(encoding='utf-8'))
               for d in (args.baseline, args.candidate)]
    for result in results:
        manifest = result['source_manifest']
        if manifest['sha256'] != origin['sha256'] or manifest['native_source_sha256'] != origin['native_source_sha256']:
            raise ValueError('Candidate origin or native sources differ')
    a, b = [np.load(d/'forecast.npz') for d in (args.baseline, args.candidate)]
    keys = [np.rint(x['time']*10).astype(np.int64) for x in (a, b)]
    if any(np.any(np.diff(k) != 1) for k in keys):
        raise ValueError('Contiguous control grid required')
    shared, ai, bi = np.intersect1d(*keys, return_indices=True)
    if not len(shared) or shared[0] != keys[0][0] or shared[0] != keys[1][0]:
        raise ValueError('A shared origin is required')
    sa, sb = score(a, ai, lengths, reference, dt), score(b, bi, lengths, reference, dt)
    full = (results[0]['summary']['stop_reason'] == 'horizon_completed'
            and results[1]['summary']['stop_reason'] == 'horizon_completed'
            and len(keys[0]) == len(keys[1]))
    nondominated = (full and sb['native_safety_events'] == 0
        and sb['gap_mae_m'] <= sa['gap_mae_m']
        and sb['mean_speed_spread_kmh'] <= sa['mean_speed_spread_kmh']
        and sb['air_work_mj_total'] <= sa['air_work_mj_total'])
    changed_actions = int(np.any(a['commands'][ai] != b['commands'][bi], axis=(1, 2)).sum())
    strictly_better = any(sb[key] < sa[key]-1.e-8 for key in
                         ('gap_mae_m', 'mean_speed_spread_kmh', 'air_work_mj_total'))
    ready_for_native = nondominated and strictly_better and changed_actions > 0
    result = dict(scope='Approximate forecast ranking only; frozen relative geometry, not native coupler acceptance',
        window_s=[float(shared[0]/10), float(shared[-1]/10)], samples=len(shared),
        reference_gap_m=reference, baseline=sa, candidate=sb,
        equal_completed_horizons=full,
        no_worse_on_all_three_screening_costs=nondominated,
        changed_action_samples=changed_actions,
        strictly_improves_at_least_one_cost=strictly_better,
        passes_effect_and_cost_screen=ready_for_native,
        next_step=('Native mechanical validation still required; no automatic adoption' if ready_for_native
                   else 'No effective intervention or no strict cost improvement' if not changed_actions or not strictly_better
                   else 'Tradeoff or incomplete horizon: do not claim overall improvement'),
        source_sha256={str(d/n):hashlib.sha256((d/n).read_bytes()).hexdigest()
                       for d in (args.baseline, args.candidate) for n in ('result.json', 'forecast.npz')},
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    main()
