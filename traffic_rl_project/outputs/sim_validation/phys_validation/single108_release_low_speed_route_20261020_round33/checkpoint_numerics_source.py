"""Resume experimental mechanics only with matching frozen implementation."""
import hashlib
from contextlib import ExitStack
from pathlib import Path

from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.fractional_air_timing import fractional_air_timing
from src.evaluation.refine_pneumatic_interval import refined_pneumatic_interval


def verify_checkpoint_numerics(manifest):
    record = manifest.get('experimental_numerical_solver')
    if not isinstance(record, dict) or not record.get('experimental_numerical_solver'):
        raise ValueError('Expected an explicitly experimental numerical checkpoint')
    root = Path(__file__).parent
    if record.get('solver_sha256') != hashlib.sha256(
            (root/'adaptive_newmark_candidate.py').read_bytes()).hexdigest():
        raise ValueError('Checkpoint mechanical implementation differs')
    for name in ('newton_mechanics_candidate', 'native_force_tangent',
                 'fractional_air_timing', 'refine_pneumatic_interval'):
        if record.get('frozen_sources_sha256', {}).get(name) != hashlib.sha256(
                (root/(name+'.py')).read_bytes()).hexdigest():
            raise ValueError(f'Checkpoint numerical implementation differs: {name}')
    settings = record['settings']
    if settings.get('solver') not in ('balanced', 'newton_analytic'):
        raise ValueError('Unknown checkpoint numerical solver')
    return settings


def checkpoint_numerical_context(manifest, train, samples):
    settings = verify_checkpoint_numerics(manifest)
    stack = ExitStack()
    try:
        stack.enter_context(fractional_air_timing(settings['fractional_air_timing']))
        stack.enter_context(refined_pneumatic_interval(settings['air_step_s'], hold_coarse_grade=True))
        stack.enter_context(coupled_candidate(samples, live_dynamics={train.dynamics},
            max_step=settings['max_step_s'], force_tol_n=settings['force_tolerance_n'],
            tol=settings['displacement_tolerance_m'], max_iter=settings['max_iter'],
            numerical_solver=settings['solver'], ramp_air_force=settings['ramp_air_force']))
    except BaseException:
        stack.close()
        raise
    return stack
