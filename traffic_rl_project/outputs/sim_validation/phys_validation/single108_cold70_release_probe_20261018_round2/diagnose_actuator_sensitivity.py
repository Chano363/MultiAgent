"""Native short-horizon actuator counterfactuals at matched running states.

These are open-loop actuator holds, not controller performance measurements.
Each branch preserves the same pneumatic, integration and safety history.
"""
import argparse
import copy
import hashlib
import inspect
import itertools
import json
import pickle
import re
from pathlib import Path
import sys

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.environments.train_env import CONSIST_PRESETS
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def capture_vehicle_state(dynamics, forces=None):
    """Read-only numerical signals, not a complete pneumatic replay checkpoint."""
    return {
        'vehicle_positions_m': dynamics.pos.copy(),
        'vehicle_speeds_mps': dynamics.vel.copy(),
        'integration_acceleration_mps2': dynamics._acc0.copy(),
        'coupler_interface_force_n': (dynamics.coupler_interface_forces()
                                      if forces is None else forces).copy(),
        'vehicle_grade': np.asarray(dynamics.grade).copy(),
        'brake_pressure_coefficient': dynamics._brake_pressure.copy(),
        'air_release_fraction': dynamics._air_brake_release_frac.copy(),
        'ab_active': dynamics._air_brake_active.copy(),
        'air_releasing': dynamics._air_brake_releasing.copy(),
        'brake_segment': np.asarray(dynamics._brake_segment, dtype=np.int64),
        'stored_air_brake_notch': np.asarray([notch.value for notch in dynamics.air_brake_state()]),
    }


def load_sequence_plan(path, horizon_s, num_locomotives=2):
    """Validate diagnostic requests; arbitrary file contents are not executed."""
    entries = json.loads(Path(path).read_text(encoding='utf-8'))['sequences']
    return validate_sequence_entries(entries, horizon_s, num_locomotives)


def validate_sequence_entries(entries, horizon_s, num_locomotives=2):
    """Validate names, actuator ranges and the complete simulation budget."""
    result = {}
    for entry in entries:
        name = entry['name']
        depths = np.asarray(entry['ED_depths'], dtype=float)
        durations = np.asarray(entry['durations_s'], dtype=float)
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in result:
            raise ValueError('Unique safe sequence names required')
        if (depths.ndim != 2 or depths.shape[1] != num_locomotives
                or durations.shape != (len(depths),) or not len(depths)
                or not np.all(np.isfinite(depths)) or np.any((depths < 0) | (depths > 1))
                or not np.all(np.isfinite(durations)) or np.any(durations <= 0)
                or not np.isclose(durations.sum(), horizon_s, rtol=0, atol=1e-8)):
            raise ValueError('Finite bounded ED blocks and positive durations covering horizon required')
        result[name] = (depths, durations)
    if not result:
        raise ValueError('At least one sequence required')
    return result


def actuator_hold_variants(actions):
    """Preserve legacy two-loco probes and support single-unit diagnostics."""
    actions = np.asarray(actions)
    if actions.ndim != 2 or actions.shape[1] != 2 or actions.shape[0] < 1:
        raise ValueError("Expected nonempty locomotive ED/AB actions")
    n = len(actions)
    variants = {'baseline_hold': actions[:, 0].copy(), 'coast': np.zeros(n),
                'both_full': np.ones(n)}
    if n == 2:
        variants.update(head_only=np.array([1.0, 0.0]), middle_only=np.array([0.0, 1.0]))
    elif n == 1:
        variants.update(quarter=np.array([0.25]), half=np.array([0.5]),
                        three_quarters=np.array([0.75]))
    return variants


def counterfactual_air_variants(variants, controller, cyclic_enabled):
    """Paired shadow branches only; never relax the running fleet's gates."""
    if controller.num_locomotives != 1 or not cyclic_enabled:
        raise ValueError('Shadow CYCLIC comparison requires one released, refill-ready locomotive')
    ready = ((controller._ab_step - controller._ab_last_release_step[0])
             * controller.dt >= controller.ab_min_refill_s)
    if any(controller._ab_on) or not ready:
        raise ValueError('Shadow CYCLIC comparison requires one released, refill-ready locomotive')
    expanded, requests = {}, {}
    for name, depths in variants.items():
        for suffix, request in [('noair', 0.0), ('cyclic50', -0.05)]:
            key = f'{name}__{suffix}'
            expanded[key] = depths
            requests[key] = request
    return expanded, requests


def validate_shadow_air_blocks(requests, durations, elapsed_since_release, refill_s):
    """Validate every planned reapplication against the unchanged refill clock."""
    values = np.asarray(requests, dtype=float)
    durations = np.asarray(durations, dtype=float)
    if (values.shape != durations.shape or values.ndim != 1 or not values.size
            or not np.all(np.isfinite(values))
            or not np.all(np.isin(values, [0.0, -0.05]))
            or not np.all(np.isfinite(durations)) or np.any(durations <= 0)
            or not np.isfinite(elapsed_since_release) or elapsed_since_release < 0
            or not np.isfinite(refill_s) or refill_s < 0):
        raise ValueError('Shadow air plan requires finite 0/-0.05 requests and positive durations')
    elapsed = float(elapsed_since_release)
    was_on = False
    for request, duration in zip(values, durations):
        on = request < 0
        if on and not was_on and elapsed < refill_s - 1e-8:
            raise ValueError('Shadow air plan attempts reapplication before refill completes')
        if not on and was_on:
            elapsed = 0.0
        elapsed += duration
        was_on = on
    return values


def native_source_hashes():
    """Dependencies of the cached native physics/safety object, not the evaluator."""
    files = set(Path('src/train_dynamics').rglob('*.py'))
    files.update(Path('src/controllers').rglob('*.py'))
    files.update(Path(name) for name in (
        'src/physics_config.py', 'src/safety_layer.py',
        'src/environments/train_env.py', 'src/environments/train_fleet_env.py'))
    return {str(path).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def validate_checkpoint_compatibility(manifest, cfg, source_hash, sources, time_s,
                                      start_m, speed_kmh):
    """Reject incompatible provenance before deserializing a trusted local object."""
    if (manifest.get('format') != 'locally-generated-native-shadow-checkpoint-v1'
            or manifest.get('env_cfg') != cfg
            or manifest.get('controller_sha256') != source_hash
            or manifest.get('native_source_sha256') != sources
            or manifest.get('numpy_version') != np.__version__
            or manifest.get('python_version') != list(sys.version_info[:2])):
        raise ValueError('Native checkpoint code, configuration or runtime differs')
    for key, expected in [('time_s', time_s), ('start_m', start_m), ('speed_kmh', speed_kmh)]:
        value = manifest.get(key)
        if not isinstance(value, (int, float)) or not np.isclose(value, expected, rtol=0, atol=1e-8):
            raise ValueError(f'Native checkpoint {key} differs')


def sequence_slew_rates(entry, durations, default):
    rates = np.asarray(entry.get('ED_ramp_per_s', np.full(len(durations), default)), dtype=float)
    if rates.shape != np.asarray(durations).shape or not np.all(np.isfinite(rates)) or np.any(rates <= 0):
        raise ValueError('ED_ramp_per_s must give one finite positive command slew per block')
    return rates


def main():
    official_entry_guard(__file__)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--controller-source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--start-m', type=float, default=26633.5)
    ap.add_argument('--speed-kmh', type=float, default=70)
    ap.add_argument('--times-s', type=float, nargs='+', default=[10, 11, 12])
    ap.add_argument('--horizon-s', type=float, default=2)
    ap.add_argument('--sequence-grid', action='store_true',
                    help='Two ED blocks over the horizon; native safety and AB retained')
    ap.add_argument('--sequence-grid-mode', choices=('full', 'corner_probes'), default='full',
                    help='corner_probes: 16 extremes plus centre and two prior transfer probes')
    ap.add_argument('--ed-ramp-per-s', type=float, default=0.5,
                    help='Engineering trial command slew, not a physical parameter')
    ap.add_argument('--record-vehicle-state', action='store_true',
                    help='Save per-vehicle and per-interface numerical signals')
    ap.add_argument('--sequence-file', type=Path,
                    help='JSON diagnostic ED blocks with explicit durations, replacing the grid')
    ap.add_argument('--counterfactual-cyclic-air', action='store_true',
                    help='Shadow paired no-air/50kPa branches; bypass new-source veto ONLY in the air clone')
    ap.add_argument('--shadow-air-plan', action='store_true',
                    help='Explicit AB_requests per ED block; copied branches only, refill enforced')
    ap.add_argument('--save-native-checkpoint', action='store_true',
                    help='Archive this locally generated full native state for later trusted replay')
    ap.add_argument('--native-checkpoint', type=Path,
                    help='Reuse ONLY our trusted local native checkpoint, with code/config/hash verification')
    args = ap.parse_args()
    if args.sequence_file and args.sequence_grid:
        ap.error('Use either a sequence file or a sequence grid')
    if args.counterfactual_cyclic_air and not args.sequence_file:
        ap.error('Shadow air comparison requires an explicit ED sequence plan')
    if args.shadow_air_plan and (not args.sequence_file or args.counterfactual_cyclic_air):
        ap.error('Explicit shadow air plans require a sequence file and cannot use paired-air mode')
    if args.sequence_grid_mode != 'full' and not args.sequence_grid:
        ap.error('A sequence probe mode requires --sequence-grid')
    if (not np.all(np.isfinite([args.start_m, args.speed_kmh, args.horizon_s, *args.times_s]))
            or not np.isfinite(args.ed_ramp_per_s) or args.ed_ramp_per_s <= 0
            or args.horizon_s <= 0 or min(args.times_s) <= 0):
        ap.error('Finite inputs and positive horizon/checkpoint times required')
    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))['env_cfg']
    nlocos = len(CONSIST_PRESETS[cfg["consist_preset"]]().locomotive_indices)
    custom_sequences = (load_sequence_plan(args.sequence_file, args.horizon_s, nlocos)
                        if args.sequence_file else None)
    plan_entries = ({entry['name']: entry for entry in
                     json.loads(args.sequence_file.read_text(encoding='utf-8'))['sequences']}
                    if args.sequence_file else {})
    if not args.shadow_air_plan and any('AB_requests' in entry for entry in plan_entries.values()):
        ap.error('AB_requests must be explicitly enabled with --shadow-air-plan')
    if args.shadow_air_plan and (nlocos != 1 or not cfg.get('cyclic_notch_50', False)):
        ap.error('Explicit shadow air plans require one locomotive and the CYCLIC interface')
    sequenced = args.sequence_grid or custom_sequences is not None
    cfg.update(num_trains=1, max_steps=10000, start_randomization={'enabled': False}, eval_mode=True)
    if custom_sequences is not None:
        for name, (_, durations) in custom_sequences.items():
            sequence_slew_rates(plan_entries[name], durations, args.ed_ramp_per_s)
    cached_state, cache_manifest = None, None
    if args.native_checkpoint:
        if len(args.times_s) != 1:
            ap.error('A native checkpoint supports exactly its single archived time')
        checkpoint_path = args.native_checkpoint.resolve()
        allowed_root = (Path.cwd() / 'outputs/sim_validation/phys_validation').resolve()
        if not checkpoint_path.is_relative_to(allowed_root):
            ap.error('Use only our locally generated checkpoint inside the validation archive')
        cache_manifest = json.loads(checkpoint_path.with_suffix('.json').read_text(encoding='utf-8'))
        validate_checkpoint_compatibility(
            cache_manifest, cfg, hashlib.sha256(args.controller_source.read_text(encoding='utf-8').encode()).hexdigest(),
            native_source_hashes(), args.times_s[0], args.start_m, args.speed_kmh)
        payload = checkpoint_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != cache_manifest.get('sha256'):
            raise ValueError('Native checkpoint checksum differs; do not deserialize')
        # This flag is exclusively for our own trusted artifacts, never arbitrary external pickle.
        cached_state = pickle.loads(payload)
        clock = cached_state['controller_clock']
        if (not np.isclose(cached_state['train_env'].dynamics.time, args.times_s[0], rtol=0, atol=1e-7)
                or not np.isclose(clock['_ab_step'] * clock['dt'], args.times_s[0], rtol=0, atol=1e-7)):
            raise ValueError('Native checkpoint payload time differs from its manifest')
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.controller_source.read_text(encoding='utf-8')
    (args.output / 'controller_source.py').write_text(source, encoding='utf-8')
    if args.sequence_file:
        (args.output / 'sequence_plan.json').write_bytes(args.sequence_file.read_bytes())
    namespace = {'__name__': 'sensitivity_frozen_controller'}
    exec(compile(source, '<sensitivity_controller>', 'exec'), namespace)
    cls = namespace['MultiLocoController']
    hashes = {}
    for filename in ['src/environments/train_fleet_env.py', 'src/environments/train_env.py',
                     'src/train_dynamics/train.py', 'src/train_dynamics/braking.py',
                     'src/safety_layer.py', 'src/train_dynamics/grade_profile.py', __file__]:
        code = Path(filename).read_text(encoding='utf-8')
        hashes[str(filename)] = hashlib.sha256(code.encode()).hexdigest()
        (args.output / Path(filename).name).write_text(code, encoding='utf-8')
    metadata = build_metadata(str(Path.cwd()), 'official', official_world_config(env_cfg=cfg), 0,
                              __file__, extra={'env_cfg': cfg, 'source_sha256': hashes,
                              'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                              'sequence_plan_sha256': (hashlib.sha256(args.sequence_file.read_bytes()).hexdigest()
                                                       if args.sequence_file else None),
                              'protocol': {k: str(v) if isinstance(v, Path) else v
                                           for k, v in vars(args).items()},
                              'scope': 'open-loop actuator sensitivity, not a policy evaluation',
                              'shadow_new_source_veto_bypass': args.counterfactual_cyclic_air or args.shadow_air_plan,
                              'native_checkpoint_provenance': cache_manifest,
                              'shadow_admission_note': 'If enabled, only the copied air branch ignores '
                              'new-source veto. ED protection and ATP remain; not a safety acceptance.'})
    result = {'metadata': metadata, 'checkpoints': []}
    out = args.output / 'result.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    env = TrainFleetEnv(cfg)
    try:
        original = env.multi_loco_controllers[0]
        env.multi_loco_controllers[0] = cls(**{k: getattr(original, k)
                                               for k in inspect.signature(cls).parameters})
        env.reset(seed=0, options={'speed': args.speed_kmh / 3.6})
        if cached_state is not None:
            env.trains[0].close()
            env.trains[0] = cached_state['train_env']
            for key, value in cached_state['controller_clock'].items():
                setattr(env.multi_loco_controllers[0], key, copy.deepcopy(value))
            dyn = env.trains[0].dynamics
        else:
            dyn = env.trains[0].dynamics
            dyn.set_initial(pos=dyn.pos + args.start_m, vel=dyn.vel.copy())
        env._train_heads[0] = float(dyn.pos[0])
        checkpoints = {int(round(t / env.dt)) for t in args.times_s}
        horizon = int(np.ceil(args.horizon_s / env.dt))
        replay_steps = sorted(checkpoints) if cached_state is not None else range(1, max(checkpoints) + 1)
        for k in replay_steps:
            if k == 1 or k % 100 == 0:
                print(f'rebuilding_native_history step={k}/{max(checkpoints)}', flush=True)
            if cached_state is None:
                _, _, _, _, info = env.step(np.zeros((env.num_agents, 2)))
            if k not in checkpoints:
                continue
            actions = (np.asarray(cached_state['actions']).copy() if cached_state is not None
                       else np.asarray(info['executed_actions']).copy())
            if args.record_vehicle_state:
                np.savez_compressed(args.output / f'step{k}_initial_vehicle_state.npz',
                                    **capture_vehicle_state(dyn), vehicle_masses_kg=dyn.masses_kg)
            if args.save_native_checkpoint:
                ctrl = env.multi_loco_controllers[0]
                timing = {key: copy.deepcopy(getattr(ctrl, key)) for key in (
                    '_ab_step', '_ab_on', '_ab_last_release_step', '_ab_last_apply_step',
                    'ab_min_refill_s', 'dt', 'num_locomotives')}
                checkpoint_file = args.output / f'step{k}_native_checkpoint.pkl'
                # Only write our own full objects. Never load arbitrary external pickle files.
                payload = pickle.dumps({'train_env': env.trains[0], 'actions': actions,
                                        'controller_clock': timing}, protocol=pickle.HIGHEST_PROTOCOL)
                checkpoint_file.write_bytes(payload)
                checkpoint_file.with_suffix('.json').write_text(json.dumps({
                    'format': 'locally-generated-native-shadow-checkpoint-v1',
                    'time_s': k * env.dt,
                    'sha256': hashlib.sha256(payload).hexdigest(),
                    'source_sha256': hashes,
                    'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                    'native_source_sha256': native_source_hashes(),
                    'env_cfg': cfg, 'start_m': args.start_m, 'speed_kmh': args.speed_kmh,
                    'numpy_version': np.__version__, 'python_version': list(sys.version_info[:2]),
                    'scope': 'trusted local native shadow only; not a full fleet/controller restart',
                }, indent=2), encoding='utf-8')
            variants = actuator_hold_variants(actions)
            if args.sequence_grid:
                if len(actions) != 2:
                    raise ValueError('Sequence grid requires exactly two locomotives')
                depths = list(itertools.product((0.0, 0.5, 1.0), repeat=2))
                variants = {f'sequence_{a}_{b}': np.asarray([first, second])
                            for a, first in enumerate(depths)
                            for b, second in enumerate(depths)}
                if args.sequence_grid_mode == 'corner_probes':
                    probes = set(itertools.product((0.0, 1.0), repeat=4))
                    probes.update([(0.5, 0.5, 0.5, 0.5), (0.0, 1.0, 0.5, 0.5),
                                   (1.0, 0.0, 0.5, 0.0)])
                    variants = {name: value for name, value in variants.items()
                                if tuple(value.ravel()) in probes}
            if custom_sequences is not None:
                variants = {name: item[0] for name, item in custom_sequences.items()}
            shadow_requests = {}
            if args.counterfactual_cyclic_air:
                variants, shadow_requests = counterfactual_air_variants(
                    variants, env.multi_loco_controllers[0], cfg.get('cyclic_notch_50', False))
            planned_air = {}
            if args.shadow_air_plan:
                ctrl = env.multi_loco_controllers[0]
                if any(ctrl._ab_on):
                    raise ValueError('Explicit shadow air plans must start after a controller release')
                elapsed = (ctrl._ab_step - ctrl._ab_last_release_step[0]) * ctrl.dt
                planned_air = {name: validate_shadow_air_blocks(
                    plan_entries[name]['AB_requests'], custom_sequences[name][1],
                    elapsed, ctrl.ab_min_refill_s) for name in variants}
            checkpoint = {'time_s': k * env.dt,
                          'initial_peak_kn': float(np.abs(dyn.coupler_interface_forces()).max()/1000),
                          'variants': {}}
            result['checkpoints'].append(checkpoint)
            for name, depths in variants.items():
                branch = copy.deepcopy(env.trains[0])
                action = actions.copy()
                if shadow_requests:
                    action[:, 1] = shadow_requests[name]
                    if shadow_requests[name] < 0:
                        # Deliberate diagnostic intervention, not production permission.
                        branch.safety.ab_new_source_veto = lambda state: False
                if not sequenced:
                    action[:, 0] = depths
                ends = None
                slew_rates = None
                if custom_sequences is not None:
                    plan_name = name.rsplit('__', 1)[0] if shadow_requests else name
                    durations = custom_sequences[plan_name][1]
                    steps = np.rint(durations / env.dt).astype(int)
                    if np.any(steps < 1) or not np.allclose(steps * env.dt, durations, atol=1e-8, rtol=0):
                        raise ValueError('Sequence durations must be positive multiples of native dt')
                    if steps.sum() != horizon:
                        raise ValueError('Sequence steps must cover the native diagnostic horizon')
                    ends = np.cumsum(steps)
                    slew_rates = sequence_slew_rates(plan_entries[plan_name], durations, args.ed_ramp_per_s)
                physical_inputs = {}
                if planned_air:
                    original_veto = branch.safety.ab_new_source_veto
                    branch.safety.ab_new_source_veto = (
                        lambda state, _action=action, _original=original_veto:
                        False if np.any(_action[:, 1] < 0) else _original(state))
                    original_physics_step = branch.dynamics.step_vehicles_ed_ab

                    def record_physical_inputs(throttle, ed_throttle, ab_command, *positional,
                                               _original=original_physics_step,
                                               _record=physical_inputs,
                                               _indices=branch.loco_indices, **kwargs):
                        _record['physical_loco_ed'] = np.asarray(ed_throttle)[_indices].copy()
                        _record['physical_ab_command'] = np.asarray(
                            ab_command.name if ab_command is not None else 'HOLD')
                        sources = kwargs.get('ab_sources') or []
                        _record['physical_ab_source_notch'] = np.asarray(
                            sources[0][1].name if sources else 'NONE')
                        return _original(throttle, ed_throttle, ab_command, *positional, **kwargs)

                    branch.dynamics.step_vehicles_ed_ab = record_physical_inputs
                previous_ed = actions[:, 0].copy()
                rows = []
                commands = []
                histories = {}
                for j in range(horizon):
                    if j % 100 == 0:
                        print(f'checkpoint={k} variant={name} step={j}/{horizon}', flush=True)
                    if sequenced:
                        block = int(np.searchsorted(ends, j, side='right')) if ends is not None else min(1, (2 * j) // horizon)
                        target = depths[block]
                        delta = (slew_rates[block] if slew_rates is not None else args.ed_ramp_per_s) * env.dt
                        previous_ed += np.clip(target - previous_ed, -delta, delta)
                        action[:, 0] = previous_ed
                        if planned_air:
                            action[:, 1] = planned_air[name][block]
                    commands.append(action.copy())
                    branch.step(action)
                    d = branch.dynamics
                    forces = d.coupler_interface_forces()
                    if args.record_vehicle_state:
                        for key, value in capture_vehicle_state(d, forces).items():
                            histories.setdefault(key, []).append(value)
                        for key, value in physical_inputs.items():
                            histories.setdefault(key, []).append(value.copy())
                    rows.append([(j + 1) * env.dt,
                                 np.abs(forces).max(),
                                 d.vel.max(), d.vel.mean(),
                                 max(0.0, float(forces.max())),
                                 max(0.0, -float(forces.min()))])
                branch.close()
                rows = np.asarray(rows)
                np.savez_compressed(args.output / f'step{k}_{name}.npz', rows=rows,
                                    actions=np.asarray(commands),
                                    **{key: np.stack(value) for key, value in histories.items()})
                checkpoint['variants'][name] = {
                    'ED_depths': np.asarray(depths).tolist(),
                    'peak_kn': float(rows[:, 1].max()/1000),
                    'end_peak_kn': float(rows[-1, 1]/1000),
                    'max_vehicle_kmh': float(rows[:, 2].max()*3.6),
                    'end_mean_kmh': float(rows[-1, 3]*3.6),
                    'max_positive_interface_kn': float(rows[:, 4].max()/1000),
                    'max_negative_interface_kn': float(rows[:, 5].max()/1000)}
                if custom_sequences is not None:
                    checkpoint['variants'][name]['block_durations_s'] = durations.tolist()
                    checkpoint['variants'][name]['ed_command_slew_per_s'] = slew_rates.tolist()
                if shadow_requests:
                    checkpoint['variants'][name].update(
                        shadow_ab_request=shadow_requests[name],
                        new_source_veto_bypassed=shadow_requests[name] < 0,
                        interpretation='counterfactual only; not a controller or safety acceptance')
                if planned_air:
                    checkpoint['variants'][name].update(
                        shadow_ab_requests=planned_air[name].tolist(),
                        new_source_veto_bypassed=True,
                        refill_constraint_s=ctrl.ab_min_refill_s,
                        interpretation='planned shadow intervention; not a controller or safety acceptance')
                out.write_text(json.dumps(result, indent=2), encoding='utf-8')
                print(f'checkpoint={k} completed={len(checkpoint["variants"])}/{len(variants)}', flush=True)
            print(json.dumps(checkpoint), flush=True)
    finally:
        env.close()


if __name__ == '__main__':
    main()
