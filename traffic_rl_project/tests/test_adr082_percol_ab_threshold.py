"""Guards for the per-column AB derive thresholds (diagnostics 19.35, 2026-11-21).

The mechanism (`ab_derive_threshold_lead` / `ab_derive_threshold_follower`)
existed in code but had never been enabled in any config. Three real defects
were found while enabling it, and the first two are exactly the ADR-077 family
("declared in config != actually in effect"):

1) The probe's runtime assertion was written as
       assert (got is None or abs(got - want) < 1e-9)
   so a FAILED delivery (got=None) PASSED the assertion. That is how five
   variants ended up with byte-identical trajectories and looked like a
   "no effect" result. The assertion must be strict equality.

2) The thresholds are delivered to the controllers inside
   `_step_decomposed_fleet` (train_fleet_env.py), i.e. DURING step. An
   assertion taken at construction time therefore always reads None and would
   always fail once fixed to strict equality. Delivery must be checked after
   the first step.

3) The mechanism is saturated in the default configuration: the decision is
   `want_on = n_k >= thr` while the notch level n_k is capped by
   `ed_notch_cap` (0.75). Any threshold <= 0.72 is therefore equivalent to
   the default 0.5 and CANNOT change behaviour. This is a property of the
   intervention point, not a delivery bug -- and it must be detectable before
   a scan is launched, otherwise a scan "finds nothing" for the wrong reason.

These tests lock all three so a later edit cannot silently reopen them.
"""
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FLEET_ENV_PY = ROOT / "src" / "environments" / "train_fleet_env.py"
CONTROLLER_PY = ROOT / "src" / "controllers" / "multi_loco_controller.py"
PROBE_PY = ROOT / "scripts" / "probes" / "probe_percol_ab_threshold.py"
REGISTRY_PY = ROOT / "src" / "trainer" / "registry.py"
BASE_YAML = ROOT / "configs" / "experiments" / "formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml"


# --- 1) probe assertion must be strict equality, not "None passes" -------------

def test_probe_assertion_is_strict_equality():
    """A failed delivery (None) must FAIL the probe assertion."""
    src = PROBE_PY.read_text(encoding="utf-8")
    # only the ASSERTION lines matter: an unrelated `x is None or ...` in
    # ordinary control flow is legitimate and must not trip this guard.
    asserts = [ln for ln in src.splitlines()
               if ln.lstrip().startswith("assert")]
    assert asserts, "probe has no runtime assertion at all"
    bad = [ln for ln in asserts if "is None or" in ln]
    assert not bad, (
        "probe assertion still lets None pass -- a failed delivery would be "
        "reported as success (ADR-077 family defect, diagnostics 19.35): %s"
        % bad)
    # strict equality form must be present
    assert any("== lead_thr" in ln for ln in asserts), (
        "probe must compare the delivered lead threshold with strict equality")
    assert any("== foll_thr" in ln for ln in asserts), (
        "probe must compare the delivered follower threshold with strict "
        "equality")


def test_probe_asserts_after_first_step():
    """Delivery happens during step, so the ctrl-side assert must be after it."""
    src = PROBE_PY.read_text(encoding="utf-8")
    step_at = src.find("env.step(actions)")
    assert step_at > 0, "probe no longer steps the env"
    # the ctrl-side assert block must live after the first step
    assert src.find("if i == 0:", step_at) > 0, (
        "ctrl-side delivery assertion must run inside the step loop")
    assert src.find("ab_derive_threshold_lead", step_at) > 0, (
        "ctrl-side delivery assertion must be after the first step")


# --- 2) env reads the keys and delivers them per column ------------------------

def test_env_reads_both_threshold_keys():
    src = FLEET_ENV_PY.read_text(encoding="utf-8")
    for key in ("ab_derive_threshold_lead", "ab_derive_threshold_follower"):
        assert "config.get('%s')" % key in src, (
            "env never reads %s from config -> dead config" % key)
    # delivery must be per column: lead only on ti == 0, follower only on ti > 0
    assert "(ti == 0 and _lead_thr is not None)" in src, (
        "lead threshold must only reach column 0")
    assert "(ti > 0 and _foll_thr is not None)" in src, (
        "follower threshold must only reach columns > 0")


def test_controller_uses_per_column_threshold():
    src = CONTROLLER_PY.read_text(encoding="utf-8")
    assert "self.ab_derive_threshold_lead is not None" in src, (
        "controller never consults the per-column lead threshold")
    assert "self.ab_derive_threshold_follower is not None" in src, (
        "controller never consults the per-column follower threshold")


def test_training_path_passes_env_cfg_through():
    """The training entry point must hand the YAML env_cfg to the env.

    Otherwise the mechanism is evaluation-only and a training window would
    silently run with the thresholds disabled.
    """
    src = REGISTRY_PY.read_text(encoding="utf-8")
    assert "TrainFleetEnv(cfg.env_cfg)" in src, (
        "training path no longer constructs the env from the YAML env_cfg -> "
        "the threshold keys would not reach the env during training")


# --- 3) saturation is detectable ----------------------------------------------

def test_default_config_is_saturated_against_the_threshold():
    """Document (and detect) that the default cap makes <=0.72 thresholds inert.

    The notch level is capped at `ed_notch_cap`; the AB derive decision is
    `n_k >= thr`. If the cap is <= the smallest threshold we ever scanned, the
    scan cannot possibly produce a difference -- so the saturation must be
    checked BEFORE launching a scan.
    """
    cfg = yaml.safe_load(BASE_YAML.read_text(encoding="utf-8"))
    env_cfg = cfg["env_cfg"]
    cap = float(env_cfg.get("ed_notch_cap", 1.0))
    default_thr = float(env_cfg.get("ab_derive_threshold", 0.5))
    # the threshold scan range that turned out to be inert
    inert_max = 0.72
    assert cap >= inert_max, (
        "ed_notch_cap=%r changed -- the saturation argument in diagnostics "
        "19.35 must be re-checked (thresholds <= %r may now be live)"
        % (cap, inert_max))
    # with a cap at/above the inert range, thresholds in that range are
    # equivalent to the default whenever n_k sits at the cap
    assert default_thr < cap, (
        "default threshold %r >= cap %r means the AB derive path can never "
        "trigger from the notch level" % (default_thr, cap))


def test_threshold_is_validated_in_range():
    """A threshold outside (0,1) would silently disable the mechanism."""
    # the global-threshold validation lives in the env, not the controller
    src = FLEET_ENV_PY.read_text(encoding="utf-8")
    assert "must be in (0,1)" in src, (
        "the (0,1) range validation for the AB derive threshold is gone -- "
        "an out-of-range threshold would silently disable the mechanism")


@pytest.mark.parametrize("thr", [0.85, 0.90, 0.95])
def test_threshold_above_cap_is_distinguishable(thr):
    """A threshold above the cap is actually able to change behaviour.

    Sanity check of the arithmetic that diagnostics 19.35.3 relies on:
    with the notch level at the cap, `n_k >= thr` is False for thr > cap.
    """
    cap = 0.75
    n_k_at_cap = 0.75
    assert not (n_k_at_cap >= thr)
    assert (n_k_at_cap >= 0.72) is True, (
        "thresholds below the cap must stay equivalent to each other")
