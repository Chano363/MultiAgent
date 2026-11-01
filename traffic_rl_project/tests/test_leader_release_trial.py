from types import SimpleNamespace

import pytest

from src.evaluation.diagnose_leader_release import set_leader_release


def state():
    env = SimpleNamespace(v_min=40./3.6, v_max=80./3.6,
        multi_loco_controllers=[SimpleNamespace(cyclic_release_kmh=50., _ab_on=[True])
                                for _ in range(3)])
    return env, {'numerical': {'source_sha256': {}}}


def test_changes_only_leader_with_immutable_manifest():
    env, manifest = state()
    _, record = set_leader_release(env, manifest, 56.1)
    assert [c.cyclic_release_kmh for c in env.multi_loco_controllers] == [56.1, 50., 50.]
    assert manifest['numerical']['source_sha256'] == {}
    assert record['experimental_leader_release_override']['previous_kmh'] == 50.


@pytest.mark.parametrize('value', [40., 50., 80., 81., float('nan')])
def test_invalid_threshold_does_not_mutate(value):
    env, manifest = state()
    with pytest.raises(ValueError):
        set_leader_release(env, manifest, value)
    assert env.multi_loco_controllers[0].cyclic_release_kmh == 50.


def test_requires_established_source():
    env, manifest = state()
    env.multi_loco_controllers[0]._ab_on = [False]
    with pytest.raises(ValueError):
        set_leader_release(env, manifest, 56.1)
