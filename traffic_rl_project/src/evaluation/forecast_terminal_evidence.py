"""Observe the copied terminal forecast only; never save it as a restart."""
from contextlib import contextmanager
import copy


@contextmanager
def capture(predictor):
    original = predictor.forecast

    def forecast(env, manifest, steps):
        deepcopy, observed = copy.deepcopy, []

        def clone(obj, *args, **kwargs):
            result = deepcopy(obj, *args, **kwargs)
            if obj is env:
                observed.append(result)
            return result

        copy.deepcopy = clone
        try:
            data, summary = original(env, manifest, steps)
        finally:
            copy.deepcopy = deepcopy
        if len(observed) != 1:
            raise RuntimeError('Expected exactly one isolated forecast fleet clone')
        fleet = observed[0]
        summary['terminal_evidence'] = [dict(train=i+1,
            safety_events=list(t.safety.last_events),
            source_on=list(c._ab_on), controller_step=c._ab_step,
            last_release_steps=list(c._ab_last_release_step),
            release_threshold_kmh=c.cyclic_release_kmh,
            one_cycle_override_active=getattr(c, '_ready_cycle_override_active', False),
            sync_consumed=getattr(c, '_phase_sync_consumed', None))
            for i, (t, c) in enumerate(zip(fleet.trains, fleet.multi_loco_controllers))]
        return data, summary

    predictor.forecast = forecast
    try:
        yield
    finally:
        predictor.forecast = original
