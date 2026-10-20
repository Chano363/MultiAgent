"""Refine only the diagnostic ordinary-cycle rejection search near low speed."""


def retry_drop_kmh(reason, speed_kmh, original_drop):
    # Existing 0.3 km/h fine step; search granularity, not a vehicle parameter.
    if reason == 'stronger_air_request_required' and speed_kmh < 45.0:
        return 0.3
    return original_drop


def refined_retry_source(source):
    old = "head*3.6-(0.3 if head*3.6 < 43.0 else self.AB_SUPPRESS_MARGIN_MPS*3.6)"
    new = "head*3.6-retry_drop_kmh(result['reason'], head*3.6, (0.3 if head*3.6 < 43.0 else self.AB_SUPPRESS_MARGIN_MPS*3.6))"
    if source.count(old) != 1:
        raise ValueError('Expected exactly one diagnostic retry step')
    return ('from src.evaluation.refined_release_retry import retry_drop_kmh\n'
            + source.replace(old, new, 1))
