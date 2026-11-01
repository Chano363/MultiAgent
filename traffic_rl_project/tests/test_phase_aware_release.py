from types import SimpleNamespace
import numpy as np
import pytest
from src.evaluation.phase_aware_release import release_adjustment, candidate


def test_chase_cannot_raise_release_threshold_while_air_source_is_on():
    ctrl = SimpleNamespace(_phase_release_floor_enabled=True, _ab_on=[True])
    train = SimpleNamespace(etcs_targets=[SimpleNamespace(kind='gap')])
    assert release_adjustment(ctrl, train, np.zeros((1, 2)), 3.) == 0.
    assert release_adjustment(ctrl, train, np.zeros((1, 2)), -1.) == -1.
    assert release_adjustment(ctrl, train, np.ones((1, 2)), 3.) == 3.
    ctrl._ab_on = [False]
    assert release_adjustment(ctrl, train, np.zeros((1, 2)), 3.) == 3.
    ctrl._ab_on = [True]
    train.etcs_targets = []
    assert release_adjustment(ctrl, train, np.zeros((1, 2)), 3.) == 3.


def test_full_recorded_context_restores_phase_patch_on_failure():
    from src.controllers.multi_loco_controller import MultiLocoController
    from src.evaluation.continue_fleet_numerics import recorded_context
    original = (MultiLocoController.get_action_decomposed, MultiLocoController._operating_ceiling)
    with pytest.raises(RuntimeError):
        with recorded_context([], dict(solver='newton_analytic_time_error', settings={},
                source_sha256=dict(phase_aware_release='verified', following_speed_margin='verified',
                                   release_budget_guard='verified'))):
            assert MultiLocoController.get_action_decomposed is not original[0]
            raise RuntimeError('deliberate')
    assert original == (MultiLocoController.get_action_decomposed, MultiLocoController._operating_ceiling)


def test_phase_only_restart_does_not_install_unrecorded_margin():
    from src.controllers.multi_loco_controller import MultiLocoController
    from src.evaluation.continue_fleet_numerics import recorded_context
    original = MultiLocoController._operating_ceiling
    with recorded_context([], dict(solver='newton_analytic_time_error', settings={},
                                   source_sha256={'phase_aware_release': 'verified'})):
        assert MultiLocoController._operating_ceiling is original
