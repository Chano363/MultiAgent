"""守卫：主指标浮点敏感度探针 `probe_primary_metric_sensitivity.py` 的契约。

钉住：
    1. 探针**必须同时产出两套口径**——工程口径（峰值/超限）与**主指标口径**
       （band_rate / gap_err_mean_abs_m / gap_err_peak_abs_m / gap_min_m）；
       只测峰值是不够的（§19.47 把主指标重定位到列距/速度带，
       §19.47 的相关性结论建立在这些读数上 ⇒ 必须知道它们自身的浮点噪声带）。
    2. 主指标口径的**采集口径必须与官方评估入口 `evaluate_decompose.py` 一致**
       （band = 领航机车速度落在 [v_min, v_max] 的步占比；
       gap_err = |info['gap_err_mean']| 的均值与峰值；gap_min = 全程最小列距；
       追尾 = 实际列距 ≤0 的步数）⇒ 不允许探针自己另立口径。
    3. 判读规则必须**前置写死**（主指标漂移 ≫ / ≪ §19.47 的信号幅度 两种判读），
       且必须写明"§19.47 结论是否可用"这个判决出口 —— 避免事后解释。
    4. 探针产出必须落盘 JSON 且带"不是判据、不得互引"的口径声明。

⚠️ 本守卫**不**跑仿真（整程 31500 步 × 多档约 18–20 min/档），
    只锁工具契约与判读规则的措辞；实数结果由计划任务产出。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "probes"))

import probe_primary_metric_sensitivity as pm  # noqa: E402


def test_probe_outputs_both_engineering_and_primary_metric_keys():
    """run_one 的返回结构必须同时含工程口径与主指标口径键。"""
    import inspect
    src = inspect.getsource(pm.run_one)
    for key in ("peak_coupler_kN", "coupler_violations", "band_rate",
                "gap_err_mean_abs_m", "gap_err_peak_abs_m", "gap_min_m",
                "rear_end_steps"):
        assert f'"{key}"' in src, f"run_one 未产出主指标/工程口径键 {key}"


def test_primary_metric_collection_matches_official_entry():
    """主指标采集口径必须与官方 evaluate_decompose.py 同源（逐项核对取数语句）。"""
    import inspect
    src = inspect.getsource(pm.run_one)
    ev = (ROOT / "src/evaluation/evaluate_decompose.py").read_text(encoding="utf-8")
    # band：官方口径 = env.v_min <= vel <= env.v_max 的步占比
    assert "env.v_min <= vel <= env.v_max" in src
    assert "env.v_min <= vel <= env.v_max" in ev
    # gap_err：官方口径 = info['gap_err_mean'] 的绝对值均值 / 峰值
    assert "info.get(\"gap_err_mean\"" in src
    assert "info.get('gap_err_mean'" in ev
    # gap_min：全程最小；追尾：实际列距 <= 0
    assert "info.get(\"gap_min_m\"" in src
    assert "info.get('gap_min_m'" in ev
    assert "gm <= 0.0" in src


def test_judgement_rule_is_written_in_advance():
    """判读规则必须前置写死，且含"§19.47 结论是否可用"的判决出口。"""
    doc = pm.__doc__ or ""
    assert "判读规则" in doc
    # 两种判读都要在
    assert "不可用" in doc and "不受浮点噪声威胁" in doc
    # 必须锚定 §19.47 的信号幅度（speed_band_sum 相关 +0.821）
    assert "0.821" in doc
    assert "speed_band_sum" in doc


def test_output_json_declares_non_criterion_boundary():
    """产出 JSON 必须带"不是判据、不得互引"的口径声明。"""
    import inspect
    src = inspect.getsource(pm.main)
    assert "不是峰值/安全判据" in src
    assert "primary_metric_sensitivity.json" in src


def test_perturb_helper_is_zero_identity_at_0_ulp():
    """0 ULP 必须是恒等（否则 0 档无法作为基线）。"""
    import numpy as np
    obs = np.array([1.0, -2.5, 0.3], dtype=np.float32)
    out = pm._perturb(obs, 0)
    assert np.array_equal(out, obs)
    # 1 ULP 必须是严格正向的一步
    out1 = pm._perturb(obs, 1)
    assert np.all(out1 >= obs)
    assert np.any(out1 > obs)
