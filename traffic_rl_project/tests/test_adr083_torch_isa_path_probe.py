"""守卫：ADR-083 §19.48 四档补全 + §19.53 探针 C（策略前向 ISA 路径）判决落账。

钉住的东西：
  1. §19.53 必须存在，且含判决小节与前置写死的云端判读规则；
  2. 探针 C 产物必须记录"唯独 MKL SSE4.2 档不同 + 差值 = float32 的 1 eps"；
  3. §19.48 四档读数（0/1/10/100 ULP）必须与产物一致，且噪声下界必须写成 −20.8%；
  4. "放大系数"措辞必须已降级（禁止再把曲线称作放大系数 / 禁止拟合外推）；
  5. §19.53 不得被写成"根因已定位"（云端对照未做）；
  6. 探针 C 脚本不得触碰云端 API（零云端机时）。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md"
DECISIONS = ROOT / "docs" / "logs" / "decisions" / "DECISIONS.md"
PIPELINE = ROOT / "docs" / "PROJECT_PIPELINE.md"
PROBE = ROOT / "scripts" / "probes" / "probe_torch_isa_path.py"
PROBE_JSON = (ROOT / "outputs" / "logs" / "adr083_float_probe" / "torch_isa_path_probe.json")
AMP_JSON = (ROOT / "outputs" / "logs" / "adr083_float_probe" / "amplification_probe.json")


def _text(p):
    return p.read_text(encoding="utf-8")


def test_diag_has_19_53():
    t = _text(DIAG)
    assert "§19.53" in t
    seg = t[t.index("§19.53"):]
    for token in ("探针 C", "ISA", "1 ULP", "mkl_sse42", "56bb457aab560bbc",
                  "dc324208b1387f4f", "前置写死"):
        assert token in seg, f"§19.53 缺少关键内容：{token}"


def test_probe_result_records_sse42_only_diff():
    if not PROBE_JSON.exists():
        assert not AMP_JSON.exists(), "探针 C 产物缺失但放大曲线在 ⇒ 不一致"
        return
    j = json.loads(_text(PROBE_JSON))
    assert j.get("isa_sensitive") is True
    diff = j["diff_vs_baseline"]
    nonzero = [k for k, v in diff.items() if not v.get("bit_identical", True)]
    assert nonzero == ["mkl_sse42"], f"预期仅 mkl_sse42 档不同，实际：{nonzero}"
    d = diff["mkl_sse42"]["max_abs_diff"]
    assert abs(d - 2.0 ** -24) < 1e-15, f"mkl_sse42 差异应为 float32 的 1 eps，实际 {d}"


def test_four_ulps_in_amplification_result():
    if not AMP_JSON.exists():
        return
    j = json.loads(_text(AMP_JSON))
    by = {r["ulps"]: r for r in j["results"]}
    assert set(by) == {0, 1, 10, 100}, f"放大曲线档位不全：{sorted(by)}"
    assert by[0]["peak_coupler_kN"] == 1478.8515764313422
    assert by[1]["peak_coupler_kN"] == 1258.9060186688087
    assert by[10]["peak_coupler_kN"] == 1170.7331906611505
    assert by[100]["peak_coupler_kN"] == 1188.2765763081247
    # 漂移量在 1 ULP 之后不再随幅度单调增大
    d10 = by[10]["peak_coupler_kN"] - by[0]["peak_coupler_kN"]
    d100 = by[100]["peak_coupler_kN"] - by[0]["peak_coupler_kN"]
    assert d100 > d10, "100 ULP 档应高于 10 ULP 档（漂移非单调）"


def test_diag_records_four_ulps_and_new_bound():
    t = _text(DIAG)
    for token in ("1188.2765763081", "−20.8%", "−19.6%", "不再随扰动幅度单调增大"):
        assert token in t, f"诊断缺少 §19.48 四档回填内容：{token}"
    assert "−14.9%" in t


def test_magnitude_bound_is_tightened_to_20_8():
    for p in (DIAG, DECISIONS, PIPELINE):
        t = _text(p)
        assert "20.8%" in t, f"{p.name} 缺少收紧后的浮点噪声下界 −20.8%"


def test_amplification_term_is_downgraded():
    """'放大系数'措辞必须降级为'敏感度曲线'，且禁止拟合/外推。"""
    t = _text(DIAG)
    seg = t[t.index("§19.48"):]
    seg = seg[:seg.index("§19.49")]
    assert "敏感度曲线" in seg, "§19.48 未把措辞改为'敏感度曲线'"
    assert "不得" in seg and ("拟合" in seg or "外推" in seg)
    # 不得出现把四档读数当作已建立放大关系的断言
    assert not re.search(r"放大系数\s*(曲线|函数|关系)\s*(已|确已|已经)(建立|成立|拟合)", seg)


def test_19_53_not_claiming_root_cause_closed():
    t = _text(DIAG)
    seg = t[t.index("§19.53"):]
    assert "未在真实跨机上验证" in seg or "云端侧对照未做" in seg, \
        "§19.53 必须声明跨机对照尚未完成"
    assert "根因已定位" in seg and ("不成立" in seg or "若" in seg)


def test_probe_script_has_no_cloud_calls():
    src = _text(PROBE)
    for bad in ("aliyun", "ecs.c9i", "InstanceId", "DescribeInstances", "requests.post"):
        assert bad not in src, f"探针 C 出现云端调用痕迹：{bad}"


def test_decisions_and_pipeline_have_19_53():
    assert "§19.53" in _text(DECISIONS)
    assert "§19.53" in _text(PIPELINE)
