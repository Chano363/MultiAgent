"""Experimental restart cannot silently fall back to native mechanics."""
import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.evaluation import checkpoint_numerics as module
from src.train_dynamics.train import TrainDynamics

FROZEN_SOURCES = ('newton_mechanics_candidate', 'native_force_tangent',
                  'fractional_air_timing', 'refine_pneumatic_interval')

# 旧冻结档（2026-10-19 round29）。其指纹对应**当时的实现**；实现升级后必须被拒，
# 而不是要求"当前实现 == 旧指纹"。
LEGACY_ARCHIVE = (Path('outputs/sim_validation/phys_validation/')
                  / 'single108_pressure_ready_cold70_cycle_20261019_round29/run/native_release_state.json')


def _sha(name):
    root = Path(module.__file__).parent
    return hashlib.sha256((root / f'{name}.py').read_bytes()).hexdigest()


def manifest():
    """按**当前实现**构造 manifest —— 测性质，不锁某一版指纹。

    历史：本测试原先直接读 round29 冻结档并断言 `settings['air_step_s'] == .0025`，
    于是求解器一升级就红（2026-10-21 合并 xmc-dev 后首次触发）。但它要守护的性质
    是"**换实现必须被拒**"，并非"实现永远不变"，故改为自洽构造 + 篡改拒绝两条性质：
      1) 当前实现配自己的指纹 → 必须通过；
      2) 指纹/设置被篡改 → 必须抛 `implementation differs`。
    旧档不被静默复用这一条，由 `test_legacy_archive_from_older_implementation_is_rejected` 守护。
    """
    record = {
        'experimental_numerical_solver': True,
        'solver_sha256': _sha('adaptive_newmark_candidate'),
        'frozen_sources_sha256': {name: _sha(name) for name in FROZEN_SOURCES},
        'settings': {
            'solver': 'balanced',
            'fractional_air_timing': .0025,
            'air_step_s': .0025,
            'max_step_s': .000625,
            'force_tolerance_n': 1.0,
            'displacement_tolerance_m': 1e-6,
            'max_iter': 10,
            'ramp_air_force': True,
        },
    }
    return {'experimental_numerical_solver': record}


def test_current_implementation_passes_its_own_manifest():
    settings = module.verify_checkpoint_numerics(manifest())
    assert settings['air_step_s'] == .0025
    assert settings['max_step_s'] == .000625
    assert settings['ramp_air_force'] is True


def test_legacy_archive_from_older_implementation_is_rejected():
    """旧档若与当前实现不符，必须被拒（禁止静默换实现续训）。"""
    if not LEGACY_ARCHIVE.exists():
        pytest.skip('legacy archive not present')
    legacy = json.loads(LEGACY_ARCHIVE.read_text(encoding='utf-8'))
    record = legacy.get('experimental_numerical_solver') or {}
    if not isinstance(record, dict) or not record.get('solver_sha256'):
        pytest.skip('legacy archive carries no frozen numeric record')
    if record['solver_sha256'] == _sha('adaptive_newmark_candidate'):
        pytest.skip('legacy archive still matches current implementation')
    with pytest.raises(ValueError, match='implementation differs'):
        module.verify_checkpoint_numerics(legacy)


@pytest.mark.parametrize('component', ['solver_sha256', 'native_force_tangent', 'fractional_air_timing'])
def test_changed_implementation_is_rejected(component):
    value = copy.deepcopy(manifest())
    record = value['experimental_numerical_solver']
    if component == 'solver_sha256':
        record[component] = 'different'
    else:
        record['frozen_sources_sha256'][component] = 'different'
    with pytest.raises(ValueError, match='implementation differs'):
        module.verify_checkpoint_numerics(value)


def test_native_manifest_is_not_experimental():
    with pytest.raises(ValueError, match='explicitly experimental'):
        module.verify_checkpoint_numerics({})


def test_context_setup_failure_restores_already_installed_hooks(monkeypatch):
    @contextmanager
    def failing(*args, **kwargs):
        raise RuntimeError('setup failed')
        yield

    before = (TrainDynamics._advance_control_once, TrainDynamics._step_newmark,
              TrainDynamics._advance_air_brake_propagation)
    monkeypatch.setattr(module, 'coupled_candidate', failing)
    with pytest.raises(RuntimeError, match='setup failed'):
        module.checkpoint_numerical_context(manifest(), SimpleNamespace(dynamics=object()), [])
    assert before == (TrainDynamics._advance_control_once, TrainDynamics._step_newmark,
                      TrainDynamics._advance_air_brake_propagation)
