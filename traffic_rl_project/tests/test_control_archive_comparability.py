"""Reject the historical Y2/Z confound before attributing parameter effects."""
import shutil
import json
from pathlib import Path

from src.evaluation.audit_control_archives import compare_archives


ARCHIVES = (Path(__file__).resolve().parents[1] / 'outputs/sim_validation/'
            'phys_validation/rulecal_20261016')


def test_historical_aa_is_not_a_single_parameter_change_from_y2():
    result = compare_archives(ARCHIVES / 'Y2_ramp07', ARCHIVES / 'AA_ramp80')
    assert result['status'] == 'requires_review'
    assert result['source_changes'] == ['controller']
    assert set(result['config_changes']) == {'ed_upgrade_ramp_s'}


def test_historical_aa_is_a_recorded_parameter_change_from_z():
    result = compare_archives(ARCHIVES / 'Z_apply_edge', ARCHIVES / 'AA_ramp80')
    assert result['status'] == 'recorded_single_parameter_change'
    assert not result['evidence_gaps']


def test_missing_frozen_source_is_unknown_not_a_match(tmp_path):
    candidate = tmp_path / 'missing_source'
    shutil.copytree(ARCHIVES / 'AA_ramp80', candidate,
                    ignore=shutil.ignore_patterns('trajectory.*'))
    (candidate / 'controller_source.py').unlink()
    result = compare_archives(ARCHIVES / 'Z_apply_edge', candidate)
    assert result['status'] == 'requires_review'
    assert any('controller' in item for item in result['evidence_gaps'])


def test_tampered_source_cannot_reuse_declared_hash(tmp_path):
    candidate = tmp_path / 'tampered'
    shutil.copytree(ARCHIVES / 'AA_ramp80', candidate,
                    ignore=shutil.ignore_patterns('trajectory.*'))
    with (candidate / 'controller_source.py').open('a', encoding='utf-8') as stream:
        stream.write('\n# Added after the archived run.\n')
    result = compare_archives(ARCHIVES / 'Z_apply_edge', candidate)
    assert result['status'] == 'requires_review'
    assert any('controller' in item for item in result['evidence_gaps'])


def test_new_diagnostic_stop_is_not_equivalent_to_historical_full_duration(tmp_path):
    candidate = tmp_path / 'early_stop'
    shutil.copytree(ARCHIVES / 'AA_ramp80', candidate,
                    ignore=shutil.ignore_patterns('trajectory.*'))
    path = candidate / 'result.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['metadata']['diagnostic_protocol']['stop_on_coupler_kn'] = 1350.0
    path.write_text(json.dumps(record), encoding='utf-8')
    result = compare_archives(ARCHIVES / 'Z_apply_edge', candidate)
    assert result['status'] == 'requires_review'
    assert result['protocol_changes']['stop_on_coupler_kn'] == {
        'baseline': None, 'candidate': 1350.0}


def test_runtime_flag_difference_requires_review_even_with_identical_recorded_config(tmp_path):
    candidate = tmp_path / 'runtime_changed'
    shutil.copytree(ARCHIVES / 'Z_apply_edge', candidate,
                    ignore=shutil.ignore_patterns('trajectory.*'))
    path = candidate / 'result.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['metadata']['controller_runtime'][0]['ed_grade_feedforward'] = True
    path.write_text(json.dumps(record), encoding='utf-8')
    result = compare_archives(ARCHIVES / 'Z_apply_edge', candidate)
    assert result['status'] == 'requires_review'
    assert not result['source_changes'] and not result['config_changes']
    assert any('controller_runtime' in item for item in result['evidence_gaps'])
