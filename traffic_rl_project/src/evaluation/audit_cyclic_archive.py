"""Read-only audit of archived single-train requested and physical air events."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def segments(times, values):
    values = np.asarray(values)
    starts = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1]
    ends = np.r_[starts[1:], len(values)]
    dt = float(np.median(np.diff(times)))
    return [dict(start_s=float(times[a]), end_s=float(times[b-1]),
                 duration_s=float(times[b-1]-times[a]+dt), value=values[a].item())
            for a, b in zip(starts, ends)]


def audit(root):
    trajectory = root / 'run' / 'trajectory.npz'
    solver = json.loads((root / 'solver_result.json').read_text(encoding='utf-8'))
    result = json.loads((root / 'run' / 'result.json').read_text(encoding='utf-8'))
    with np.load(trajectory, allow_pickle=False) as data:
        t = data['rows'][:, 0]
        if data['vehicle_speeds_mps'].shape[1] != 1:
            raise ValueError('Single-train archive required')
        request = data['commands'][:, 0, 1]
        command = data['ab_command_to_physics'][:, 0]
        count = data['ab_source_count_to_physics'][:, 0]
        speeds = data['vehicle_speeds_mps'][:, 0, :] * 3.6
        request_segments = segments(t, request)
        # New-source records, not every repeated command while the valve holds.
        # In decomposed control ab_sources overrides global ab_command, which
        # intentionally remains RELEASE even while a source applies CYCLIC.
        # The archive stores source count, not source-notch tuples: do not infer
        # the accepted source notch from that global fallback field.
        admitted = count > 0
        rising = np.flatnonzero(admitted & ~np.r_[False, admitted[:-1]])
        air_events = []
        for i in rising:
            air_events.append(dict(time_s=float(t[i]), fallback_command=str(command[i]),
                controller_request=float(request[i]),
                physical_head_notch=str(data['physical_ab'][i, 0, 0]),
                source_count=int(count[i]), mean_speed_kmh=float(speeds[i].mean()),
                predecision_refill_elapsed_s=float(data['predecision_refill_elapsed_s'][i, 0, 0])
                    if data['predecision_refill_elapsed_s'].ndim == 3
                    else float(np.asarray(data['predecision_refill_elapsed_s'][i]).flat[0])))
        return dict(
            scope='Archived single-train prefix; request events are not physical refill proof',
            trajectory_sha256=hashlib.sha256(trajectory.read_bytes()).hexdigest(),
            duration_s=float(t[-1]), head_m=float(data['heads'][-1, 0]),
            tail_m=float(data['tails'][-1, 0]),
            mean_speed_range_kmh=[float(speeds.mean(axis=1).min()), float(speeds.mean(axis=1).max())],
            max_vehicle_speed_kmh=float(speeds.max()),
            control_sample_peak_kn=float(np.abs(data['coupler_interface_force_n']).max()/1000),
            internal_microstep_peak_kn=solver['numerical']['live']['internal_peak_kn'],
            request_segments=request_segments, admitted_source_intervals=air_events,
            physical_command_segments=segments(t, command),
            physical_head_notch_segments=segments(t, data['physical_ab'][:, 0, 0]),
            safety_event_counts_by_recorded_column=data['safety_rule_counts'].sum(axis=(0, 1)).tolist(),
            safety_column_names=result['metadata'].get('actuator_diagnostic', {}).get('safety_rule_order'),
            diagnostic_stop_reason=result['summary'].get('diagnostic_stop_reason'),
            solver_status=solver['status'],
            note='Source count takes priority over fallback command. Exact source-notch tuples were not archived. '
                 'A 140 kPa request is not automatically ATP: inspect safety and physical notch events.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.archive)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
