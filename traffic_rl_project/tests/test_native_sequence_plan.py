import copy

import numpy as np
import pytest

from src.evaluation.diagnose_actuator_sensitivity import validate_sequence_entries


def example():
    return {'name': 'head_020', 'ED_depths': [[0, 0], [1, 0], [0, 0]],
            'durations_s': [3, 3, 6]}


def test_unequal_blocks_cover_native_horizon_and_preserve_two_actuators():
    value = validate_sequence_entries([example()], 12)['head_020']
    np.testing.assert_array_equal(value[0], [[0, 0], [1, 0], [0, 0]])
    np.testing.assert_array_equal(np.cumsum(value[1] / 0.1), [30, 60, 120])


@pytest.mark.parametrize('name', ['../escape', 'folder/name', ''])
def test_plan_names_cannot_escape_archive(name):
    entry = example()
    entry['name'] = name
    with pytest.raises(ValueError):
        validate_sequence_entries([entry], 12)


@pytest.mark.parametrize('change', ['unbounded', 'nan', 'wrong_horizon', 'missing_actuator'])
def test_invalid_physical_requests_and_incomplete_horizons_rejected(change):
    entry = copy.deepcopy(example())
    if change == 'unbounded':
        entry['ED_depths'][0][0] = 1.1
    elif change == 'nan':
        entry['ED_depths'][0][0] = float('nan')
    elif change == 'wrong_horizon':
        entry['durations_s'] = [3, 3, 5]
    else:
        entry['ED_depths'] = [[0], [1], [0]]
    with pytest.raises(ValueError):
        validate_sequence_entries([entry], 12)


def test_duplicate_names_rejected_instead_of_silently_replacing_a_trial():
    with pytest.raises(ValueError):
        validate_sequence_entries([example(), example()], 12)


def test_single_locomotive_probes_preserve_shape_and_input():
    import numpy as np
    from src.evaluation.diagnose_actuator_sensitivity import actuator_hold_variants, validate_sequence_entries
    action=np.array([[0.6,-0.05]])
    probes=actuator_hold_variants(action)
    assert all(v.shape==(1,) for v in probes.values())
    probes['baseline_hold'][0]=0.1
    assert action[0,0]==0.6
    validate_sequence_entries([{'name':'single','ED_depths':[[0.2],[0.4]],'durations_s':[1,2]}],3,1)


def test_shadow_air_comparison_preserves_the_original_clock_and_plan():
    from types import SimpleNamespace
    from src.evaluation.diagnose_actuator_sensitivity import counterfactual_air_variants
    controller = SimpleNamespace(num_locomotives=1, _ab_step=4711,
                                 _ab_last_release_step=[2491], dt=0.1,
                                 ab_min_refill_s=222.0, _ab_on=[False])
    plan = {'hold': np.array([[0.55]])}
    before = copy.deepcopy(controller.__dict__)
    expanded, requests = counterfactual_air_variants(plan, controller, True)
    assert requests == {'hold__noair': 0.0, 'hold__cyclic50': -0.05}
    assert controller.__dict__ == before
    np.testing.assert_array_equal(expanded['hold__cyclic50'], plan['hold'])


@pytest.mark.parametrize('change', ['not_ready', 'still_on', 'wrong_consist', 'cyclic_disabled'])
def test_shadow_air_comparison_rejects_inapplicable_state(change):
    from types import SimpleNamespace
    from src.evaluation.diagnose_actuator_sensitivity import counterfactual_air_variants
    controller = SimpleNamespace(num_locomotives=1, _ab_step=4711,
                                 _ab_last_release_step=[2491], dt=0.1,
                                 ab_min_refill_s=222.0, _ab_on=[False])
    if change == 'not_ready':
        controller._ab_step -= 1
    elif change == 'still_on':
        controller._ab_on = [True]
    elif change == 'wrong_consist':
        controller.num_locomotives = 2
    with pytest.raises(ValueError):
        counterfactual_air_variants({'hold': np.array([[0.55]])}, controller,
                                    change != 'cyclic_disabled')


def test_planned_air_keeps_full_refill_before_reapplication():
    from src.evaluation.diagnose_actuator_sensitivity import validate_shadow_air_blocks
    np.testing.assert_array_equal(
        validate_shadow_air_blocks([0, -0.05], [222, 38], 0, 222), [0, -0.05])
    with pytest.raises(ValueError):
        validate_shadow_air_blocks([0, -0.05], [221.9, 38.1], 0, 222)


def test_planned_air_restarts_refill_clock_after_a_second_release():
    from src.evaluation.diagnose_actuator_sensitivity import validate_shadow_air_blocks
    with pytest.raises(ValueError):
        validate_shadow_air_blocks([-0.05, 0, -0.05], [10, 100, 5], 222, 222)
    validate_shadow_air_blocks([-0.05, 0, -0.05], [10, 222, 5], 222, 222)


@pytest.mark.parametrize('requests,durations', [([-0.75], [1]), ([float('nan')], [1]),
                                               ([0, -0.05], [1]), ([0], [-1])])
def test_planned_air_rejects_wrong_notches_or_invalid_blocks(requests, durations):
    from src.evaluation.diagnose_actuator_sensitivity import validate_shadow_air_blocks
    with pytest.raises(ValueError):
        validate_shadow_air_blocks(requests, durations, 222, 222)


def test_own_native_environment_checkpoint_roundtrip_preserves_internal_state():
    import pickle
    from pathlib import Path
    import yaml
    from src.environments.train_fleet_env import TrainFleetEnv
    path = Path(__file__).resolve().parents[1] / 'configs/experiments/single_10kt108_coupler_rulecal.yaml'
    env = TrainFleetEnv(yaml.safe_load(path.read_text(encoding='utf-8'))['env_cfg'])
    try:
        env.reset(seed=0)
        # Deserialize only bytes generated in this test, never external input.
        restored = pickle.loads(pickle.dumps(env.trains[0], protocol=pickle.HIGHEST_PROTOCOL))
        for name in ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_pending',
                     '_air_brake_delay_remaining', '_air_brake_release_frac'):
            np.testing.assert_array_equal(getattr(restored.dynamics, name),
                                          getattr(env.trains[0].dynamics, name))
        assert restored.dynamics.time == env.trains[0].dynamics.time
        assert restored.safety._peak_hist == env.trains[0].safety._peak_hist
        restored.close()
    finally:
        env.close()


def test_per_block_slew_preserves_legacy_default_and_phase_boundaries():
    from src.evaluation.diagnose_actuator_sensitivity import sequence_slew_rates
    durations = [50, 172, 38]
    np.testing.assert_array_equal(sequence_slew_rates({}, durations, 0.5), [0.5]*3)
    entry = {'ED_ramp_per_s': [0.05, 0.005, 0.05]}
    np.testing.assert_array_equal(sequence_slew_rates(entry, durations, 0.5), entry['ED_ramp_per_s'])
    for value in ([0.05], [0, 1, 1], [float('nan'), 1, 1]):
        with pytest.raises(ValueError):
            sequence_slew_rates({'ED_ramp_per_s': value}, durations, 0.5)


@pytest.mark.parametrize('change', [None, 'env_cfg', 'controller_sha256', 'native_source_sha256',
                                   'numpy_version', 'python_version', 'time_s', 'start_m', 'speed_kmh'])
def test_cached_native_provenance_rejects_incompatible_configuration_before_loading(change):
    import sys
    from src.evaluation.diagnose_actuator_sensitivity import validate_checkpoint_compatibility
    cfg = {'consist_preset': '10kt_1plus108'}
    sources = {'src/train_dynamics/train.py': 'example-source-hash'}
    manifest = {'format': 'locally-generated-native-shadow-checkpoint-v1',
                'env_cfg': cfg, 'controller_sha256': 'controller-hash',
                'native_source_sha256': sources, 'numpy_version': np.__version__,
                'python_version': list(sys.version_info[:2]),
                'time_s': 249.1, 'start_m': 0, 'speed_kmh': 80}
    if change is None:
        validate_checkpoint_compatibility(manifest, cfg, 'controller-hash', sources, 249.1, 0, 80)
    else:
        manifest[change] = 'incompatible'
        with pytest.raises(ValueError):
            validate_checkpoint_compatibility(manifest, cfg, 'controller-hash', sources, 249.1, 0, 80)
