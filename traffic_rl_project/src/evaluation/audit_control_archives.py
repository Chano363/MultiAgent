"""Check recorded controls before interpreting a parameter comparison.

This checks provenance, not physical validity or statistical significance.
Missing evidence is reported as unknown rather than treated as a match.
"""
import argparse
import hashlib
import json
from pathlib import Path


SOURCES = {
    'controller': 'controller_source.py',
    'fleet_env': 'fleet_env_source.py',
    'train_env': 'train_env_source.py',
    'train_dynamics': 'train_dynamics_source.py',
    'etcs_braking': 'etcs_braking_source.py',
}
PROTOCOL_KEYS = (
    'stop_on_coupler_kn',
    'steps', 'trains', 'grade', 'speed', 'profile', 'start_m', 'finish_m',
    'gap_offset_m', 'train_speeds_kmh', 'consist_preset', 'ed_recovery_rate',
    'ed_recovery_scope', 'ed_grade_feedforward', 'ed_physics_availability',
    'ed_prelimit', 'ed_baseline_projection', 'anticipate_etcs',
)


def read_archive(directory):
    directory = Path(directory)
    record = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    metadata = record['metadata']
    evidence = {}
    for name, filename in SOURCES.items():
        path = directory / filename
        declared = metadata.get(f'{name}_sha256')
        actual = (hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8'))
                  .hexdigest() if path.exists() else None)
        evidence[name] = {
            'sha256': actual,
            'verified': actual is not None and declared == actual,
        }
    return {'directory': str(directory), 'metadata': metadata,
            'summary': record['summary'], 'sources': evidence}


def compare_archives(baseline, candidate):
    """Return conservative evidence for a *recorded* single-parameter contrast."""
    left = read_archive(baseline)
    right = read_archive(candidate)
    source_changes = []
    evidence_gaps = []
    for name in SOURCES:
        a, b = left['sources'][name], right['sources'][name]
        if not a['verified'] or not b['verified']:
            evidence_gaps.append(f'{name}: missing source or hash mismatch')
        elif a['sha256'] != b['sha256']:
            source_changes.append(name)

    missing = {'missing': True}
    a_cfg = left['metadata'].get('env_cfg', {})
    b_cfg = right['metadata'].get('env_cfg', {})
    config_changes = {
        key: {'baseline': a_cfg.get(key, missing),
              'candidate': b_cfg.get(key, missing)}
        for key in sorted(set(a_cfg) | set(b_cfg))
        if a_cfg.get(key, missing) != b_cfg.get(key, missing)
    }
    a_protocol = left['metadata'].get('diagnostic_protocol', {})
    b_protocol = right['metadata'].get('diagnostic_protocol', {})
    protocol_changes = {}
    for key in PROTOCOL_KEYS:
        if key == 'stop_on_coupler_kn':
            # This option did not exist in the historical diagnostics. Absence
            # means no diagnostic stop, while a newly enabled threshold differs.
            a_value, b_value = a_protocol.get(key), b_protocol.get(key)
            if a_value != b_value:
                protocol_changes[key] = {'baseline': a_value, 'candidate': b_value}
            continue
        if key not in a_protocol or key not in b_protocol:
            evidence_gaps.append(f'protocol.{key}: missing')
        elif a_protocol[key] != b_protocol[key]:
            protocol_changes[key] = {'baseline': a_protocol[key],
                                     'candidate': b_protocol[key]}

    for key in ('physics_version', 'runtime_physics', 'etcs_runtime', 'controller_runtime'):
        if key not in left['metadata'] or key not in right['metadata']:
            evidence_gaps.append(f'{key}: missing')
        elif left['metadata'][key] != right['metadata'][key]:
            evidence_gaps.append(f'{key}: differs; inspect before attributing effects')

    clean = not source_changes and not evidence_gaps and not protocol_changes
    if clean and len(config_changes) == 1:
        status = 'recorded_single_parameter_change'
    elif clean and not config_changes:
        status = 'same_recorded_setup'
    else:
        status = 'requires_review'
    return {
        'baseline': left['directory'], 'candidate': right['directory'],
        'status': status, 'source_changes': source_changes,
        'config_changes': config_changes, 'protocol_changes': protocol_changes,
        'evidence_gaps': evidence_gaps,
        'baseline_summary': left['summary'], 'candidate_summary': right['summary'],
        'scope': 'Recorded provenance only; does not prove physical validity.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    comparisons = [compare_archives(args.baseline, path) for path in args.candidate]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve previous audits; the caller must choose a new output filename.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(comparisons, stream, ensure_ascii=False, indent=2)
    for result in comparisons:
        print(f"{Path(result['candidate']).name}: {result['status']}; "
              f"source_changes={result['source_changes']}; "
              f"config_changes={list(result['config_changes'])}")


if __name__ == '__main__':
    main()
