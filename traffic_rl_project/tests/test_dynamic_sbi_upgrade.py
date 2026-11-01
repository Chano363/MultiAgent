"""Restrictive upgrade threshold must not weaken the native trigger."""
import math

import pytest

from src.evaluation.dynamic_sbi_upgrade import upgrade_threshold


@pytest.mark.parametrize('ceiling,expected', [(70/3.6, 70.), (80/3.6, 76.), (60/3.6, 60.)])
def test_earlier_dynamic_threshold_only(ceiling, expected):
    assert upgrade_threshold(76., ceiling, True, True) == pytest.approx(expected)


@pytest.mark.parametrize('ceiling,gap,enabled', [(70/3.6, False, True),
    (70/3.6, True, False), (math.nan, True, True), (-1., True, True)])
def test_invalid_or_disabled_context_preserves_native_value(ceiling, gap, enabled):
    assert upgrade_threshold(76., ceiling, gap, enabled) == 76.
