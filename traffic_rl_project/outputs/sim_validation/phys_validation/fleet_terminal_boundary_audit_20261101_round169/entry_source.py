"""Audit an existing native terminal run and distinguish map extrapolation."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np


def main():
    base = Path('outputs/sim_validation/phys_validation')
    trial = base/'fleet_joint_phase_terminal150_20261101_round168'
    root = base/'fleet_terminal_boundary_audit_20261101_round169'
    root.mkdir(exist_ok=False)
    (root/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    status = dict(status='waiting_for_existing_terminal_trial')
    (root/'progress.json').write_text(json.dumps(status), encoding='utf-8')
    began = time.monotonic()
    try:
        while not (trial/'result.json').exists():
            if (root/'STOP').exists():
                status['status'] = 'requested_audit_stop_native_unchanged'
                return
            if time.monotonic()-began > 43200:
                raise TimeoutError('Native terminal trial not completed within 12h')
            time.sleep(20)
        native = json.loads((trial/'result.json').read_text(encoding='utf-8'))
        with np.load(trial/'trajectory.npz') as a, np.load(trial/'telemetry.npz') as b:
            times, pos, v = a['rows'][:, 0], a['vehicle_positions_m'], a['vehicle_speeds_mps']
            inside = np.max(pos, axis=(1, 2)) <= 49600.
            groups = {}
            for label, mask in [('all_vehicles_inside_map', inside), ('some_vehicles_beyond_map', ~inside)]:
                if mask.any():
                    groups[label] = dict(samples=int(mask.sum()),
                        window_s=[float(times[mask][0]), float(times[mask][-1])],
                        accepted_micro_peak_kn=float(a['rows'][mask, 5].max()/1000),
                        min_vehicle_kmh=float(v[mask].min()*3.6),
                        max_vehicle_kmh=float(v[mask].max()*3.6),
                        safety_events=int(b['safety_events_delta'][mask].sum()))
            crossings = [float(times[ix[0]]) if len(ix := np.flatnonzero(pos[:, j, 0] > 49600.))
                         else None for j in range(3)]
        status.update(status='boundary_audit_completed', native_summary=native['summary'],
            first_recorded_head_crossing_s=crossings, groups=groups,
            scope='Control-endpoint boundary classification at 0.1s resolution; last-grade extension is not new surveyed route data',
            metadata=native['metadata'],
            source_sha256={str(trial/n):hashlib.sha256((trial/n).read_bytes()).hexdigest()
                           for n in ('metadata.json', 'trajectory.npz', 'telemetry.npz', 'result.json')})
        report = Path('D:/Codex/Documents/Train/controller_takeover_20261017/编队追赶与缓解保持接口修复_20261031.md')
        lines = ['', '### 2026-11-01：末段模型验证与线路边界核对', '',
            f"后续原生停止原因：{native['summary']['stop_reason']}，末时刻{native['summary']['last_time_s']:.1f}s。",
            f'三列车头首次归档越过49600m时刻：{crossings}。',
            '分组按0.1秒控制采样末态位置；延长段沿用模型最后坡度，不是新增真实线路数据。']
        for label, values in groups.items():
            lines += ['', f'{label}: {json.dumps(values, ensure_ascii=False)}']
        lines += ['', '未从失败状态续跑；局部验证不等于全程从零起点、所有循环和实际线路均已通过。',
                  f'原始证据：{root.resolve()}。']
        with report.open('a', encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
        status['document'] = str(report)
    except BaseException as exc:
        status.update(status='audit_failed', error=repr(exc))
        raise
    finally:
        (root/'result.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
        (root/'progress.json').write_text(json.dumps(status, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
