"""Record the production fleet control path; export diagnostics, not paper claims."""
import argparse
import json
import sys
import subprocess
import hashlib
import os
import copy
import pickle
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.environments.train_env import CONSIST_PRESETS
from src.metadata import build_metadata
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment, PROFILES
from src.train_dynamics.braking import notch_from_throttle
from src.physics_governance import official_entry_guard, official_world_config


def capture_admission_state(train_env, controller):
    """Observe the upcoming decision without advancing its clocks or veto history."""
    peak = float(np.abs(train_env.dynamics.coupler_interface_forces()).max())
    elapsed = [(controller._ab_step + 1 - step) * controller.dt
               for step in controller._ab_last_release_step]
    return {
        'predecision_coupler_peak_kn': peak / 1000.0,
        'predecision_max_vehicle_kmh': float(train_env.dynamics.vel.max() * 3.6),
        'predecision_new_source_veto': bool(train_env.safety.ab_new_source_veto(
            train_env._state_snapshot())),
        'predecision_controller_ratio_allowed': bool(
            peak < controller.AB_ADD_SOURCE_MAX_RATIO * controller.coupler_force_limit_n),
        'predecision_refill_elapsed_s': np.asarray(elapsed),
        'predecision_refill_ready': np.asarray(elapsed) >= controller.ab_min_refill_s,
        'predecision_ab_on': np.asarray(controller._ab_on, dtype=bool).copy(),
    }


def main():
    official_entry_guard(__file__)
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--config', type=Path,
                    default=Path('configs/experiments/formation_ed_ab_3train_1plus1.yaml'),
                    help='Experiment YAML whose env_cfg seeds the diagnostic environment')
    ap.add_argument('--override', action='append', default=[], metavar='KEY=VALUE',
                    help='Override one env_cfg key (repeatable); true/false/int/float inferred')
    ap.add_argument('--steps', type=int, default=900)
    ap.add_argument('--stop-on-coupler-kn', type=float,
                    help='Diagnostic early stop after exceeding this force; does not alter safety limits')
    ap.add_argument('--stop-file', type=Path,
                    help='Archive completed steps when this file exists at a step boundary')
    ap.add_argument('--stop-on-infeasible-release', action='store_true',
                    help='Archive and stop after a release forecast fails at the existing speed floor')
    ap.add_argument('--save-native-release-state', action='store_true',
                    help='Save trusted local full single-train state for matched release sensitivity')
    ap.add_argument('--trains', type=int, default=1)
    ap.add_argument('--consist-preset', choices=sorted(CONSIST_PRESETS),
                    help='Explicit diagnostic consist; otherwise use main configuration')
    ap.add_argument('--grade', type=float, default=-12.0)
    ap.add_argument('--speed', type=float, default=80.0)
    ap.add_argument('--train-speeds-kmh', type=float, nargs='+',
                    help='Optional initial speed per train, in formation order')
    ap.add_argument('--fleet-env-source', type=Path,
                    help='Replay an archived fleet adapter; current physics remains shared')
    ap.add_argument('--profile', choices=sorted(PROFILES), help='Use a registered route instead of constant grade')
    ap.add_argument('--start-m', type=float, default=0.0, help='Translate the whole formation along the route')
    ap.add_argument('--gap-offset-m', type=float, default=0.0, help='Additional initial gap per adjacent train pair')
    ap.add_argument('--finish-m', type=float, help='Stop when the last vehicle of every train passes this route position')
    ap.add_argument('--ed-recovery-rate', type=float, help='Diagnostic override; zero disables ED recovery limiting')
    ap.add_argument('--ed-recovery-scope', choices=('all', 'coupler'), default='all')
    ap.add_argument('--ed-grade-feedforward', action='store_true')
    ap.add_argument('--ed-physics-availability', action='store_true')
    ap.add_argument('--ed-prelimit', action='store_true')
    ap.add_argument('--ed-baseline-projection', choices=('single', 'legacy'), help='Isolate original baseline ED protection')
    ap.add_argument('--anticipate-etcs', action='store_true',
                    help='Experimental rule ceiling from the existing ETCS service curve')
    frozen = ap.add_mutually_exclusive_group()
    frozen.add_argument('--controller-ref', help='Frozen git ref for before/after replay; physical model stays current')
    frozen.add_argument('--controller-source', type=Path, help='Replay an archived controller source snapshot')
    ap.add_argument('--reuse', action='store_true', help='Summarize saved trajectories without rerunning physics')
    ap.add_argument('--metadata-file', default='result.json', help='Alternative result filename, preserving original metadata')
    args = ap.parse_args()
    if args.stop_on_coupler_kn is not None and (
            not np.isfinite(args.stop_on_coupler_kn) or args.stop_on_coupler_kn <= 0):
        ap.error('stop-on-coupler-kn must be finite and positive')
    if args.steps < 3 or args.trains < 1:
        ap.error('steps must be >=3 and trains must be >=1')
    if args.save_native_release_state and (args.trains != 1 or args.reuse):
        ap.error('Native release state export requires a fresh single-train run')
    if not np.isfinite(args.gap_offset_m) or args.gap_offset_m < 0:
        ap.error('gap-offset-m must be finite and nonnegative')
    if args.train_speeds_kmh is not None and (
            len(args.train_speeds_kmh) != args.trains
            or not np.all(np.isfinite(args.train_speeds_kmh))
            or min(args.train_speeds_kmh) < 0):
        ap.error('train-speeds-kmh must contain one finite nonnegative speed per train')
    args.output.mkdir(parents=True, exist_ok=args.reuse)
    if args.reuse and (args.output / 'result.json').exists():
        archived = json.loads((args.output / 'result.json').read_text(encoding='utf-8'))['metadata']
        protocol = archived.get('diagnostic_protocol', {})
        defaults = {'stop_on_coupler_kn': None, 'ed_prelimit': False, 'ed_physics_availability': False, 'consist_preset': None, 'profile': None, 'start_m': 0.0, 'finish_m': None,
                    'ed_recovery_rate': None, 'ed_baseline_projection': None, 'gap_offset_m': 0.0,
                    'train_speeds_kmh': None, 'anticipate_etcs': False, 'ed_recovery_scope': 'all',
                    'ed_grade_feedforward': False, 'stop_on_infeasible_release': False}
        for key in ('stop_on_coupler_kn', 'ed_prelimit', 'ed_physics_availability', 'consist_preset', 'profile', 'start_m', 'finish_m', 'speed', 'trains', 'grade', 'steps',
                    'ed_recovery_rate', 'ed_recovery_scope', 'ed_grade_feedforward', 'ed_baseline_projection', 'gap_offset_m', 'train_speeds_kmh', 'anticipate_etcs', 'stop_on_infeasible_release'):
            if key in protocol or key in defaults:
                if getattr(args, key) != protocol.get(key, defaults.get(key)):
                    raise ValueError(f'Cannot relabel saved trajectory: {key} differs from archived protocol')
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg']
    # 【2026-10-14 运营口径标定】env_cfg 键级覆盖（bool/int/float/str 类型推断），
    # 覆盖结果随 metadata.env_cfg 归档留痕。
    for item in args.override:
        if '=' not in item:
            ap.error(f'--override expects KEY=VALUE, got: {item}')
        key, raw = item.split('=', 1)
        if raw.strip().lower() in ('true', 'false'):
            value = raw.strip().lower() == 'true'
        elif raw.strip().lower() in ('none', 'null'):
            value = None      # 恢复"未配置"语义（如速度门=None=旧行为）
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw
        config[key] = value
    config.update(num_trains=args.trains, max_steps=args.steps,
                  start_randomization={'enabled': False})
    if args.consist_preset:
        config['consist_preset'] = args.consist_preset
    if args.profile:
        config['grade_profile'] = args.profile
    fleet_source = Path('src/environments/train_fleet_env.py').read_text(encoding='utf-8')
    entry_source = Path(__file__).read_text(encoding='utf-8')
    if args.reuse:
        frozen_entry = args.output / 'diagnostic_source.py'
        entry_source = frozen_entry.read_text(encoding='utf-8') if frozen_entry.exists() else None
    train_source = Path('src/environments/train_env.py').read_text(encoding='utf-8')
    dynamics_source = Path('src/train_dynamics/train.py').read_text(encoding='utf-8')
    etcs_source = Path('src/train_dynamics/etcs_braking.py').read_text(encoding='utf-8')
    fleet_cls = TrainFleetEnv
    if args.fleet_env_source:
        fleet_source = args.fleet_env_source.read_text(encoding='utf-8')
        namespace = {'__name__': 'frozen_fleet_adapter'}
        exec(compile(fleet_source, '<frozen_fleet_adapter>', 'exec'), namespace)
        fleet_cls = namespace['TrainFleetEnv']
        if '_frozen_train_source' in namespace:
            train_source = namespace['_frozen_train_source']
    env = fleet_cls(config)
    source_path = 'src/controllers/multi_loco_controller.py'
    source = Path(source_path).read_text(encoding='utf-8')
    if args.controller_ref or args.controller_source:
        if args.controller_source:
            source = args.controller_source.read_text(encoding='utf-8')
        else:
            source = subprocess.check_output(['git', 'show', f'{args.controller_ref}:traffic_rl_project/{source_path}'], encoding='utf-8')
        namespace = {'__name__': 'frozen_controller'}
        exec(compile(source, '<frozen_controller>', 'exec'), namespace)
        cls = namespace['MultiLocoController']
        import inspect
        # Explicit fleet config wins for the two wired ED flags. Other trial
        # options retain frozen-source defaults, rather than inheriting today's
        # controller defaults and silently erasing an archived experiment.
        parameters = inspect.signature(cls).parameters
        trial_options = {
            'ed_prelimit', 'ed_physics_availability', 'ed_recovery_rate_per_s',
            'ed_recovery_scope', 'ed_grade_feedforward',
            'ed_baseline_projection', 'anticipate_etcs'}
        configured_flags = {'ed_grade_feedforward', 'ed_prelimit'} & config.keys()
        env.multi_loco_controllers = [
            cls(**{name: getattr(controller, name) for name in parameters
                   if name not in trial_options or name in configured_flags})
            for controller in env.multi_loco_controllers]
    if args.ed_recovery_rate is not None:
        if args.controller_ref or args.controller_source or not np.isfinite(args.ed_recovery_rate) or args.ed_recovery_rate < 0:
            raise ValueError('Recovery override requires current controller and a finite nonnegative value')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_recovery_rate_per_s = args.ed_recovery_rate
    if args.ed_baseline_projection is not None:
        if args.controller_ref or args.controller_source:
            raise ValueError('Baseline projection override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_baseline_projection = args.ed_baseline_projection
    if args.ed_grade_feedforward:
        if args.controller_ref or args.controller_source:
            raise ValueError('Grade feedforward override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_grade_feedforward = True
    if args.ed_physics_availability:
        if args.controller_ref or args.controller_source:
            raise ValueError('Availability override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_physics_availability = True
    if args.ed_prelimit:
        if args.controller_ref or args.controller_source:
            raise ValueError('Prelimit override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_prelimit = True
    if args.ed_recovery_scope != 'all':
        if args.controller_ref or args.controller_source:
            raise ValueError('Recovery scope override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.ed_recovery_scope = args.ed_recovery_scope
    if args.anticipate_etcs:
        if args.controller_ref or args.controller_source:
            raise ValueError('ETCS anticipation override requires current controller')
        for ctrl in env.multi_loco_controllers:
            ctrl.anticipate_etcs = True
    env.reset(seed=0, options={'speed': args.speed / 3.6})
    for i, tr in enumerate(env.trains):
        tr.dynamics.set_initial(pos=tr.dynamics.pos + args.start_m - i * args.gap_offset_m,
                                vel=(np.full(tr.num_vehicles, args.train_speeds_kmh[i] / 3.6)
                                     if args.train_speeds_kmh is not None else tr.dynamics.vel))
        env._train_heads[i] = float(tr.dynamics.pos[0])
        if not args.profile:
            tr.dynamics.set_grade_profile(GradeProfile(segments=[GradeSegment(0, args.grade)]))
    initial_heads = np.array([tr.dynamics.pos[0] for tr in env.trains])
    initial_head_speeds = np.array([tr.dynamics.vel[0] for tr in env.trains])
    detail = {'heads': [], 'tails': [], 'head_speed': [], 'max_vehicle_speed': [],
              'ab_active': [], 'subenv_safety_events': [], 'subenv_overspeed_steps': [],
              'physical_loco_ed': [], 'physical_loco_traction': [],
              'ab_command_to_physics': [], 'ab_source_count_to_physics': [],
              'cyclic_braking': [], 'safety_rule_counts': [], 'air_brake_segment': [],
              'coupler_interface_force_n': [], 'loco_ed_force_n': [],
              'vehicle_air_force_n': [], 'vehicle_positions_m': [],
              'vehicle_speeds_mps': [], 'brake_pressure_coefficient': [],
              'air_release_fraction': [], 'effective_pressure_coefficient': [],
              'air_releasing': [], 'controller_release_force_target_kn': [],
              'controller_ed_hold_steps': []}
    admission_keys = tuple(capture_admission_state(env.trains[0], env.multi_loco_controllers[0]))
    detail.update({key: [] for key in admission_keys})
    # Observe the actual post-safety actuator inputs without modifying them.
    # Fleet executed_actions are controller requests, not these physical inputs.
    actuator_inputs = [{} for _ in env.trains]
    safety_rules = ('coupler_force_limit', 'min_gap', 'overspeed',
                    'etcs_ebi', 'etcs_permitted')
    if not args.reuse:
        for ti, tr in enumerate(env.trains):
            original_step = tr.dynamics.step_vehicles_ed_ab

            def record_inputs(throttle, ed_throttle, ab_command, *positional,
                              _ti=ti, _tr=tr, _original=original_step, **kwargs):
                actuator_inputs[_ti] = {
                    'ed': np.asarray(ed_throttle)[_tr.loco_indices].copy(),
                    'traction': np.asarray(throttle)[_tr.loco_indices].copy(),
                    'ab_command': ab_command.name if ab_command is not None else 'HOLD',
                    'ab_sources': len(kwargs.get('ab_sources') or []),
                }
                return _original(throttle, ed_throttle, ab_command, *positional, **kwargs)

            tr.dynamics.step_vehicles_ed_ab = record_inputs
    rows, commands, physical_ab = [], [], []
    diagnostic_stop_s = None
    requested_stop_reason = None
    for k in range(0 if args.reuse else args.steps):
        # Check only between completed steps. Never serialize a half-advanced
        # controller/physics state, or label an administrative stop as success.
        if args.stop_file is not None and args.stop_file.exists() and len(rows) >= 3:
            requested_stop_reason = 'requested_stop_file'
            break
        admission = [capture_admission_state(tr, ctrl) for tr, ctrl in
                     zip(env.trains, env.multi_loco_controllers)]
        for key in admission_keys:
            detail[key].append([state[key] for state in admission])
        _, _, term, trunc, info = env.step(np.zeros((env.num_agents, 2)))
        speeds = [float(np.mean(tr.dynamics.vel)) for tr in env.trains]
        peak = max(float(np.max(np.abs(tr.dynamics.coupler_interface_forces()))) for tr in env.trains)
        cmds = np.asarray(info['executed_actions']).copy()
        commands.append(cmds)
        physical_ab.append([[n.value for n in tr.dynamics.air_brake_state()] for tr in env.trains])
        detail['heads'].append([tr.dynamics.pos[0] for tr in env.trains])
        detail['tails'].append([tr.dynamics.pos[-1] for tr in env.trains])
        detail['head_speed'].append([tr.dynamics.vel[0] for tr in env.trains])
        detail['max_vehicle_speed'].append([np.max(tr.dynamics.vel) for tr in env.trains])
        detail['ab_active'].append([tr.dynamics._air_brake_active.copy() for tr in env.trains])
        detail['brake_pressure_coefficient'].append([tr.dynamics._brake_pressure.copy() for tr in env.trains])
        detail['air_release_fraction'].append([tr.dynamics._air_brake_release_frac.copy() for tr in env.trains])
        detail['effective_pressure_coefficient'].append([
            tr.dynamics._brake_pressure * tr.dynamics._air_brake_release_frac
            * tr.dynamics._air_brake_active for tr in env.trains])
        detail['air_releasing'].append([tr.dynamics._air_brake_releasing.copy() for tr in env.trains])
        detail['subenv_safety_events'].append([tr._safety_events for tr in env.trains])
        detail['subenv_overspeed_steps'].append([tr._overspeed_violations for tr in env.trains])
        detail['physical_loco_ed'].append([actuator_inputs[i]['ed'] for i in range(env.num_trains)])
        detail['physical_loco_traction'].append([actuator_inputs[i]['traction'] for i in range(env.num_trains)])
        detail['coupler_interface_force_n'].append([
            tr.dynamics.coupler_interface_forces().copy() for tr in env.trains])
        detail['vehicle_positions_m'].append([tr.dynamics.pos.copy() for tr in env.trains])
        detail['vehicle_speeds_mps'].append([tr.dynamics.vel.copy() for tr in env.trains])
        step_ed_forces = []
        for ti, tr in enumerate(env.trains):
            full_ed = np.zeros(tr.num_vehicles)
            full_ed[tr.loco_indices] = actuator_inputs[ti]['ed']
            step_ed_forces.append(tr.dynamics._electric_braking_forces(full_ed)[tr.loco_indices])
        detail['loco_ed_force_n'].append(step_ed_forces)
        detail['vehicle_air_force_n'].append([
            tr.dynamics._air_braking_forces().copy() for tr in env.trains])
        detail['ab_command_to_physics'].append([actuator_inputs[i]['ab_command'] for i in range(env.num_trains)])
        detail['ab_source_count_to_physics'].append([actuator_inputs[i]['ab_sources'] for i in range(env.num_trains)])
        detail['cyclic_braking'].append([c._cyclic_braking for c in env.multi_loco_controllers])
        detail['controller_release_force_target_kn'].append([
            float(value) if (value := getattr(c, '_release_force_hold_kn', None)) is not None
            else np.nan for c in env.multi_loco_controllers])
        detail['controller_ed_hold_steps'].append([
            c._ed_hold_steps for c in env.multi_loco_controllers])
        detail['air_brake_segment'].append([tr.dynamics._brake_segment for tr in env.trains])
        detail['safety_rule_counts'].append([
            [sum(ev.get('rule') == rule for ev in tr.safety.last_events)
             for rule in safety_rules] for tr in env.trains])
        rows.append([k * env.dt + env.dt, *speeds, peak,
                     info['coupler_limit_violations'], info['safety_events'], info.get('gap_min_m', 0)])
        if k % 100 == 0:
            print(f'step={k+1} head={detail["heads"][-1][0]:.1f}m peak={peak/1000:.1f}kN', flush=True)
        if not np.all(np.isfinite(rows[-1][:-1])):
            raise RuntimeError('Nonfinite physical trajectory; diagnostic aborted')
        if (args.stop_on_coupler_kn is not None and diagnostic_stop_s is None
                and peak > args.stop_on_coupler_kn * 1000.0):
            diagnostic_stop_s = float(rows[-1][0])
        # Three samples are needed for acceleration/jerk accounting. Record the
        # first crossing even when it happens before those samples are available.
        if diagnostic_stop_s is not None and len(rows) >= 3:
            break
        if args.stop_on_infeasible_release and len(rows) >= 3:
            failed = any(event.get('event') == 'release_feasibility'
                         and event.get('at_floor') and not event.get('feasible', True)
                         for ctrl in env.multi_loco_controllers
                         for event in getattr(ctrl, '_ed_guard_events', []))
            if failed:
                requested_stop_reason = 'release_infeasible_at_floor'
                break
        if term or trunc or (args.finish_m is not None and min(detail['tails'][-1]) >= args.finish_m):
            break
    if args.reuse:
        # allow_pickle only for our legacy Enum arrays, never external assets.
        with np.load(args.output / 'trajectory.npz', allow_pickle=True) as saved:
            rows, commands = saved['rows'], saved['commands']
            physical_ab = np.vectorize(lambda n: n.value if hasattr(n, 'value') else n)(saved['physical_ab'])
            detail = {name: saved[name] for name in detail if name in saved.files}
            if 'initial_heads' in saved.files:
                initial_heads = saved['initial_heads']
        if (args.output / 'controller_source.py').exists():
            source = (args.output / 'controller_source.py').read_text(encoding='utf-8')
    else:
        rows, commands = np.asarray(rows), np.asarray(commands)
        (args.output / 'diagnostic_source.py').write_bytes(entry_source.encode('utf-8'))
        (args.output / 'train_dynamics_source.py').write_bytes(dynamics_source.encode('utf-8'))
        (args.output / 'etcs_braking_source.py').write_bytes(etcs_source.encode('utf-8'))
        np.savez_compressed(args.output / 'trajectory.npz', rows=rows, commands=commands,
                            physical_ab=np.asarray(physical_ab), initial_heads=initial_heads,
                            initial_head_speeds=initial_head_speeds,
                            **{name: np.asarray(value) for name, value in detail.items()})
        (args.output / 'controller_source.py').write_bytes(source.encode('utf-8'))
        (args.output / 'fleet_env_source.py').write_bytes(fleet_source.encode('utf-8'))
        (args.output / 'train_env_source.py').write_bytes(train_source.encode('utf-8'))
        np.savetxt(args.output / 'trajectory.csv', rows, delimiter=',',
                   header='time_s,' + ','.join(f'speed_{i}_mps' for i in range(args.trains)) + ',force_N,violations,safety_events,gap_min_m', comments='')
        if args.save_native_release_state:
            from src.evaluation.release_feasibility import clone_native_prediction_env
            from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
            branch = clone_native_prediction_env(env.trains[0])
            try:
                # Controller functions stay in the frozen source, never in a
                # dynamic-class pickle. No state is inferred from NPZ arrays.
                payload = pickle.dumps({'train_env': branch,
                    'controller_state': copy.deepcopy(env.multi_loco_controllers[0].__dict__),
                    'controls': {'v_max': env.v_max, 'v_min': env.v_min,
                                 'v_max_adj': 0.0, 'v_min_adj': 0.0}},
                    protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                branch.close()
            (args.output / 'native_release_state.pkl').write_bytes(payload)
            (args.output / 'native_release_state.json').write_text(json.dumps({
                'format': 'trusted-local-native-release-state-v1',
                'sha256': hashlib.sha256(payload).hexdigest(),
                'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'native_source_sha256': native_source_hashes(),
                'elapsed_s': float(rows[-1, 0]), 'env_cfg': config,
                'scope': 'single-train sensitivity only, not a complete fleet restart',
                'numpy_version': np.__version__, 'python_version': list(sys.version_info[:2]),
            }, indent=2), encoding='utf-8')
    velocity = rows[:, 1:1 + args.trains]
    accel = np.diff(velocity, axis=0) / env.dt
    jerk = np.diff(accel, axis=0) / env.dt
    summary = dict(steps=len(rows), speed_min_kmh=float(velocity.min()*3.6),
                   speed_max_kmh=float(velocity.max()*3.6), peak_kn=float(rows[:, 1+args.trains].max()/1000),
                   jerk_rms=float(np.sqrt(np.mean(jerk**2))),
                   jerk_peak=float(np.abs(jerk).max()),
                   command_switches=int(np.sum(np.abs(np.diff(commands[:,:,1], axis=0)) > 1e-6)),
                   violations=int(rows[-1, 2+args.trains]),
                   safety_events=int(rows[-1, 3+args.trains]))
    if args.reuse:
        if args.stop_on_coupler_kn is not None:
            crossings = np.flatnonzero(rows[:, 1 + args.trains] > args.stop_on_coupler_kn * 1000.0)
            diagnostic_stop_s = float(rows[crossings[0], 0]) if crossings.size else None
    summary['diagnostic_stop_reason'] = ('coupler_threshold' if diagnostic_stop_s is not None
                                         else requested_stop_reason)
    summary['diagnostic_first_crossing_s'] = diagnostic_stop_s
    # Diagnose executed actuator discontinuities, rather than attributing
    # speed oscillations to pre-safety controller requests alone.
    if 'physical_loco_ed' in detail:
        ed_delta = np.diff(np.asarray(detail['physical_loco_ed']), axis=0)
        summary['physical_ed_change_rms_per_s'] = float(
            np.sqrt(np.mean((ed_delta / env.dt) ** 2)))
        summary['physical_ed_max_step_increase'] = float(max(0.0, ed_delta.max()))
        summary['physical_ed_max_step_decrease'] = float(max(0.0, -ed_delta.min()))
    if args.trains > 1:
        summary['min_gap_m'] = float(rows[:, -1].min())
        summary['negative_gap_steps'] = int(np.sum(rows[:, -1] < 0))
    notches = np.vectorize(lambda x: notch_from_throttle(x).value)(commands[:, :, 1])
    summary['requested_notch_switches'] = int(np.sum(notches[1:] != notches[:-1]))
    head_notches = np.asarray(physical_ab)[:, :, 0]
    # The engine retains the last notch even after release. This is a stored
    # setting, not an assertion about active cylinder pressure/braking force.
    summary['stored_head_notch_switches'] = int(np.sum(head_notches[1:] != head_notches[:-1]))
    if 'heads' in detail:
        summary.update(elapsed_s=float(rows[-1, 0]),
                       mean_speed_kmh=float(np.mean(velocity)*3.6),
                       distance_leader_m=float(np.asarray(detail['heads'])[-1, 0]-initial_heads[0]),
                       leader_end_m=float(np.asarray(detail['heads'])[-1, 0]),
                       last_tail_end_m=float(np.min(np.asarray(detail['tails'])[-1])),
                       max_vehicle_speed_kmh=float(np.max(detail['max_vehicle_speed'])*3.6),
                       overspeed_train_steps=int(np.sum(np.asarray(detail['subenv_overspeed_steps'])[-1])),
                       subenv_safety_events=int(np.sum(np.asarray(detail['subenv_safety_events'])[-1])),
                       full_route_completed=bool(args.finish_m is not None and min(np.asarray(detail['tails'])[-1]) >= args.finish_m))
    world = official_world_config(env_cfg=config)
    world['physics'].update(grade_profile=args.profile or 'constant_grade', dt=env.dt,
                            v_max_mps=env.v_max, v_min_mps=env.v_min,
                            target_speed_mps=env.target_speed, target_gap_m=env.target_gap,
                            max_accel=env.max_accel, coupler_force_limit_n=env.coupler_force_limit_n)
    runtime_physics = [{'simcase': tr.dynamics.simcase,
                        'enable_cyclic_degrade': tr.dynamics.enable_cyclic_degrade,
                        'tail_pressure_kpa': tr.dynamics.tail_pressure_kpa} for tr in env.trains]
    assert all(p['simcase'] == 'official' and p['enable_cyclic_degrade'] for p in runtime_physics)
    meta = build_metadata(str(Path.cwd()), 'official', world, 0, __file__,
                          extra={'diagnostic_protocol': vars(args) | {'output': str(args.output),
                                                                    'config': str(args.config),
                                                                    'stop_file': str(args.stop_file) if args.stop_file else None,
                                                                    'fleet_env_source': str(args.fleet_env_source) if args.fleet_env_source else None,
                                                                    'controller_source': str(args.controller_source) if args.controller_source else None},
                                 'grade_override_permille': None if args.profile else args.grade,
                                 'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                                 'diagnostic_entry_sha256': (hashlib.sha256(entry_source.encode('utf-8')).hexdigest()
                                                             if entry_source is not None else None),
                                 'controller_sha256_format': 'UTF-8 source text with LF line endings',
                                 'fleet_env_sha256': hashlib.sha256(fleet_source.encode('utf-8')).hexdigest(),
                                 'train_env_sha256': hashlib.sha256(train_source.encode('utf-8')).hexdigest(),
                                 'train_dynamics_sha256': hashlib.sha256(dynamics_source.encode('utf-8')).hexdigest(),
                                 'etcs_braking_sha256': hashlib.sha256(etcs_source.encode('utf-8')).hexdigest(),
                                 'etcs_runtime': {
                                     'speed_profile': env.etcs_curve.speed_profile,
                                     'emergency_build_up_s': env.etcs_curve.brake_build_up_s,
                                     'service_build_up_s': env.etcs_curve.service_build_up_s,
                                 },
                                 'controller_ref': args.controller_ref or ('source-file' if args.controller_source else 'working-tree'),
                                 'controller_runtime': [{'ed_recovery_rate_per_s': getattr(c, 'ed_recovery_rate_per_s', None),
                                                         'ed_physics_availability': getattr(c, 'ed_physics_availability', False),
                                                         'ed_prelimit': getattr(c, 'ed_prelimit', False),
                                                         'ed_grade_feedforward': getattr(c, 'ed_grade_feedforward', False),
                                                         'ed_recovery_scope': getattr(c, 'ed_recovery_scope', 'all'),
                                                         'anticipate_etcs': getattr(c, 'anticipate_etcs', False),
                                                         'ed_baseline_projection': getattr(c, 'ed_baseline_projection', None),
                                                         'ab_min_refill_s': c.ab_min_refill_s,
                                                         'ab_min_hold_s': c.ab_min_hold_s,
                                                         'ed_exit_decay_rate_per_s': getattr(c, 'ed_exit_decay_rate_per_s', None),
                                                         'sbi_exit_margin_mps': getattr(c, 'sbi_exit_margin_mps', None),
                                                         **({'predictive_ed_guard_events': c._ed_guard_events}
                                                            if hasattr(c, '_ed_guard_events') else {})}
                                                        for c in env.multi_loco_controllers],
                                 'runtime_physics': runtime_physics,
                                 'actuator_diagnostic': {
                                     'physical_ed_unit': 'fraction, post-safety input; not force',
                                     'force_sample': 'post-step state model evaluation in N; not step-integrated force',
                                     'coupler_sign': 'positive = forward force on preceding vehicle',
                                     'loco_indices': [list(tr.loco_indices) for tr in env.trains],
                                     'safety_rule_order': list(safety_rules),
                                     'controller_requests': 'commands, before environment safety',
                                     'release_force_target': 'last stored model-force target in kN, '
                                     'before controller/safety projection; NaN means unavailable',
                                 },
                                 'numerical_runtime': {'numpy_version': np.__version__,
                                     'thread_environment': {name: os.environ.get(name) for name in
                                         ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}},
                                 'env_cfg': config,
                                 'tracked_diff': subprocess.check_output(['git', 'diff', '--stat'], encoding='utf-8'),
                                 'purpose': 'controller diagnostic; zero RL modulation, not a paper main-table evaluation'})
    if args.reuse and (args.output / 'result.json').exists():
        previous_record = json.loads((args.output / 'result.json').read_text(encoding='utf-8'))
        previous = previous_record['metadata']
        if diagnostic_stop_s is None:
            summary['diagnostic_stop_reason'] = previous_record['summary'].get('diagnostic_stop_reason')
        # Recomputing statistics must not relabel the archived controller as
        # today's working tree (especially for intermediate diagnostic trials).
        for key in ('etcs_runtime', 'etcs_braking_sha256', 'train_dynamics_sha256', 'controller_sha256', 'controller_ref', 'controller_runtime', 'fleet_env_sha256', 'train_env_sha256',
                    'numerical_runtime', 'tracked_diff', 'actuator_diagnostic'):
            if key in previous:
                meta[key] = previous[key]
        if 'actuator_diagnostic' not in previous:
            meta['actuator_diagnostic'] = None
        if 'train_env_sha256' not in previous:
            meta['train_env_sha256'] = None
        if 'train_dynamics_sha256' not in previous:
            meta['train_dynamics_sha256'] = None
        if 'etcs_braking_sha256' not in previous:
            meta['etcs_braking_sha256'] = None
        if 'etcs_runtime' not in previous:
            meta['etcs_runtime'] = None
        if 'fleet_env_sha256' not in previous:
            meta['fleet_env_sha256'] = None
            meta['fleet_env_provenance_note'] = 'Legacy archive did not record a fleet environment source hash'
        if 'controller_runtime' not in previous:
            meta['controller_runtime'] = None
            meta['controller_runtime_note'] = (
                'Legacy archive did not record runtime parameters; '
                'the currently constructed controller must not relabel them')
        meta['summary_recompute_command'] = meta['diagnostic_protocol']
        meta['diagnostic_protocol'] = previous.get('diagnostic_protocol', meta['diagnostic_protocol'])
        meta['metadata_correction'] = 'Canonical official world config; original trajectory and controller identity preserved'
    (args.output / args.metadata_file).write_text(json.dumps({'summary': summary, 'metadata': meta}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
    env.close()


if __name__ == '__main__':
    main()
