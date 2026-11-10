from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.diagnose_held_air_neighbor import enable_neighbor


def state():
    controls = [SimpleNamespace(cyclic_release_kmh=x, _ab_on=[True],
        _ab_step=7600, _ab_last_release_step=[7201]) for x in [56.1, 50., 50.]]
    dynamics = SimpleNamespace(pos=np.array([100., 90.]), vel=np.array([16., 16.]),
                               pressure=np.array([.3, .4]))
    return SimpleNamespace(num_trains=3, multi_loco_controllers=controls,
        dynamics=dynamics, _formation_ref_gap=lambda i=None: 183.33), \
        {'numerical': {'source_sha256': {}}}


def test_preserves_physical_state_and_history():
    env, manifest = state()
    before = [x.copy() for x in (env.dynamics.pos, env.dynamics.vel, env.dynamics.pressure)]
    _, result = enable_neighbor(env, manifest)
    for old, actual in zip(before, (env.dynamics.pos, env.dynamics.vel, env.dynamics.pressure)):
        assert np.array_equal(old, actual)
    assert [c.cyclic_release_kmh for c in env.multi_loco_controllers] == [54., 50., 50.]
    assert all(c._ab_step == 7600 and c._ab_last_release_step == [7201]
               for c in env.multi_loco_controllers)
    assert manifest['numerical']['source_sha256'] == {}
    assert result['experimental_alternate_state_override']['previous_leader_release_kmh'] == 56.1


def test_rejects_other_follower_setting_before_mutation():
    env, manifest = state()
    env.multi_loco_controllers[1].cyclic_release_kmh = 48.
    with pytest.raises(ValueError):
        enable_neighbor(env, manifest)
    assert env.multi_loco_controllers[0].cyclic_release_kmh == 56.1
