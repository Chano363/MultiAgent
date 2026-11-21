"""守卫：§19.48「幅度类结论降级」纪律的**落地检查**。

背景（诊断 §19.48）：
    同机同码下，**仅 1 ULP** 的策略输入扰动即可让整程车钩峰值漂移 **−14.9%**、
    超限步数漂移 **−33.9%** ⇒ **凡"X 比 Y 好 N%"且 N 与该量级同阶的表述，
    都不足以区分"机制带来的改进"与"轨迹对浮点噪声的混沌敏感性"**。

为什么需要机器守卫（而不是只写文档）：
    诊断文档与 ADR 是**流水账**——旧段落原文保留是对的（历史可追溯），
    但**引用它们的人可能只看到"−21.7%"而没看到降级限定**
    ⇒ 必须保证**凡出现该幅度主张的地方，紧接着就有降级标注**，
    否则纪律会被无声地绕过（这正是 ADR-077 "以为它生效"同族的引用卫生问题）。

本守卫钉住：
    1. §19.48 的降级条款在**诊断文档**与 **DECISIONS.md** 中**都存在**；
    2. 关键幅度主张位置（`bias_n` −21.7% / `bias_g` −17.8% / ep6 破线 +11.0%）
       **附近必须出现降级标注关键词**（"§19.48" + "降级"）；
    3. 降级标注**必须同时说明哪些部分不受影响**（机制存在性 / 结构事实）
       —— 只降级不解释边界，等于把结论删掉，那是另一种失真；
    4. **执行规则第 10 条必须在 `EXECUTION_RULES.md` 中存在**，
       且必须含"只能表述为有可区分差异"的措辞。

⚠️ 本守卫只做**引用卫生**（文本存在性与结构），
    **不判断**任何幅度主张在事实上对不对（那是 ADR review + 人审的事）。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "docs/logs/diagnostics/DIAGNOSTICS_2026-11.md"
DEC = ROOT / "docs/logs/decisions/DECISIONS.md"
RULES = ROOT / "docs/rules/EXECUTION_RULES.md"


def _read(p: Path) -> str:
    assert p.exists(), f"缺文件：{p}"
    return p.read_text(encoding="utf-8")


def test_1948_section_exists_in_diagnostics():
    diag = _read(DIAG)
    assert "§19.48" in diag
    assert "1 ULP" in diag
    # 必须给出实测幅度，而不是只写结论
    assert "14.9%" in diag or "−14.9%" in diag


def test_1948_downgrade_clause_in_decisions():
    dec = _read(DEC)
    assert "§19.48" in dec
    idx = dec.find("§19.48")
    assert idx > 0
    seg = dec[idx:idx + 3000]
    # 必须含"降级"与"不得再主张"这类**禁止性**措辞
    assert "降级" in seg
    assert "幅度" in seg


def test_bias_magnitude_claims_carry_downgrade_marker():
    """bias 变体的幅度主张附近必须有降级标注。"""
    diag = _read(DIAG)
    # 定位 §19.34 的 bias 变体结论区（bias_n / bias_g 出现处）
    for key in ("bias_n", "bias_g"):
        idx = diag.find(key)
        assert idx > 0, f"诊断文档找不到 {key}"
    # 在文档中找含 −21.7% 的位置，其后 4000 字内必须有降级标注
    i217 = diag.find("−21.7%")
    assert i217 > 0, "找不到 −21.7% 的幅度主张"
    seg = diag[i217:i217 + 4000]
    assert "§19.48" in seg and "降级" in seg, \
        "−21.7% 幅度主张附近缺 §19.48 降级标注"
    # 同样检查 −17.8%
    i178 = diag.find("−17.8%")
    if i178 > 0:
        seg2 = diag[i178:i178 + 3000]
        assert "§19.48" in seg2 and "降级" in seg2, \
            "−17.8% 幅度主张附近缺 §19.48 降级标注"


def test_downgrade_states_what_is_unaffected():
    """降级标注必须说明**哪些部分不受影响**（机制存在性 / 结构事实）——
    只降级不解释边界 = 把结论删掉 = 另一种失真。"""
    diag = _read(DIAG)
    i217 = diag.find("−21.7%")
    seg = diag[i217:i217 + 4000]
    assert "不受影响" in seg
    assert "结构事实" in seg or "机制存在性" in seg


def test_execution_rule_10_exists_with_downgrade_wording():
    rules = _read(RULES)
    assert "10." in rules
    # 必须含"幅度类相对结论"这类小节标题
    assert "幅度类相对结论" in rules
    # 必须含"有可区分的差异"的措辞（降级后的替代表述）
    assert "有可区分的差异" in rules
    # 必须含浮点噪声带的实测数字
    assert "14.9%" in rules


def test_rule_11_cross_machine_band_exists():
    """§19.49 的规则第 11 条（跨机漂移带）也必须落规则。"""
    rules = _read(RULES)
    assert "跨机读数比较必须先测漂移带" in rules
    assert "53.5%" in rules
