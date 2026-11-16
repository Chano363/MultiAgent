"""Bounded continuation from our full-fleet experimental checkpoint; no reset."""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter
from contextlib import contextmanager, ExitStack

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.fleet_checkpoint import load_fleet_checkpoint, save_fleet_checkpoint
from src.evaluation.fractional_air_timing import fractional_air_timing
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def recorded_context(samples, numerical):
    """Resume exactly the recorded solver; never silently substitute defaults."""
    if numerical['solver'] == 'newton_analytic_time_error':
        from src.evaluation.error_controlled_mechanics import candidate
        context = candidate(samples, **numerical['settings'])
        if 'following_speed_margin' in numerical.get('source_sha256', {}):
            context = with_recorded_margin(context, numerical)
        elif 'release_budget_guard' in numerical.get('source_sha256', {}):
            context = with_recorded_release_guard(context)
        if 'phase_aware_release' in numerical.get('source_sha256', {}):
            context = with_recorded_phase(context)
        if 'refill_chase_guard' in numerical.get('source_sha256', {}):
            context = with_recorded_refill(context)
        if 'held_air_speed_balance' in numerical.get('source_sha256', {}):
            context = with_recorded_held_air(context)
        if 'held_air_smooth_handoff' in numerical.get('source_sha256', {}):
            context = with_recorded_smooth_handoff(context)
        if 'gap_aware_air_balance' in numerical.get('source_sha256', {}):
            context = with_recorded_gap_aware_air(context)
        if 'formation_traction_slew' in numerical.get('source_sha256', {}):
            context = with_recorded_traction_slew(context)
        if 'formation_release_budget' in numerical.get('source_sha256', {}):
            context = with_recorded_formation_release(context)
        if 'traction_brake_preview' in numerical.get('source_sha256', {}):
            context = with_recorded_traction_preview(context)
        if 'ready_cycle_pacing' in numerical.get('source_sha256', {}):
            context = with_recorded_ready_cycle(context)
        if 'delayed_leader_release' in numerical.get('source_sha256', {}):
            context = with_recorded_delayed_release(context)
        if 'pre_release_chase_exit' in numerical.get('source_sha256', {}):
            context = with_recorded_chase_exit(context)
        if 'dynamic_sbi_upgrade' in numerical.get('source_sha256', {}):
            context = with_recorded_dynamic_upgrade(context)
        if 'preview_sbi_upgrade' in numerical.get('source_sha256', {}):
            context = with_recorded_preview_upgrade(context)
        return context
    if numerical['solver'] == 'newton_analytic':
        return coupled_candidate(samples, numerical_solver=numerical['solver'],
                                 **numerical['settings'])
    raise ValueError('Unsupported recorded experimental solver')


@contextmanager
def with_recorded_preview_upgrade(numerical_context):
    from src.evaluation.preview_sbi_upgrade import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_dynamic_upgrade(numerical_context):
    from src.evaluation.dynamic_sbi_upgrade import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_chase_exit(numerical_context):
    from src.evaluation.pre_release_chase_exit import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_delayed_release(numerical_context):
    from src.evaluation.delayed_leader_release import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_ready_cycle(numerical_context):
    from src.evaluation.ready_cycle_pacing import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_traction_preview(numerical_context):
    from src.evaluation.traction_brake_preview import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_formation_release(numerical_context):
    from src.evaluation.formation_release_budget import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_traction_slew(numerical_context):
    from src.evaluation.formation_traction_slew import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_gap_aware_air(numerical_context):
    from src.evaluation.gap_aware_air_balance import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_smooth_handoff(numerical_context):
    from src.evaluation.held_air_smooth_handoff import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_held_air(numerical_context):
    from src.evaluation.held_air_speed_balance import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_refill(numerical_context):
    from src.evaluation.refill_chase_guard import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_phase(numerical_context):
    from src.evaluation.phase_aware_release import candidate
    with numerical_context, candidate():
        yield


@contextmanager
def with_recorded_margin(numerical_context, numerical):
    from src.evaluation.following_speed_margin import candidate
    guard = (with_recorded_release_guard(numerical_context)
             if 'release_budget_guard' in numerical.get('source_sha256', {}) else numerical_context)
    with guard, candidate():
        yield


@contextmanager
def with_recorded_release_guard(numerical_context):
    from src.evaluation.release_budget_guard import candidate
    with numerical_context, candidate():
        yield


def main():
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    parser.add_argument('--finish-m', type=float)
    parser.add_argument('--stop-on-safety-event', action='store_true')
    parser.add_argument('--checkpoint-below-kmh', type=float)
    parser.add_argument('--checkpoint-train', type=int, default=1)
    parser.add_argument('--one-shot-ab-suppress-train', type=int,
                        help='One-based train index for an isolated, one-cycle AB-release trial')
    parser.add_argument('--one-shot-ab-suppress-below-kmh', type=float,
                        help='Only request the isolated AB release at or below this head speed')
    parser.add_argument('--fractional-air-timing', action='store_true',
                        help='Experimental event-resolved air timing; comparison only, never a restart source')
    parser.add_argument('--post-release-ed-mod-train', type=int,
                        help='One-based train index for a bounded RL-style ED transition probe')
    parser.add_argument('--post-release-ed-mod', type=float,
                        help='ED modulation in [-1, 1] while the bounded transition probe is active')
    parser.add_argument('--post-release-ed-mod-s', type=float,
                        help='Duration in seconds for the bounded ED transition probe')
    parser.add_argument('--on-source-release-ed-mod-train', type=int,
                        help='One-based train index for a bounded ED probe after its normal AB source release')
    parser.add_argument('--on-source-release-ed-mod', type=float,
                        help='ED modulation in [-1, 1] after the first normal AB source release')
    parser.add_argument('--on-source-release-ed-mod-s', type=float,
                        help='Duration in seconds for the normal-release ED transition probe')
    parser.add_argument('--rule-release-transition-s', type=float,
                        help='Temporarily configure the formal rule transition duration for this replay')
    parser.add_argument('--rule-release-transition-ed-mod', type=float,
                        help='Temporarily configure the formal rule ED modulation for this replay')
    parser.add_argument('--rule-etcs-anticipation-level', choices=('sbi', 'p'),
                        help='Temporarily configure the formal ETCS anticipation level for this replay')
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('Positive continuation budget required')
    if args.finish_m is not None and (not np.isfinite(args.finish_m) or args.finish_m <= 0):
        parser.error('Positive finite finish position required')
    if args.checkpoint_below_kmh is not None and (
            not np.isfinite(args.checkpoint_below_kmh) or args.checkpoint_below_kmh <= 0):
        parser.error('Positive finite speed checkpoint required')
    if (args.one_shot_ab_suppress_train is None) != (
            args.one_shot_ab_suppress_below_kmh is None):
        parser.error('One-shot AB suppression requires both train and speed arguments')
    if args.one_shot_ab_suppress_below_kmh is not None and (
            not np.isfinite(args.one_shot_ab_suppress_below_kmh)
            or args.one_shot_ab_suppress_below_kmh <= 0):
        parser.error('Positive finite one-shot AB suppression speed required')
    env, manifest = load_fleet_checkpoint(args.state_dir)
    if not 1 <= args.checkpoint_train <= env.num_trains:
        parser.error('Checkpoint train outside fleet')
    if (args.one_shot_ab_suppress_train is not None and not
            1 <= args.one_shot_ab_suppress_train <= env.num_trains):
        parser.error('One-shot AB suppression train outside fleet')
    if args.fractional_air_timing and any(
            getattr(train.dynamics, 'mid_source_delay_s', 0.0) > 0.0 for train in env.trains):
        parser.error('Fractional air timing does not support delayed middle sources')
    ed_probe_args = (args.post_release_ed_mod_train, args.post_release_ed_mod,
                     args.post_release_ed_mod_s)
    if any(value is not None for value in ed_probe_args):
        if any(value is None for value in ed_probe_args):
            parser.error('Post-release ED probe requires train, modulation, and duration arguments')
        if args.one_shot_ab_suppress_train is None:
            parser.error('Post-release ED probe requires an isolated AB-release trial')
        if not 1 <= args.post_release_ed_mod_train <= env.num_trains:
            parser.error('Post-release ED probe train outside fleet')
        if not np.isfinite(args.post_release_ed_mod) or not -1.0 <= args.post_release_ed_mod <= 1.0:
            parser.error('Post-release ED modulation must be finite and within [-1, 1]')
        if not np.isfinite(args.post_release_ed_mod_s) or args.post_release_ed_mod_s <= 0.0:
            parser.error('Post-release ED probe duration must be positive and finite')
    source_probe_args = (args.on_source_release_ed_mod_train, args.on_source_release_ed_mod,
                         args.on_source_release_ed_mod_s)
    if any(value is not None for value in source_probe_args):
        if any(value is None for value in source_probe_args):
            parser.error('Normal-release ED probe requires train, modulation, and duration arguments')
        if args.post_release_ed_mod_train is not None:
            parser.error('Choose either isolated-release or normal-release ED probe, not both')
        if not 1 <= args.on_source_release_ed_mod_train <= env.num_trains:
            parser.error('Normal-release ED probe train outside fleet')
        if not np.isfinite(args.on_source_release_ed_mod) or not -1.0 <= args.on_source_release_ed_mod <= 1.0:
            parser.error('Normal-release ED modulation must be finite and within [-1, 1]')
        if not np.isfinite(args.on_source_release_ed_mod_s) or args.on_source_release_ed_mod_s <= 0.0:
            parser.error('Normal-release ED probe duration must be positive and finite')
    rule_transition_args = (args.rule_release_transition_s,
                            args.rule_release_transition_ed_mod)
    if any(value is not None for value in rule_transition_args):
        if any(value is None for value in rule_transition_args):
            parser.error('Formal rule transition replay requires duration and modulation arguments')
        if not np.isfinite(args.rule_release_transition_s) or args.rule_release_transition_s < 0.0:
            parser.error('Formal rule transition duration must be finite and nonnegative')
        if (not np.isfinite(args.rule_release_transition_ed_mod)
                or not -1.0 <= args.rule_release_transition_ed_mod <= 0.0):
            parser.error('Formal rule ED modulation must be finite and within [-1, 0]')
        if args.on_source_release_ed_mod_train is not None:
            parser.error('Formal rule transition replay cannot be combined with a normal-release probe')
        for controller in env.multi_loco_controllers:
            controller.ed_release_transition_s = args.rule_release_transition_s
            controller.ed_release_transition_ed_mod = args.rule_release_transition_ed_mod
            controller._ed_release_transition_steps = 0
    if args.rule_etcs_anticipation_level is not None:
        for controller in env.multi_loco_controllers:
            controller.anticipate_etcs = True
            controller.etcs_anticipation_level = args.rule_etcs_anticipation_level
    numerical = manifest['numerical']
    if numerical['solver'] not in ('newton_analytic', 'newton_analytic_time_error'):
        raise ValueError('Unsupported recorded experimental solver')
    origin = json.loads((args.state_dir/'result.json').read_text(encoding='utf-8'))
    env.max_steps = max(env.max_steps, env.steps + args.steps + 1)
    for train in env.trains:
        train.max_steps = max(train.max_steps, train.steps + args.steps + 1)
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = build_metadata(str(Path.cwd()), 'official',
        official_world_config(env_cfg=origin['metadata']['env_cfg']), 0, __file__, extra={
            'env_cfg': origin['metadata']['env_cfg'], 'initial_fleet_manifest': manifest,
            'numerical': numerical, 'steps_budget': args.steps,
            'speed_checkpoint_kmh': args.checkpoint_below_kmh,
            'speed_checkpoint_train': args.checkpoint_train,
            'one_shot_ab_suppress': (None if args.one_shot_ab_suppress_train is None else {
                'train_one_based': args.one_shot_ab_suppress_train,
                'below_kmh': args.one_shot_ab_suppress_below_kmh,
                'scope': 'Isolated existing-AB-source suppression; never changes refill or safety gates',
            }),
            'fractional_air_timing': bool(args.fractional_air_timing),
            'post_release_ed_probe': (None if args.post_release_ed_mod_train is None else {
                'train_one_based': args.post_release_ed_mod_train,
                'rl_style_ed_modulation': args.post_release_ed_mod,
                'duration_s': args.post_release_ed_mod_s,
                'scope': ('Isolated post-release RL-action probe; does not alter the rule controller, '
                          'air model, refill clock, or safety gates'),
            }),
            'normal_release_ed_probe': (None if args.on_source_release_ed_mod_train is None else {
                'train_one_based': args.on_source_release_ed_mod_train,
                'rl_style_ed_modulation': args.on_source_release_ed_mod,
                'duration_s': args.on_source_release_ed_mod_s,
                'scope': ('Isolated normal-source-release RL-action probe; does not alter the rule controller, '
                          'air model, refill clock, or safety gates'),
            }),
            'formal_rule_release_transition': (None if args.rule_release_transition_s is None else {
                'duration_s': args.rule_release_transition_s,
                'ed_modulation': args.rule_release_transition_ed_mod,
                'scope': 'Replay-only configuration of the formal rule; air model and safety gates unchanged',
            }),
            'formal_rule_etcs_anticipation': (None if args.rule_etcs_anticipation_level is None else {
                'level': args.rule_etcs_anticipation_level,
                'scope': 'Replay-only formal ETCS anticipation setting; safety thresholds remain unchanged',
            }),
            'scope': 'Zero-RL bounded fleet continuation, not route or training acceptance'})
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    samples, rows, commands, positions, speeds, forces, pressure, clock = [], [], [], [], [], [], [], []
    air_forces, physical_ed, heads, rear_centers, gaps, safety, modes, holds = [], [], [], [], [], [], [], []
    safety_deltas, event_records = [], []
    source_on, release_steps, refill_remaining, refill_veto_counts = [], [], [], []
    initial_safety_count = sum(int(t._safety_events) for t in env.trains)
    previous_safety_count = initial_safety_count
    one_shot_suppression_applied = False
    post_release_ed_probe_steps = 0
    normal_release_ed_probe_steps = 0
    normal_release_ed_probe_applied = False
    previous_source_state = [list(controller._ab_on) for controller in env.multi_loco_controllers]
    actuator_inputs = [{} for _ in env.trains]
    for ti, tr in enumerate(env.trains):
        original_step = tr.dynamics.step_vehicles_ed_ab
        def record_inputs(throttle, ed_throttle, ab_command, *positional,
                          _ti=ti, _tr=tr, _original=original_step, **kwargs):
            actuator_inputs[_ti] = np.asarray(ed_throttle)[_tr.loco_indices].copy()
            return _original(throttle, ed_throttle, ab_command, *positional, **kwargs)
        tr.dynamics.step_vehicles_ed_ab = record_inputs
    reason, error = 'step_budget', None
    try:
        with ExitStack() as stack:
            stack.enter_context(recorded_context(samples, numerical))
            if args.fractional_air_timing:
                stack.enter_context(fractional_air_timing(True))
            for step in range(args.steps):
                if (args.output/'STOP').exists():
                    reason = 'requested_stop_file'
                    break
                before = len(samples)
                actions = np.zeros((env.num_agents, 2))
                if not one_shot_suppression_applied and args.one_shot_ab_suppress_train is not None:
                    index = args.one_shot_ab_suppress_train - 1
                    ctrl = env.multi_loco_controllers[index]
                    head_kmh = float(env.trains[index].dynamics.vel[0]) * 3.6
                    # This is routed through the normal controller gate.  It can only
                    # suppress an already active source; it cannot forge a release,
                    # alter pressure propagation, or shorten the refill clock.
                    if any(ctrl._ab_on) and head_kmh <= args.one_shot_ab_suppress_below_kmh:
                        actions[index, 1] = 1.0
                        one_shot_suppression_applied = True
                        if args.post_release_ed_mod_train is not None:
                            post_release_ed_probe_steps = max(
                                int(round(args.post_release_ed_mod_s / env.dt)), 1)
                if post_release_ed_probe_steps > 0:
                    actions[args.post_release_ed_mod_train - 1, 0] = args.post_release_ed_mod
                    post_release_ed_probe_steps -= 1
                if normal_release_ed_probe_steps > 0:
                    actions[args.on_source_release_ed_mod_train - 1, 0] = args.on_source_release_ed_mod
                    normal_release_ed_probe_steps -= 1
                _, _, terminated, truncated, info = env.step(actions)
                if (args.on_source_release_ed_mod_train is not None
                        and not normal_release_ed_probe_applied):
                    index = args.on_source_release_ed_mod_train - 1
                    current_source_state = list(env.multi_loco_controllers[index]._ab_on)
                    if any(before and not after for before, after in zip(
                            previous_source_state[index], current_source_state)):
                        normal_release_ed_probe_steps = max(
                            int(round(args.on_source_release_ed_mod_s / env.dt)), 1)
                        normal_release_ed_probe_applied = True
                previous_source_state = [list(controller._ab_on)
                                         for controller in env.multi_loco_controllers]
                velocity = np.asarray([t.dynamics.vel.copy() for t in env.trains])
                cf = np.asarray([t.dynamics.coupler_interface_forces().copy() for t in env.trains])
                mean = velocity.mean(axis=1)
                micropeak = max((s['peak_interface_n'] for s in samples[before:]), default=0.)
                rows.append([env.trains[0].dynamics.time, np.abs(cf).max(), velocity.max(),
                             velocity.min(), mean.min(), micropeak])
                commands.append(np.asarray(info['executed_actions']).copy())
                positions.append([t.dynamics.pos.copy() for t in env.trains])
                speeds.append(velocity)
                forces.append(cf)
                pressure.append([t.dynamics._brake_pressure * t.dynamics._air_brake_release_frac
                                 * t.dynamics._air_brake_active for t in env.trains])
                clock.append([c._ab_step for c in env.multi_loco_controllers])
                air_forces.append([t.dynamics._air_braking_forces().copy() for t in env.trains])
                physical_ed.append([a.copy() for a in actuator_inputs])
                heads.append([float(t.dynamics.pos[0]) for t in env.trains])
                rear_centers.append([float(t.dynamics.pos[-1]) for t in env.trains])
                gaps.append(float(info.get('gap_min_m', float('inf'))))
                safety.append(int(info.get('safety_events', 0)))
                safety_deltas.append(safety[-1] - previous_safety_count)
                previous_safety_count = safety[-1]
                for ti, train in enumerate(env.trains):
                    for event in train.safety.last_events:
                        event_records.append(dict(time_s=rows[-1][0], train_one_based=ti+1,
                                                  **event))
                modes.append([c._cyclic_braking for c in env.multi_loco_controllers])
                holds.append([c._ed_hold_steps for c in env.multi_loco_controllers])
                source_on.append([list(c._ab_on) for c in env.multi_loco_controllers])
                release_steps.append([list(c._ab_last_release_step) for c in env.multi_loco_controllers])
                refill_remaining.append([
                    [max(0., c.ab_min_refill_s-(c._ab_step-int(last))*c.dt)
                     for last in c._ab_last_release_step] for c in env.multi_loco_controllers])
                refill_veto_counts.append([c.ab_refill_veto_count for c in env.multi_loco_controllers])
                if step % 100 == 0:
                    print(f't={rows[-1][0]:.1f} peak={micropeak/1000:.1f}'
                          f' vmin={velocity.min()*3.6:.2f} gap={gaps[-1]:.2f}'
                          f' safety_delta={safety_deltas[-1]}'
                          f' air={np.max(np.abs(air_forces[-1]))/1000:.2f}kN/vehicle', flush=True)
                if not np.all(np.isfinite(rows[-1])):
                    reason = 'nonfinite'
                    break
                if max(micropeak, np.abs(cf).max()) > env.coupler_force_limit_n:
                    reason = 'coupler_threshold'
                    break
                if velocity.max() >= env.v_max - 1e-6:
                    reason = 'speed_ceiling'
                    break
                if mean.min() < env.v_min - 1e-6:
                    reason = 'speed_floor'
                    break
                if velocity.min() < env.v_min - 1e-6:
                    reason = 'vehicle_speed_floor'
                    break
                if float(info.get('gap_min_m', float('inf'))) < 0:
                    reason = 'negative_gap'
                    break
                if args.stop_on_safety_event and safety_deltas[-1] > 0:
                    reason = 'new_safety_event'
                    break
                if args.finish_m is not None and all(
                        float(t.dynamics.pos[-1]) >= args.finish_m for t in env.trains):
                    reason = 'all_train_tails_finished'
                    break
                if (args.checkpoint_below_kmh is not None
                        and mean[args.checkpoint_train-1]*3.6 <= args.checkpoint_below_kmh):
                    reason = 'mean_speed_checkpoint'
                    break
                if terminated or truncated:
                    reason = 'environment_ended'
                    break
    except BaseException as exc:
        reason, error = 'exception_incomplete', repr(exc)
        raise
    finally:
        if reason not in ('exception_incomplete', 'nonfinite'):
            save_fleet_checkpoint(env, args.output, numerical)
        np.savez_compressed(args.output/'trajectory.npz', rows=np.asarray(rows),
            commands=np.asarray(commands), vehicle_positions_m=np.asarray(positions),
            vehicle_speeds_mps=np.asarray(speeds), coupler_interface_force_n=np.asarray(forces),
            effective_pressure_coefficient=np.asarray(pressure), controller_steps=np.asarray(clock))
        np.savez_compressed(args.output/'telemetry.npz', vehicle_air_force_n=np.asarray(air_forces),
            physical_loco_ed=np.asarray(physical_ed), heads=np.asarray(heads),
            last_vehicle_centers=np.asarray(rear_centers), gap_min_m=np.asarray(gaps),
            safety_events=np.asarray(safety), cyclic_braking=np.asarray(modes),
            safety_events_delta=np.asarray(safety_deltas),
            ab_source_on=np.asarray(source_on), ab_last_release_step=np.asarray(release_steps),
            ab_refill_remaining_s=np.asarray(refill_remaining),
            ab_refill_veto_cumulative=np.asarray(refill_veto_counts),
            ed_hold_steps=np.asarray(holds))
        (args.output/'safety_events.json').write_text(json.dumps(dict(
            initial_cumulative_count=initial_safety_count,
            event_count_from_counter_delta=sum(safety_deltas),
            recorded_rule_counts=dict(Counter(e['rule'] for e in event_records)),
            records=event_records), indent=2), encoding='utf-8')
        summary = dict(stop_reason=reason, error=error, steps=len(rows),
            full_route_completed=reason == 'all_train_tails_finished',
            finish_m=args.finish_m,
            final_tail_positions_m=[float(t.dynamics.pos[-1]) for t in env.trains],
            last_time_s=rows[-1][0] if rows else manifest['elapsed_s'][0],
            internal_peak_kn=max((s['peak_interface_n'] for s in samples), default=0)/1000,
            max_force_residual_n=max((s['max_force_residual_n'] for s in samples), default=0),
            accepted_microsteps=sum(s['accepted'] for s in samples),
            min_train_mean_kmh=min((r[4]*3.6 for r in rows), default=None),
            min_gap_m=min(gaps, default=None), safety_event_count=sum(safety_deltas),
            safety_count_semantics='Difference of cumulative train counters, not sum over time',
            actual_air_force_peak_n=max((float(np.max(np.abs(f))) for f in air_forces), default=0.),
            vehicle_speed_floor_stop_enabled=True,
            min_vehicle_kmh=min((r[3]*3.6 for r in rows), default=None),
            max_vehicle_kmh=max((r[2]*3.6 for r in rows), default=None))
        (args.output/'result.json').write_text(json.dumps(dict(summary=summary, metadata=metadata),
            indent=2), encoding='utf-8')
        env.close()
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
