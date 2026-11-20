"""Runtime-effectiveness guards for the closer / billing-guard machinery.

WHY THIS FILE EXISTS (2026-11-21):
    tests/test_closer_registration_resilience.py asserts that the register
    scripts CONTAIN the hardening flags ("-StartWhenAvailable",
    "-RestartCount 3", "-AllowStartIfOnBatteries", ...). Those are STATIC
    string checks: they prove the source mentions a switch, not that the
    registered task actually carries it. That is precisely the ADR-077 family
    defect ("config declared != runtime effective") -- a flag present in the
    source but dropped at the settings layer would still pass every static
    test, and the W4 idle-burn incident would recur silently.

    Diagnostics 19.33 requires the three closer hardening fixes to be
    RE-TESTED before the next window opens. These tests provide that evidence
    offline and for free:
      * test_closer_registration_settings_resolve_at_runtime
        -- evaluates the REAL New-ScheduledTaskSettingsSet line out of the
        REAL register script, registers a throwaway probe task, reads it back
        with Get-ScheduledTask, and asserts the RESOLVED property values.
      * test_verifier_detects_unhardened_settings
        -- negative control: strips the hardening switches and asserts the
        verifier REJECTS them (a guard that cannot fail is worthless).
      * test_wrapper_exits_fast_on_bad_config
        -- runtime check of the wrapper's fail-fast path: an unreadable /
        incomplete config must exit non-zero in seconds, NOT enter the 20s
        self-heal loop (the ZTEST leftover that polluted the closer logs).

    These need Windows Task Scheduler, so they are skipped on non-Windows
    (the WSL test run). They are cheap: no cloud instance, no ssh, no billing.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "cloud"
VERIFY_PS1 = SCRIPTS / "verify_closer_settings.ps1"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows Task Scheduler runtime check; not available on WSL/linux",
)


def _run_ps(script: Path, *args: str, timeout: int = 180):
    exe = shutil.which("powershell") or shutil.which("powershell.exe")
    assert exe, "powershell not found"
    cmd = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _verify(register_script: Path, timeout: int = 180):
    proc = _run_ps(VERIFY_PS1, "-RegisterScript", str(register_script), timeout=timeout)
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
    assert payload is not None, f"verifier produced no JSON; rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return payload, proc


@pytest.mark.parametrize(
    "script_name",
    ["register_closer_pair.ps1", "register_billing_guard.ps1"],
)
def test_closer_registration_settings_resolve_at_runtime(script_name):
    """The hardening must survive into the RESOLVED task settings, not just the source."""
    payload, proc = _verify(SCRIPTS / script_name)
    assert payload.get("error") is None, payload
    assert payload.get("registered") is True, payload
    checks = payload["checks"]
    assert checks["disallow_start_if_on_batteries_false"], payload["resolved"]
    assert checks["stop_if_going_on_batteries_false"], payload["resolved"]
    assert checks["start_when_available_true"], payload["resolved"]
    assert checks["restart_count_ge_3"], payload["resolved"]
    assert checks["restart_interval_positive"], payload["resolved"]
    assert checks["multiple_instances_ignore_new"], payload["resolved"]
    assert checks["trigger_present"], payload["resolved"]
    assert payload["all_pass"] is True, payload
    assert proc.returncode == 0, proc.stdout


def test_verifier_detects_unhardened_settings():
    """Negative control: the verifier must REJECT the W4 incident conditions.

    Stripping the four hardening switches reproduces exactly the settings that
    killed the W4 guard (battery stop enabled, missed triggers not made up, no
    self-restart). If the verifier still passed this, it would be vacuous.
    """
    import tempfile

    src = (SCRIPTS / "register_closer_pair.ps1").read_text(encoding="utf-8")
    weak = (
        src.replace(" -AllowStartIfOnBatteries", "")
        .replace(" -DontStopIfGoingOnBatteries", "")
        .replace(" -StartWhenAvailable", "")
        .replace(" -RestartCount 3", "")
        .replace(" -RestartInterval (New-TimeSpan -Minutes 1)", "")
    )
    assert weak != src, "weakening transformation did not apply"
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as fh:
        fh.write(weak)
        tmp = Path(fh.name)
    try:
        payload, proc = _verify(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    assert payload["all_pass"] is False, payload
    assert payload["checks"]["stop_if_going_on_batteries_false"] is False, payload
    assert payload["checks"]["start_when_available_true"] is False, payload
    assert payload["checks"]["restart_count_ge_3"] is False, payload
    assert proc.returncode == 1, proc.stdout


def test_wrapper_exits_fast_on_bad_config():
    """Unreadable / incomplete config -> fail fast, never enter the self-heal loop."""
    wrapper = SCRIPTS / "closer_wrapper_resilient.ps1"

    # (a) config file does not exist at all
    t0 = time.time()
    proc = _run_ps(wrapper, "-Config", str(SCRIPTS / "__definitely_missing__.json"), timeout=60)
    dt = time.time() - t0
    assert proc.returncode == 3, proc.stdout
    assert "FATAL: cannot read config" in proc.stdout
    assert dt < 15, f"wrapper took {dt:.1f}s - it must not spin the self-heal loop"

    # (b) config exists but is missing required fields
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        fh.write(json.dumps({"run_tag": "zzbad", "instance": "i-xxx"}))
        bad = Path(fh.name)
    try:
        t0 = time.time()
        proc = _run_ps(wrapper, "-Config", str(bad), timeout=60)
        dt = time.time() - t0
    finally:
        bad.unlink(missing_ok=True)
    assert proc.returncode == 3, proc.stdout
    assert "FATAL: config incomplete" in proc.stdout
    assert dt < 15, f"wrapper took {dt:.1f}s - it must not spin the self-heal loop"


def _scheduled_task_names(pattern: str):
    """List scheduled task names matching a wildcard pattern (Windows only)."""
    exe = shutil.which("powershell") or shutil.which("powershell.exe")
    proc = subprocess.run(
        [
            exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"(Get-ScheduledTask -TaskName '{pattern}' -ErrorAction SilentlyContinue "
            f"| Select-Object -ExpandProperty TaskName) -join ','",
        ],
        capture_output=True, text=True, timeout=120,
    )
    raw = (proc.stdout or "").strip()
    return [t for t in raw.split(",") if t.strip()]


def test_drill_cannot_overwrite_a_live_guard_and_leaves_no_residue():
    """A closer DRILL must be fully isolated from a live window's guard.

    Two hazards this locks down:
      1. Task-name collision: the drill used the SAME task name as a real
         window ("<prefix>_closer_primary") and registered with -Force, so a
         drill on the same prefix silently REPLACED the running window's guard
         (including the wrapper state that carries the remaining deadline).
      2. Residue: the drill registered a task with a 5min repetition trigger
         (3-day duration) that kept re-launching itself long after the drill
         ended, polling a real instance.
    """
    reg = SCRIPTS / "register_closer_pair.ps1"
    prefix = "zzguard_test"
    run_tag = "zzguard_test"
    proc = _run_ps(
        reg,
        "-RunTag", run_tag,
        "-Ip", "127.0.0.1",
        "-DeadlineMin", "1",
        "-StartMarker", "zzguard_START",
        "-TaskPrefix", prefix,
        "-DryRun",
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout
    out = proc.stdout
    assert "DRILL_CLEANED" in out, out
    # the drill must use a DISTINCT task name, never the live one
    assert f"{prefix}_dryrun_closer_primary" in out, out
    assert f"task={prefix}_closer_primary" not in out, out
    # the drill config must carry the _dryrun suffix (log isolation)
    assert f"closer_{run_tag}_dryrun.json" in out, out
    # nothing may be left registered under the drill prefix
    leftover = _scheduled_task_names(f"{prefix}*")
    assert leftover == [], f"drill left scheduled tasks behind: {leftover}"
