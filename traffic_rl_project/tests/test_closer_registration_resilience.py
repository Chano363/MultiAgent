"""Static guard for the closer/billing-guard SCHEDULTASK registration scripts.

Root cause guarded (2026-11-20 idle-burn incident): register_closer_pair.ps1
registered both closers with NO -Trigger and Interactive logon. Once the
wrapper process died with the interactive session, the tasks turned Ready and
never came back (all 4 historical closer tasks found dead). Self-heal inside
the wrapper cannot help if the wrapper itself is gone.

These tests assert the registration scripts keep the three resilience
properties, so a future edit cannot silently drop them again:
  1. periodic repetition trigger (dead wrapper is re-launched within minutes);
  2. MultipleInstances=IgnoreNew (no duplicate python while one is running);
  3. privileged-logon attempt with Interactive fallback (S4U / SYSTEM), so the
     guard works whenever the session permits and degrades safely otherwise;
  4. billing guard exists and is pure-API (no ssh) with its own trigger;
  5. both scripts are ASCII-only (PS 5.1 mis-decodes BOM-less UTF-8 and breaks
     parsing -- a Chinese comment actually caused a silent registration failure
     during the fix, see diagnostics 19.32.3).
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "cloud"

CLOSER_REG = SCRIPTS / "register_closer_pair.ps1"
BILLING_REG = SCRIPTS / "register_billing_guard.ps1"
BILLING_GUARD = SCRIPTS / "billing_guard.py"


@pytest.fixture(scope="module")
def closer_src() -> str:
    return CLOSER_REG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def billing_src() -> str:
    return BILLING_REG.read_text(encoding="utf-8")


def test_scripts_ascii_only():
    """PS 5.1 + BOM-less UTF-8: non-ASCII breaks parsing (incident reproduced)."""
    for p in (CLOSER_REG, BILLING_REG):
        raw = p.read_bytes()
        bad = [b for b in raw if b > 0x7F]
        assert not bad, f"{p.name} contains non-ASCII bytes {bad[:8]!r}"


def test_closer_has_repetition_trigger(closer_src):
    assert "-Trigger" in closer_src
    assert "New-ScheduledTaskTrigger" in closer_src
    assert "-RepetitionInterval" in closer_src
    assert "-RepetitionDuration" in closer_src


def test_closer_ignore_new_instances(closer_src):
    assert "MultipleInstances" in closer_src and "IgnoreNew" in closer_src


def test_closer_tracks_remaining_deadline(closer_src):
    """Wrapper recomputes remaining minutes from the absolute deadline on each
    (re)start, so a self-heal can never extend the billing window."""
    wrapper = (SCRIPTS / "closer_wrapper_resilient.ps1").read_text(encoding="utf-8")
    assert "deadlineAbs" in wrapper
    assert "TotalMinutes" in wrapper
    assert "remain" in wrapper


def test_closer_privileged_logon_with_fallback(closer_src):
    assert "S4U" in closer_src
    # register itself must be inside try (S4U principal creation succeeds but
    # Register fails on non-admin sessions -- that was a silent-failure trap).
    assert "fallback Interactive" in closer_src


def test_billing_guard_registration_exists(billing_src):
    assert "-Trigger" in billing_src
    assert "-RepetitionInterval" in billing_src
    assert "MultipleInstances" in billing_src and "IgnoreNew" in billing_src


def test_billing_guard_is_pure_api():
    src = BILLING_GUARD.read_text(encoding="utf-8")
    assert "StopInstance" in src and "DescribeInstances" in src
    # no ssh subprocess: the whole point is survival when ssh is unavailable.
    assert "subprocess" not in src
    assert "stop-after" in src


def test_billing_guard_iso_deadline_validated(billing_src):
    """ISO 'T' separator is validated (schtasks argument splitting hazard)."""
    assert "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}" in billing_src
