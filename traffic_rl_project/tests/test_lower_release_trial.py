from types import SimpleNamespace

import pytest

from src.evaluation.diagnose_lower_release import set_lower_release


def setup_state():
    controls = [SimpleNamespace(cyclic_release_kmh=50., _ab_on=[True],
                               _phase_release_floor_enabled=True) for _ in range(3)]
    return SimpleNamespace(v_min=40./3.6, multi_loco_controllers=controls), {
        'numerical': {'source_sha256': {}}}


def test_changes_only_selected_controller_and_preserves_source_manifest():
    env, manifest = setup_state()
    returned, record = set_lower_release(env, manifest, 2, 48.)
    assert returned is env
    assert [c.cyclic_release_kmh for c in env.multi_loco_controllers] == [50., 48., 50.]
    assert manifest['numerical']['source_sha256'] == {}
    assert record['experimental_release_speed_override']['previous_kmh'] == 50.
    assert 'diagnose_lower_release' in record['numerical']['source_sha256']


@pytest.mark.parametrize('index,value', [(0, 48.), (4, 48.), (2, 39.), (2, 50.),
                                        (2, 51.), (2, float('nan'))])
def test_reject_invalid_trial_without_mutation(index, value):
    env, manifest = setup_state()
    with pytest.raises(ValueError):
        set_lower_release(env, manifest, index, value)
    assert all(c.cyclic_release_kmh == 50. for c in env.multi_loco_controllers)


def test_reject_already_released_state():
    env, manifest = setup_state()
    env.multi_loco_controllers[1]._ab_on = [False]
    with pytest.raises(ValueError, match='before release'):
        set_lower_release(env, manifest, 2, 48.)
