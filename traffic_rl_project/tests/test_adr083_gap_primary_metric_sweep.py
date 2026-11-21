"""§19.51 守卫：主指标口径的全库盘点结论的**引用卫生**与**口径边界**。

背景（§19.51）：
    owner 方向纠偏（"车钩力压下来之后不就在做列距吗"）后，把分析重心从**峰值**移到
    **列距/速度带**，对全库 44 条同编组/同物理版本/同整程协议的官方读数做了横切盘点。
    结论：第 9 投窗口（ep2/4/6 + adr083_official ep1）在**峰值**上最优，
    但在**主指标（列距）**上是同协议**最差档之一**（gap_err_mean 598–983 m，
    比列距最好档 41.8–55.6 m 差 11–23 倍）。

本守卫的作用（**不判内容对错，只钉引用纪律**，与 check_agents_links 同款边界）：
    ① 诊断文档必须存在 §19.51 且含"峰值最优但列距最差"的判决；
    ② **禁止**把"第 9 投窗口"无条件称为"最好结果"而不带口径限定；
    ③ 必须保留**不可比项的排除说明**（20kt 规则基线 / MPC 行），
       防止后续把 gap_err 与异源参照并排；
    ④ 必须保留**判据归属**声明（方向属 owner，本节不构成拍板）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md"
PIPELINE = ROOT / "docs" / "PROJECT_PIPELINE.md"
DECISIONS = ROOT / "docs" / "logs" / "decisions" / "DECISIONS.md"

SEC = "§19.51"


def _text(path: Path) -> str:
    assert path.exists(), f"缺文件：{path}"
    return path.read_text(encoding="utf-8")


def _section(doc: str) -> str:
    """截取 §19.51 小节正文（到下一个同级 `## ` 标题或文件尾）。"""
    m = re.search(rf"^## {re.escape(SEC)}.*$", doc, flags=re.M)
    assert m, f"诊断文档缺 {SEC} 小节"
    nxt = re.search(r"^## ", doc[m.end():], flags=re.M)
    return doc[m.start(): m.end() + nxt.start()] if nxt else doc[m.start():]


def test_diag_has_section_1951():
    doc = _text(DIAG)
    sec = _section(doc)
    assert len(sec) > 1500, f"{SEC} 正文过短，疑为占位"
    for kw in ("19.51.1", "19.51.2", "19.51.3", "19.51.4", "19.51.5", "19.51.6"):
        assert kw in sec, f"{SEC} 缺小节 {kw}"


def test_section_states_peak_best_but_gap_worst():
    """判决句必须同时含"峰值最优"与"列距最差"两个面，防止只留一面。"""
    sec = _section(_text(DIAG))
    assert "峰值最优" in sec and "列距最差" in sec, (
        f"{SEC} 必须同时陈述『峰值最优』与『列距最差』两面"
    )
    assert "gap_err_mean" in sec, f"{SEC} 必须落到具体指标键"
    assert "11–23" in sec or "11-23" in sec, f"{SEC} 必须给出量级差倍数"


def test_section_keeps_incomparable_exclusions():
    """必须显式排除 20kt 规则基线与 MPC 行（异源参照不得并排）。"""
    sec = _section(_text(DIAG))
    assert "20kt_1plus108_1plus108" in sec, f"{SEC} 必须指明 20kt 基线编组不同源"
    assert "10kt_1plus108" in sec, f"{SEC} 必须写明纳入的编组"
    assert "不得与 MPC 行并排" in sec or "不可与 MPC 行并排" in sec, (
        f"{SEC} 必须保留 MPC 行的参照不同源警示"
    )


def test_section_declares_not_an_owner_decision():
    """方向归属 owner；本节不得自称拍板。"""
    sec = _section(_text(DIAG))
    assert "不构成对第 11 投的拍板" in sec, f"{SEC} 必须声明不构成 owner 拍板"
    assert "待验证假设" in sec, f"{SEC} 必须把『开闸能拉回列距』标为待验证假设"


def test_section_zero_machine_time_and_n_boundary():
    sec = _section(_text(DIAG))
    assert "零新增机时" in sec, f"{SEC} 必须声明零新增机时"
    assert "n = 44" in sec, f"{SEC} 必须写明样本量 n"
    assert "不得当显著结论" in sec, f"{SEC} 必须保留 n 小不得主张显著的纪律"


def test_pipeline_and_decisions_have_1951():
    """计划与决策台账都必须有 §19.51 的条目（防止只写在诊断里、正本缺失）。"""
    assert SEC in _text(PIPELINE), f"PROJECT_PIPELINE.md 缺 {SEC} 条目"
    assert SEC in _text(DECISIONS), f"DECISIONS.md 缺 {SEC} 条目"


def test_no_unqualified_best_result_claim():
    """禁止出现无口径限定的『第 9 投窗口 = 最好结果』表述。"""
    doc = _text(DIAG)
    bad = re.findall(r"第 ?9 ?投窗口[^。\n]{0,20}(?<!不)(?<!非)(?<!并非)最好结果", doc)
    assert not bad, f"出现无口径限定的『最好结果』表述：{bad[:3]}"


def test_switch_wiring_state_is_recorded():
    """§19.51.4 必须区分"完整接线"与"死代码（只读属性、无使用点）"。

    背景：`ab_chase_gap_guard` 一族在 env 里只被读成属性，**全仓无任何使用点**
    ⇒ 属死代码（ADR-077 的镜像形态），与"配置缺失"是**两件事**，
    必须分别陈述，否则会误导"加一行配置就能启用"。
    """
    sec = _section(_text(DIAG))
    assert "接线核实" in sec, f"{SEC} 必须含接线核实表"
    assert "未接线" in sec, f"{SEC} 必须标出未接线的开关"
    assert "死代码" in sec, f"{SEC} 必须把『死代码』与『配置缺失』分开"
    # 完整接线的两个开关也要点名，避免只说坏消息
    assert "ed_feedforward_cap" in sec and "ab_physical_trigger" in sec


def test_switch_wiring_matches_code():
    """守卫接线断言本身与代码一致：读 env 的属性定义 + grep 下游使用点。"""
    env_src = (ROOT / "src" / "environments" / "train_fleet_env.py").read_text(
        encoding="utf-8")
    ctrl_src = (ROOT / "src" / "controllers" / "multi_loco_controller.py").read_text(
        encoding="utf-8")

    # 三个开关在 env 侧都有属性定义
    for key in ("ab_chase_gap_guard", "ab_physical_trigger", "ed_feedforward_cap"):
        assert key in env_src, f"env 侧缺 {key} 的属性定义"

    # 完整接线的两个：controller 侧必须有属性 + 使用点
    for key in ("ab_physical_trigger", "ed_feedforward_cap"):
        assert key in ctrl_src, f"controller 侧缺 {key}"
        uses = len(re.findall(rf"self\.{key}", ctrl_src))
        assert uses >= 2, f"{key} 在 controller 侧只有属性定义、无使用点"

    # 未接线的一个：controller 侧**不得**出现该键（否则守卫结论过期）
    assert "ab_chase_gap_guard" not in ctrl_src, (
        "ab_chase_gap_guard 已在 controller 侧接线 ⇒ §19.51.4 的接线表已过期，"
        "请更新诊断与本守卫"
    )
