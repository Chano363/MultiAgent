from pathlib import Path
import hashlib,json,openpyxl
root=Path(r'D:\Codex\Documents\Train\controller_pressure_20261014')
p=Path(r'E:\wx\xwechat_files\wxid_zo4ng1tx19se22_84f2\temp\RWTemp\2026-10\6de70b565c621fbbb30d056284634dbe\朔黄铁路_完整线路信息表_表3表4补充版.xlsx')
w=openpyxl.load_workbook(p,data_only=True,read_only=True)
limits=[]
for i,r in enumerate(w['统一线路表'].iter_rows(values_only=True),1):
    if i>2 and isinstance(r[1],(float,int)) and isinstance(r[3],(float,int)):
        if not limits or r[3]!=limits[-1]['limit_kmh']:
            limits.append(dict(km=r[1],limit_kmh=r[3],source_row=i))
data=dict(source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),origin_km=15.9,end_km=65.5,limits=limits,reference_cycles=[dict(start_km=21,release_window_km=[25,25],release_speed_kmh=33),dict(start_km=28,release_window_km=[40,42],release_speed_kmh=60,conflict='Main sheet K40 conditional release; table3 K42 station release'),dict(start_km=46,release_window_km=[64,65],release_speed_kmh=55)],not_applied=['50 kPa mapping','fixed ED forces','50 s ED hold','hard release at reference positions'])
(root/'route_operating_reference_03.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
s=Path(r'F:\列车大创xmc\multi-agent\traffic_rl_project\src\environments\train_fleet_env.py').read_text(encoding='utf-8')
prefix='\n_ROUTE_REFERENCE = '+repr(data)+'\n\ndef _route_limits(tr, global_cap):\n    entries = _ROUTE_REFERENCE["limits"]\n    km = 15.9 + tr.dynamics.pos / 1000.0\n    limits = np.array([entries[max(0, np.searchsorted([e["km"] for e in entries], float(x), side="right") - 1)]["limit_kmh"] / 3.6 for x in km])\n    current = min(global_cap, float(np.min(limits)))\n    tr.line_speed_limit_mps = current\n    tr.safety.max_speed_mps = current\n    head = float(tr.dynamics.pos[0])\n    targets = []\n    for j, e in enumerate(entries):\n        position = (e["km"] - 15.9) * 1000.0\n        if j and head < position <= 49600 and e["limit_kmh"] < entries[j-1]["limit_kmh"]:\n            targets.append(EbdTarget(position_m=position, speed_mps=min(global_cap,e["limit_kmh"]/3.6), kind="speed"))\n    return current, targets\n\n'
needle='            final_edab, _ = ctrl.get_action_decomposed('
assert s.count(needle)==1
s=s.replace(needle,'            route_limit, route_targets = _route_limits(tr, self.v_max)\n            tr.set_etcs_targets([t for t in tr.etcs_targets if t.kind != "speed"] + route_targets)\n            v_bound_max = min(v_bound_max, route_limit - self.v_max)\n'+needle)
s += prefix
(root/'route_limits_baseline_03.py').write_text(s,encoding='utf-8')
old='if gap_err > self.LEAN_CHASE_DEADBAND_M:'
new='if (gap_err > self.LEAN_CHASE_DEADBAND_M and not (ctrl._cyclic_braking and np.any(tr.dynamics._air_brake_active & ~tr.dynamics._air_brake_releasing))):'
assert s.count(old)==1
(root/'route_phase_candidate_03.py').write_text(s.replace(old,new),encoding='utf-8')
print('limit transitions',len(limits));print('source sha256',data['sha256']);print('data saved',root/'route_operating_reference_03.json')

