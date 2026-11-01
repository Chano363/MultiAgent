"""Classify instantaneous ED-only authority from archived native force samples."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source = json.loads(args.audit.read_text(encoding='utf-8'))
    rows = []
    for sample in source['samples']:
        trains = []
        for train in sample['trains']:
            # All values are positive magnitudes except signed along-track gravity.
            demand = train['gravity_kn']-train['resistance_kn']-train['air_braking_kn']
            cap = train['native_ed_capacity_kn']
            if demand < -1.e-6:
                mode = 'decelerates_even_with_zero_ed'
            elif demand > cap+1.e-6:
                mode = 'accelerates_even_with_full_ed'
            else:
                mode = 'instantaneous_ed_equilibrium_possible'
            mass = train['mass_t']*1000
            trains.append(dict(train=train['train'], equilibrium_ed_kn=demand,
                available_ed_interval_kn=[0., cap], classification=mode,
                instantaneous_accel_interval_mps2=[(demand-cap)*1000/mass, demand*1000/mass]))
        rows.append(dict(time_s=sample['time_s'], trains=trains))
    result = dict(scope='Sparse end-sample feasibility audit; no phase optimization or safety guarantee',
        equation='M*a = G_down - R - B_air - E; E_equilibrium = G_down - R - B_air',
        limitations=['Instantaneous authority does not certify a 50s hold or 222s recharge interval',
                     'Negative required ED would need positive traction or less air, not stronger ED',
                     'Classification uses existing native model, not a replacement locomotive curve'],
        samples=rows,
        source_sha256={str(args.audit): hashlib.sha256(args.audit.read_bytes()).hexdigest()},
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    peak = min(rows, key=lambda x: abs(x['time_s']-source['peak_spread_time_s']))
    print(json.dumps(peak, indent=2))


if __name__ == '__main__':
    main()
