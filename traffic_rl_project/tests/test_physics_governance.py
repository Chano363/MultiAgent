"""物理治理 / metadata 编组派生回归（2026-09-30）。

背景：主实验切 `10kt_1plus1` 后，metadata 的 `physics` 块仍固报 `PhysicsConfig`
默认 `10kt_1plus0`（`simulator_model` / `simulator_model_version` 连带失真）。
修复 = `official_world_config(physics, env_cfg)` 支持按 `RUN_DERIVED_KEYS`
从本次运行 env_cfg 派生。溯源见
`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-metadata 编组不一致溯源」。
"""
from src.environments.train_env import CONSIST_PRESETS
from src.metadata import build_metadata, simulator_model, simulator_model_version
from src.physics_config import PhysicsConfig
from src.physics_governance import (
    RUN_DERIVED_KEYS, official_world_config,
)

RUN_CONSIST = '20kt_1plus108_1plus108'   # 主实验真实编组（3列×头/中部双机车=6 机车智能体，ADR-035）


def test_no_env_cfg_keeps_official_snapshot():
    """不传 env_cfg → 与旧行为一致（纯固版快照，向后兼容）。"""
    cfg = official_world_config(PhysicsConfig())
    assert cfg['physics']['consist_preset'] == PhysicsConfig().consist_preset


def test_env_cfg_derives_consist_into_world_cfg():
    cfg = official_world_config(PhysicsConfig(), env_cfg={'consist_preset': RUN_CONSIST})
    assert cfg['physics']['consist_preset'] == RUN_CONSIST
    # 其余物理项仍锚定固版基线，不随实验漂移
    default = PhysicsConfig()
    for key in ('grade_profile', 'coupler_force_limit_n', 'enable_cyclic_degrade'):
        assert cfg['physics'][key] == default.to_dict()[key]


def test_derived_consist_is_known_preset():
    """派生的编组必须是登记在案的预设（防 env_cfg 手写错串静默落入 metadata）。"""
    cfg = official_world_config(PhysicsConfig(), env_cfg={'consist_preset': RUN_CONSIST})
    assert cfg['physics']['consist_preset'] in CONSIST_PRESETS


def test_empty_env_cfg_value_does_not_override():
    """env_cfg 里该键为空/缺失 → 不覆盖（避免空值污染固版快照）。"""
    cfg = official_world_config(PhysicsConfig(), env_cfg={'consist_preset': ''})
    assert cfg['physics']['consist_preset'] == PhysicsConfig().consist_preset


def test_metadata_simulator_model_reflects_run_consist():
    """`simulator_model` 串与 `simulator_model_version` 必须反映本次运行编组。"""
    derived = official_world_config(PhysicsConfig(), env_cfg={'consist_preset': RUN_CONSIST})
    snapshot = official_world_config(PhysicsConfig())

    model = simulator_model('official', derived)
    assert f'consist={RUN_CONSIST}' in model
    assert simulator_model_version('official', derived) != \
        simulator_model_version('official', snapshot)

    meta = build_metadata(project_root='.', case='official', world_cfg=derived,
                          seed=0, entry='test_physics_governance.py')
    # meta['physics'] = world_cfg（顶层治理开关 + 嵌套 physics 快照）
    assert meta['physics']['physics']['consist_preset'] == RUN_CONSIST
    assert f'consist={RUN_CONSIST}' in meta['simulator_model']


def test_run_derived_keys_are_declared():
    """派生键须显式登记（防后人加字段却忘了让 metadata 跟随）。"""
    assert 'consist_preset' in RUN_DERIVED_KEYS