"""守卫：ADR-084 第 11 投开窗物料的**结构与口径**（不判科学结论，只钉可机检的部分）。

钉住：
  ① 开窗票据存在且含 G1 六问逐条留痕；
  ② 窗口 A（主线）配置相对第 9 投配置的 `env_cfg` **差异面恰为 2 键**，
     窗口 B（对照）配置**零差异**，且两者三目录同换**不同** run_tag；
  ③ 快评判据的列距通道**默认关闭**（零回归）且列距 nan ⇒ fail-closed；
  ④ `ab_physical_trigger` 的运行时自证脚本存在且含**对照侧**检查（证明读数来自配置）；
  ⑤ ADR-084 方向决定在 DECISIONS 与决策简报中都在场。
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / "docs" / "reports" / "decision_brief_20261121_p11_direction.md"
TICKET = ROOT / "docs" / "reports" / "adr084_window_open_checklist.md"
DECISIONS = ROOT / "docs" / "logs" / "decisions" / "DECISIONS.md"
BASE_CFG = (ROOT / "configs" / "experiments"
            / "formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
A_CFG = (ROOT / "configs" / "experiments"
         / "formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap.yaml")
B_CFG = (ROOT / "configs" / "experiments"
         / "formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap_ctrl.yaml")
VERIFY = ROOT / "scripts" / "probes" / "verify_ab_physical_trigger_runtime.py"
JUDGE = ROOT / "src" / "evaluation" / "cover_quick_eval.py"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _cfg(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_ticket_exists_with_six_questions():
    t = _text(TICKET)
    assert "G1" in t and "六问" in t
    for q in ("判据锚", "对标物", "从头训", "确定性快评协议", "ADR-070", "closer"):
        assert q in t, f"开窗票据缺少检查单项：{q}"
    assert "≤8.6 元" in t and "≤5.6 h" in t, "票据须写明红线 1 四件套"
    assert "P1" in t and "P2" in t, "票据须列出两项本地前置结果"


def test_window_a_diff_is_exactly_two_keys():
    base = _cfg(BASE_CFG)["env_cfg"]
    a = _cfg(A_CFG)["env_cfg"]
    diff = {k for k in set(base) | set(a) if base.get(k) != a.get(k)}
    assert diff == {"ab_physical_trigger", "ab_physical_avail_threshold"}, \
        f"窗口 A 差异面应恰为 2 键，实际 {diff}"
    assert a["ab_physical_trigger"] is True
    assert abs(float(a["ab_physical_avail_threshold"]) - 0.99) < 1e-12
    assert a.get("ed_notch_cap") == base.get("ed_notch_cap"), \
        "窗口 A 不得改动 ed_notch_cap（否则差异面不止 AB 通道）"


def test_window_b_is_zero_diff_control():
    base = _cfg(BASE_CFG)["env_cfg"]
    b = _cfg(B_CFG)["env_cfg"]
    diff = {k for k in set(base) | set(b) if base.get(k) != b.get(k)}
    assert diff == set(), f"窗口 B 必须零差异（对照侧），实际 {diff}"


def test_run_tags_differ_and_dirs_consistent():
    a = _cfg(A_CFG)["dirs"]
    b = _cfg(B_CFG)["dirs"]
    ta = {v.split("/")[3] for v in a.values()}
    tb = {v.split("/")[3] for v in b.values()}
    assert len(ta) == 1 and len(tb) == 1, "三目录必须同换同一个 run_tag"
    assert ta != tb, "窗口 A 与窗口 B 必须用不同 run_tag（禁覆写）"
    assert not (ta & tb)


def test_gap_criteria_default_off_and_failclosed():
    src = _text(JUDGE)
    assert "gap_max_abs_m" in src and "gap_rise_tol" in src
    # 默认关：签名里的两个阈值必须是 None 默认，且未启用时列距不参与判定
    m = re.search(r"def judge\((.*?)\)\s*->\s*dict:", src, flags=re.S)
    assert m, "找不到 judge 签名"
    sig = m.group(1)
    assert "gap_max_abs_m: Optional[float] = None" in sig
    assert "gap_rise_tol: Optional[float] = None" in sig
    assert "gap_enabled" in src, "必须有'未启用则列距不参与判定'的显式开关"
    assert "nan" in src, "启用后列距 nan 必须 fail-closed"


def test_runtime_verification_has_control_side():
    src = _text(VERIFY)
    assert "control_experiment" in src, "自证必须含对照侧（证明读数来自配置）"
    assert "multi_loco_controllers" in src, "自证必须取实际下发动作的 controller 列表"
    assert "reset" in src, "自证必须先 reset 再步进"


def test_adr084_recorded_in_decisions_and_brief():
    d = _text(DECISIONS)
    b = _text(BRIEF)
    assert "ADR-084" in d and "ab_physical_trigger" in d
    assert "ADR-084" in b
    assert "干预面②" in b, "简报须写明主线是干预面②"
    assert "≤8.6 元" in b and "1.52" in b
