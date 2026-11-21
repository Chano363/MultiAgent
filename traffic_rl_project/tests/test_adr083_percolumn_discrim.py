"""§19.44 永久守卫：逐列可分性判定的结论不得被静默推翻。

钉住四类事实：
  1. 别名关系：`max_col_peak_kN` ≡ 总 peak、`sum_col_viol_steps` ≡ 总 viol
     —— 防止把"换个写法"当成逐列分解的新信息；
  2. 评估态侧结论：中列逐列 peak / 超限、列间 peak 极差可分 ep6 与 ep7 且误杀集空；
  3. 头列 / 尾列逐列 peak 与超限**无区分力**（ep6 排第 7 / 第 6）；
  4. 文档纪律：§19.44 必须在诊断文档里，且"评估态可分性 ≠ 训练期同向性"
     这个区分不得被抹掉（它是候选前提②的修订依据）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "docs/logs/diagnostics/DIAGNOSTICS_2026-11.md"
OUT = ROOT / "outputs/logs/adr083_percolumn_discrim/percolumn_discrim.json"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _res(d: dict) -> dict:
    return {r["metric"]: r for r in d["results"]}


def test_alias_relation_max_col_peak_equals_total_peak():
    """`max_col_peak_kN` 恒等于总 peak —— 不得当成逐列新信息。"""
    d = json.loads(_read(OUT))
    r = _res(d)
    assert r["max_col_peak_kN"]["is_global_alias"] is True, (
        "max_col_peak_kN 的别名标注被去掉 ⇒ 可能被误当作逐列分解的新信息")
    for ep, m in d["per_episode"].items():
        assert abs(max(m["train_peak_coupler_kN"]) - m["peak_coupler_kN"]) < 1e-6, (
            f"ep{ep}: max_col_peak 与总 peak 不等，别名关系被破坏")


def test_alias_relation_sum_col_viol_equals_total_viol():
    """`sum_col_viol_steps` 恒等于总 viol —— 不得当成逐列新信息。"""
    d = json.loads(_read(OUT))
    r = _res(d)
    assert r["sum_col_viol_steps"]["is_global_alias"] is True, (
        "sum_col_viol_steps 的别名标注被去掉")
    for ep, m in d["per_episode"].items():
        assert abs(sum(m["train_coupler_viol"]) - m["viol"]) < 1e-6, (
            f"ep{ep}: sum_col_viol 与总 viol 不等，别名关系被破坏")


def test_global_peak_alone_is_already_discriminative_in_eval():
    """评估态总 peak 本身就能把 ep6 排第 1、ep7 排第 3、误杀集空。

    ⇒ 这是 §19.44 的核心产物：**逐列分解相对总 peak 在评估态无可用增量**，
    真正的缺口是"训练期同向性"。若此事实被推翻，§19.44 的推论需重做。
    """
    d = json.loads(_read(OUT))
    r = _res(d)["GLOBAL_total_peak_kN"]
    assert r["rank_of_break_ep6"] == 1, r["rank_of_break_ep6"]
    assert r["single_threshold_can_isolate_ep6"] is True
    assert r["false_positive_includes_ep3"] is False
    assert r["false_positive_eps_at_that_threshold"] == []


def test_percolumn_couplermetrics_are_discriminative_and_clean():
    """中列逐列 peak / 超限步、列间 peak 极差：可分 ep6/ep7 且误杀集空。"""
    d = json.loads(_read(OUT))
    r = _res(d)
    for name in ("col1_peak_kN", "col1_viol_steps", "spread_col_peak_kN"):
        assert r[name]["usable"] is True, f"{name} 不再可用：{r[name]}"
        assert r[name]["rank_of_break_ep6"] == 1, name
        assert r[name]["false_positive_eps_at_that_threshold"] == [], name


def test_head_and_tail_column_peak_have_no_discriminative_power():
    """头列 / 尾列逐列 peak 与超限在评估态无区分力（ep6 排第 7 / 第 6）。

    ⇒ 若哪天它们变得"可用"，说明数据口径变了，§19.44 的"必须绑中列或离散度"
    结论需重做（不得静默沿用旧结论）。
    """
    d = json.loads(_read(OUT))
    r = _res(d)
    for name in ("col0_peak_kN", "col0_viol_steps",
                 "col2_peak_kN", "col2_viol_steps"):
        assert r[name]["single_threshold_can_isolate_ep6"] is False, (
            f"{name} 变成可分了：{r[name]} ⇒ §19.44 需重做")
        assert r[name]["rank_of_break_ep6"] >= 5, (
            f"{name} 的 ep6 排名变成 {r[name]['rank_of_break_ep6']}（原为 6–7）")


def test_diagnostics_contains_1944_with_key_distinctions():
    """§19.44 必须在诊断文档里，且三处关键区分不得被抹掉。"""
    txt = _read(DIAG)
    assert "§19.44" in txt, "诊断文档缺 §19.44"
    for kw in ("analyze_percolumn_discrim.py", "spread_col_peak_kN",
               "训练期的同向性", "别名"):
        assert kw in txt, f"§19.44 缺关键内容：{kw}"
    # "评估态侧的可分性"与"训练期的同向性"必须被写成两件事（措辞允许细微差异）
    assert "评估态侧的可分性" in txt and "训练期的同向性" in txt, (
        "§19.44 未把『评估态可分性』与『训练期同向性』区分为两件事")
