"""Mechanical air-work audit for linked native branches; no thermal inference."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def load_branch(directories):
    blocks, sources, previous, native, origin = [], {}, None, None, None
    for directory in directories:
        meta = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        initial = meta['initial_fleet_manifest']
        if native is not None and initial['native_source_sha256'] != native:
            raise ValueError('Native sources differ within branch')
        if previous is not None and initial['sha256'] != previous['sha256']:
            raise ValueError('Checkpoint chain is broken')
        native = initial['native_source_sha256']
        if origin is None:
            origin = initial['sha256']
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            speed, air = a['vehicle_speeds_mps'], b['vehicle_air_force_n']
            if speed.shape != air.shape or not np.isfinite(speed).all() or not np.isfinite(air).all():
                raise ValueError('Finite matched vehicle arrays required')
            power = np.maximum(0., -air*speed)
            blocks.append(dict(time=a['rows'][:, 0], power=power.sum(axis=2),
                source=b['ab_source_on'].reshape(len(speed), 3, -1).any(axis=2),
                spread=np.ptp(speed.mean(axis=2)*3.6, axis=1)))
        previous = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'fleet_state.json', 'trajectory.npz', 'telemetry.npz'):
            sources[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    arrays = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    ticks = np.rint(arrays['time']*10).astype(np.int64)
    if np.any(np.diff(ticks) != 1):
        raise ValueError('Unique contiguous 0.1s samples required')
    return arrays, ticks, native, origin, sources


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, nargs='+', required=True)
    p.add_argument('--candidate', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    a, ak, an, ao, ap = load_branch(args.baseline)
    b, bk, bn, bo, bp = load_branch(args.candidate)
    if an != bn or ao != bo:
        raise ValueError('Common physical sources and initial checkpoint required')
    shared, ai, bi = np.intersect1d(ak, bk, return_indices=True)
    if not len(shared) or shared[0] != ak[0] or shared[0] != bk[0] or np.any(np.diff(shared) != 1):
        raise ValueError('Contiguous common prefix required')
    result = dict(scope='Native mechanical work only; not wheel temperature or route acceptance',
        window_s=[float(shared[0]/10), float(shared[-1]/10)],
        samples=len(shared), integrated_duration_s=len(shared)*.1,
        source_sha256={**ap, **bp},
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for name, data, ix in [('baseline', a, ai), ('candidate', b, bi)]:
        work = data['power'][ix].sum(axis=0)*.1/1e6
        result[name] = dict(air_work_mj_by_train=work.tolist(),
            air_work_mj_total=float(work.sum()),
            source_on_s_by_train=(data['source'][ix].sum(axis=0)*.1).tolist(),
            mean_speed_spread_kmh=float(data['spread'][ix].mean()),
            peak_speed_spread_kmh=float(data['spread'][ix].max()),
            peak_speed_spread_time_s=float(data['time'][ix][np.argmax(data['spread'][ix])]))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    main()
