"""Compare aligned, signed interface traces from the same native checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def compare(reference_dir, candidate_dir):
    runs = [json.loads((p/'result.json').read_text(encoding='utf-8'))
            for p in (reference_dir, candidate_dir)]
    for key in ('native_state_manifest', 'controller_sha256'):
        if runs[0]['metadata'][key] != runs[1]['metadata'][key]:
            raise ValueError('Different input state or controller')
    with (np.load(reference_dir/'interface_trace.npz', allow_pickle=False) as a,
          np.load(candidate_dir/'interface_trace.npz', allow_pickle=False) as b):
        np.testing.assert_array_equal(a['elapsed_s'], b['elapsed_s'])
        force_error = b['force_n'] - a['force_n']
        i, j = np.unravel_index(np.abs(force_error).argmax(), force_error.shape)
        peak_error = np.max(np.abs(b['force_n']), axis=1) - np.max(np.abs(a['force_n']), axis=1)
        k = int(np.abs(peak_error).argmax())
        report = {
            'max_signed_interface_error_kn': float(np.max(np.abs(force_error))/1000),
            'rms_signed_interface_error_kn': float(np.sqrt(np.mean(force_error**2))/1000),
            'max_envelope_error_kn': float(np.max(np.abs(peak_error))/1000),
            'critical_signed_force': {'elapsed_s': float(a['elapsed_s'][i]),
                'interface_one_based': int(j+1),
                'reference_force_kn': float(a['force_n'][i,j]/1000),
                'candidate_force_kn': float(b['force_n'][i,j]/1000),
                'reference_e_m': float(a['deflection_m'][i,j]),
                'candidate_e_m': float(b['deflection_m'][i,j]),
                'reference_dv_mps': float(a['relative_velocity_mps'][i,j]),
                'candidate_dv_mps': float(b['relative_velocity_mps'][i,j])},
            'critical_envelope': {'elapsed_s': float(a['elapsed_s'][k]),
                'reference_interface_one_based': int(np.abs(a['force_n'][k]).argmax()+1),
                'candidate_interface_one_based': int(np.abs(b['force_n'][k]).argmax()+1)},
            'max_deflection_error_m': float(np.max(np.abs(b['deflection_m']-a['deflection_m']))),
            'max_relative_velocity_error_mps': float(np.max(np.abs(
                b['relative_velocity_mps']-a['relative_velocity_mps']))) }
    with (np.load(reference_dir/'balanced.npz', allow_pickle=False) as a,
          np.load(candidate_dir/'balanced.npz', allow_pickle=False) as b):
        np.testing.assert_array_equal(a['rows'][:,0], b['rows'][:,0])
        report['AB_requests_identical'] = bool(np.array_equal(a['rows'][:,4], b['rows'][:,4]))
        report['max_mean_speed_error_kmh'] = float(np.max(np.abs(a['rows'][:,3]-b['rows'][:,3]))*3.6)
    report['scope'] = 'same-state numerical diagnostic, no full-route acceptance'
    report['reference_result'] = str(reference_dir/'result.json')
    report['candidate_result'] = str(candidate_dir/'result.json')
    report['source_sha256'] = {
        str(p/name): hashlib.sha256((p/name).read_bytes()).hexdigest()
        for p in (reference_dir, candidate_dir)
        for name in ('result.json', 'interface_trace.npz', 'balanced.npz')}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.reference, args.candidate)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
