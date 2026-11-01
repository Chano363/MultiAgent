from types import SimpleNamespace
import pytest
from src.evaluation.following_speed_margin import restrictive_ceiling, candidate


def test_margin_restricts_only_enabled_following_targets():
    gap = [SimpleNamespace(kind='gap')]
    assert restrictive_ceiling(20., .5, gap, True) == 19.5
    assert restrictive_ceiling(.2, .5, gap, True) == 0
    assert restrictive_ceiling(20., .5, [], True) == 20
    assert restrictive_ceiling(20., .5, [SimpleNamespace(kind='line')], True) == 20
    assert restrictive_ceiling(20., .5, gap, False) == 20
    assert restrictive_ceiling(20., 0., gap, True) == 20


@pytest.mark.parametrize('margin', [-1., float('nan'), float('inf')])
def test_invalid_margin_rejected(margin):
    with pytest.raises(ValueError):
        restrictive_ceiling(20., margin, [], True)


def test_patch_restored_on_failure():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController._operating_ceiling
    with pytest.raises(RuntimeError):
        with candidate():
            raise RuntimeError('deliberate')
    assert MultiLocoController._operating_ceiling is original


def test_restart_installs_both_recorded_control_patches():
    from src.controllers.multi_loco_controller import MultiLocoController
    from src.evaluation.continue_fleet_numerics import recorded_context
    original = (MultiLocoController._operating_ceiling, MultiLocoController.get_action_decomposed)
    with recorded_context([], dict(solver='newton_analytic_time_error', settings={},
            source_sha256={'following_speed_margin': 'verified', 'release_budget_guard': 'verified'})):
        assert MultiLocoController._operating_ceiling is not original[0]
        assert MultiLocoController.get_action_decomposed is not original[1]
    assert original == (MultiLocoController._operating_ceiling,
                        MultiLocoController.get_action_decomposed)
