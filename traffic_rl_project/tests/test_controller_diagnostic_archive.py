"""Diagnostic archives must describe actual physics and preserve provenance."""
import hashlib
import json
import sys

import pytest
import numpy as np

from src.evaluation.diagnose_low_level_control import main


def test_prelimit_runtime_and_reuse_guard(tmp_path, monkeypatch):
    output = tmp_path / 'prelimit'
    argv = ['diagnostic', '--output', str(output), '--steps', '3',
            '--consist-preset', '20kt_1plus108_1plus108', '--speed', '79', '--ed-prelimit']
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert result['metadata']['controller_runtime'][0]['ed_prelimit'] is True
    with np.load(output / 'trajectory.npz') as data:
        assert np.any(data['physical_loco_ed'] > 0)
        assert not data['cyclic_braking'].any()
    monkeypatch.setattr(sys, 'argv', argv[:-1] + ['--reuse'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()


def test_middle_distributed_20kt_archive_and_reuse_guard(tmp_path, monkeypatch):
    output = tmp_path / 'middle_20kt'
    argv = ['diagnostic', '--output', str(output), '--steps', '3',
            '--consist-preset', '20kt_1plus108_1plus108', '--speed', '65']
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert result['metadata']['env_cfg']['consist_preset'] == '20kt_1plus108_1plus108'
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
                         'decompose': 'loco_ed_ab'})
    try:
        tr = env.trains[0]
        assert tr.num_vehicles == 218
        assert tr.loco_indices == [0, 109]
        assert tr.dynamics.masses_kg.sum() / 1000 == pytest.approx(21976)
        assert env.multi_loco_controllers[0].loco_indices == [0, 109]
    finally:
        env.close()
    with np.load(output / 'trajectory.npz') as data:
        assert data['physical_loco_ed'].shape == (3, 1, 2)
        assert data['air_brake_segment'].shape == (3, 1)
        assert np.all(data['air_brake_segment'] >= 0)
        assert data['brake_pressure_coefficient'].shape == (3, 1, 218)
        np.testing.assert_allclose(data['effective_pressure_coefficient'],
                                   data['brake_pressure_coefficient'] * data['air_release_fraction'] * data['ab_active'])
        assert data['coupler_interface_force_n'].shape == (3, 1, 217)
        assert data['loco_ed_force_n'].shape == (3, 1, 2)
        assert data['vehicle_air_force_n'].shape == (3, 1, 218)
        assert data['vehicle_positions_m'].shape == (3, 1, 218)
        np.testing.assert_allclose(
            np.max(np.abs(data['coupler_interface_force_n']), axis=(1, 2)),
            data['rows'][:, 2])
    changed = argv.copy()
    changed[changed.index('--consist-preset') + 1] = '10kt_1plus1'
    monkeypatch.setattr(sys, 'argv', changed + ['--reuse'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()


def test_frozen_fleet_source_and_per_train_speeds_are_archived(tmp_path, monkeypatch):
    from pathlib import Path

    snapshot = tmp_path / 'fleet_source.py'
    source = Path('src/environments/train_fleet_env.py').read_text(encoding='utf-8')
    snapshot.write_bytes(source.encode('utf-8'))
    output = tmp_path / 'mixed_speeds'
    argv = ['diagnostic', '--output', str(output), '--steps', '3', '--trains', '3',
            '--train-speeds-kmh', '40', '65', '65', '--fleet-env-source', str(snapshot)]
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert result['metadata']['fleet_env_sha256'] == hashlib.sha256(source.encode('utf-8')).hexdigest()
    assert result['metadata']['diagnostic_protocol']['train_speeds_kmh'] == [40, 65, 65]
    with np.load(output / 'trajectory.npz') as data:
        np.testing.assert_allclose(data['initial_head_speeds'] * 3.6, [40, 65, 65])
        assert data['physical_loco_ed'].shape == (3, 3, 2)
        assert np.all((data['physical_loco_ed'] >= 0) & (data['physical_loco_ed'] <= 1))
        assert data['cyclic_braking'].shape == (3, 3)
        assert data['safety_rule_counts'].shape == (3, 3, 5)
        delta = np.diff(data['physical_loco_ed'], axis=0)
        assert result['summary']['physical_ed_change_rms_per_s'] == pytest.approx(
            np.sqrt(np.mean((delta / 0.1) ** 2)))
    changed = argv.copy()
    changed[changed.index('--train-speeds-kmh') + 1] = '45'
    monkeypatch.setattr(sys, 'argv', changed + ['--reuse'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()

    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--anticipate-etcs'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()

    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--ed-recovery-scope', 'coupler'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()

    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--ed-grade-feedforward'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()


def test_runtime_metadata_and_reuse_do_not_relabel_physics(tmp_path, monkeypatch):
    output = tmp_path / 'route_probe'
    argv = ['diagnostic', '--output', str(output), '--steps', '3',
            '--profile', 'shuozhou_ningwuxi_beidaniu_49km', '--start-m', '16000', '--speed', '65']
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    original = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    metadata = original['metadata']
    assert metadata['physics']['enable_cyclic_degrade'] is True
    assert all(p['enable_cyclic_degrade'] for p in metadata['runtime_physics'])
    assert 'cyclic_degrade=True' in metadata['simulator_model']
    assert metadata['physics']['physics']['grade_profile'] == 'shuozhou_ningwuxi_beidaniu_49km'
    assert metadata['controller_sha256'] == hashlib.sha256((output / 'controller_source.py').read_bytes()).hexdigest()
    data_hash = hashlib.sha256((output / 'trajectory.npz').read_bytes()).hexdigest()

    # A caller's new source request cannot relabel an already saved controller.
    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--controller-ref', '4ba79e2',
                                           '--metadata-file', 'recomputed.json'])
    main()
    recomputed = json.loads((output / 'recomputed.json').read_text(encoding='utf-8'))
    assert recomputed['metadata']['controller_sha256'] == metadata['controller_sha256']
    assert recomputed['metadata']['controller_ref'] == metadata['controller_ref']
    assert recomputed['metadata']['controller_runtime'] == metadata['controller_runtime']
    assert recomputed['metadata']['diagnostic_protocol'] == metadata['diagnostic_protocol']
    assert hashlib.sha256((output / 'trajectory.npz').read_bytes()).hexdigest() == data_hash

    # Missing legacy parameters are unknown, not today's constructor defaults.
    del original['metadata']['controller_runtime']
    (output / 'result.json').write_text(json.dumps(original), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--metadata-file', 'legacy_recomputed.json'])
    main()
    legacy = json.loads((output / 'legacy_recomputed.json').read_text(encoding='utf-8'))
    assert legacy['metadata']['controller_runtime'] is None
    assert hashlib.sha256((output / 'trajectory.npz').read_bytes()).hexdigest() == data_hash

    incompatible = argv.copy()
    incompatible[incompatible.index('--profile') + 1] = 'long_downhill_20km'
    monkeypatch.setattr(sys, 'argv', incompatible + ['--reuse'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()

    monkeypatch.setattr(sys, 'argv', argv + ['--reuse', '--ed-recovery-rate', '0'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()


def test_archived_source_replay_keeps_its_experimental_defaults(tmp_path, monkeypatch):
    from pathlib import Path

    source = Path('src/controllers/multi_loco_controller.py').read_text(encoding='utf-8')
    archived_source = source.replace('ed_recovery_rate_per_s: float = 0.0',
                                     'ed_recovery_rate_per_s: float = 2.0', 1)
    assert archived_source != source
    snapshot = tmp_path / 'archived_trial.py'
    snapshot.write_bytes(archived_source.encode('utf-8'))
    output = tmp_path / 'source_replay'
    monkeypatch.setattr(sys, 'argv', ['diagnostic', '--output', str(output),
                                    '--steps', '3', '--speed', '65',
                                    '--controller-source', str(snapshot)])
    main()
    metadata = json.loads((output / 'result.json').read_text(encoding='utf-8'))['metadata']
    assert metadata['controller_ref'] == 'source-file'
    assert metadata['diagnostic_protocol']['controller_source'] == str(snapshot)
    assert metadata['controller_runtime'][0]['ed_recovery_rate_per_s'] == 2.0
    assert metadata['controller_sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_feedforward_trial_metadata_matches_executed_braking(tmp_path, monkeypatch):
    output = tmp_path / 'feedforward'
    argv = ['diagnostic', '--output', str(output), '--steps', '3', '--speed', '65',
            '--profile', 'shuozhou_ningwuxi_beidaniu_49km', '--start-m', '40000', '--ed-grade-feedforward']
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert result['metadata']['controller_runtime'][0]['ed_grade_feedforward'] is True
    with np.load(output / 'trajectory.npz') as data:
        assert np.any(data['physical_loco_ed'] > 0)
        assert not np.any(data['cyclic_braking'])
    digest = hashlib.sha256((output / 'trajectory.npz').read_bytes()).hexdigest()
    monkeypatch.setattr(sys, 'argv', argv[:-1] + ['--reuse'])
    with pytest.raises(ValueError, match='Cannot relabel saved trajectory'):
        main()
    assert hashlib.sha256((output / 'trajectory.npz').read_bytes()).hexdigest() == digest
