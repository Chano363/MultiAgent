import builtins
import os

_original_print = builtins.print

def suppress_prints():
    """Suppress non-critical prints unless TRAFFIC_RL_VERBOSE=1.

    Keeps prints that likely indicate errors or warnings (contain 'ERROR' or 'WARNING').
    """
    if os.getenv('TRAFFIC_RL_VERBOSE', '0') == '1':
        return

    def _print(*args, **kwargs):
        try:
            if not args:
                return
            first = args[0]
            if isinstance(first, str) and ("ERROR" in first or "Error" in first or "WARNING" in first or "Warning" in first):
                _original_print(*args, **kwargs)
            else:
                # suppressed
                return
        except Exception:
            return

    builtins.print = _print
