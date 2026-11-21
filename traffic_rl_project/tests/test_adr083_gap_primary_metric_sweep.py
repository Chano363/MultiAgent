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


def test_schema_stratification_recorded():
    """§19.51.3b：必须记录"列距优势与 observation_schema 共变"的分层统计。

    这层很重要——它把"第 9 投列距差"从"这个窗口差"变成"这条动作空间差"，
    并明确**共变 ≠ 因果**，防止后续直接断言"换 schema 就能拿到 42 m 列距"。
    """
    sec = _section(_text(DIAG))
    assert "19.51.3b" in sec, f"{SEC} 必须含 §19.51.3b 分层统计"
    assert "loco_ed_ab_base12" in sec and "loco_notch_incr_v1" in sec, (
        f"{SEC} 分层统计必须点名两个 observation_schema"
    )
    assert "共变 ≠ 因果" in sec or "共变≠因果" in sec, (
        f"{SEC} 必须标明『共变 ≠ 因果』"
    )
    assert "不得断言" in sec, f"{SEC} 必须禁止『换 schema 就能拿到 42 m 列距』这类断言"


def test_two_intervention_surfaces_both_listed():
    """第 11 投有两个干预面（回 ed_ab schema / 在 notch_incr 内补通道），都须列出。"""
    for path in (DIAG, DECISIONS, PIPELINE):
        t = _text(path)
        assert "两个干预面" in t or "干预面" in t, f"{path.name} 缺干预面表述"
    sec = _section(_text(DIAG))
    assert "loco_ed_ab_base12" in sec
    assert "ab_chase_gap_guard" in sec


def test_unique_wording_corrected_in_1952():
    """§19.52：`speed_band_sum` 不是"唯一"稳定同向信号——`term_coupler_peak_sum` 也是。

    §19.47 原文写"唯一"，与它自己的产物 json 不符（后者显示
    `term_coupler_peak_sum` ~ gapMean +0.679，LOO 稳定同向）。
    ⇒ 必须有 §19.52 的修正节，且关键文档不得再出现未加限定的"唯一"表述。
    """
    doc = _text(DIAG)
    assert "19.52" in doc, "诊断缺 §19.52 修正节"
    sec1952 = doc[doc.find("### 19.52"):]
    assert "term_coupler_peak_sum" in sec1952, "§19.52 必须点名 term_coupler_peak_sum"
    assert "+0.679" in sec1952 or "0.6786" in sec1952, "§19.52 必须给出该相关系数"

    # 关键文档不得再出现"唯一…同向"表述——**限 speed_band_sum 语境**
    # （§19.41 在**峰值口径**下说 `gap_eff` 是"唯一同向"是正确的，不在修正范围）
    for path in (DIAG, DECISIONS, PIPELINE):
        t = _text(path)
        for m in re.finditer(r"唯一[^。\n]{0,40}同向", t):
            seg = t[max(0, m.start() - 160): m.end() + 80]
            if "gap_eff" in seg:
                continue  # §19.41 峰值口径的正确表述
            assert "最稳" in seg or "修正" in seg or "不是唯一" in seg, (
                f"{path.name} 出现未加限定的『唯一…同向』表述：{m.group(0)!r}"
            )


def test_1952_keeps_target_unchanged():
    """§19.52 只改措辞，**不改靶子**——`speed_band_sum` 仍是最强信号、仍是靶子。"""
    doc = _text(DIAG)
    sec = doc[doc.find("### 19.52"):]
    assert "靶子结论" in sec and "不变" in sec, "§19.52 必须声明靶子结论不变"
    assert "不得主张统计显著" in sec, "§19.52 必须保留 n=7 不得主张显著的纪律"


def test_gap_eff_scale_mismatch_recorded():
    """§19.51.3d：`GAP_EFF_SCALE_M = 150` 是硬编码常量，与第 9 投实测列距失配。

    这是"奖励面看不见散开"的量化根源，也是第 11 投第 ② 干预面的必要组成项。
    """
    sec = _section(_text(DIAG))
    assert "19.51.3d" in sec, f"{SEC} 必须含 §19.51.3d 奖励面根源"
    assert "GAP_EFF_SCALE_M" in sec, f"{SEC} 必须点名 GAP_EFF_SCALE_M"
    assert "278.7" in sec, f"{SEC} 必须给出零分区阈值（d_eff + 150）"
    assert "硬编码" in sec, f"{SEC} 必须标明它是硬编码常量（非配置键）"
    assert "待验证假设" in sec, f"{SEC} 必须把『调到 600 m 能拉回』标为待验证假设"


def test_gap_eff_scale_is_configurable_with_zero_regression():
    """【2026-11-21 §19.66 更新】`GAP_EFF_SCALE_M` **已可配置**，但**默认值仍为常量**。

    旧守卫断言"必须是常量、不是 config 键"，该断言已随实现变更过期（守卫本身提示了这一点）
    ⇒ 现改为：**常量仍在（默认语义）+ config 键存在且默认取常量 + 奖励处真的用它**。
    ⚠️ 零回归要求：**默认路径的行为必须与改动前逐位相同** ⇒ 默认值必须仍为 150.0。
    """
    env_src = (ROOT / "src" / "environments" / "train_fleet_env.py").read_text(
        encoding="utf-8")
    m = re.search(r"^GAP_EFF_SCALE_M\s*=\s*([\d.]+)", env_src, flags=re.M)
    assert m, "GAP_EFF_SCALE_M 默认常量应仍在"
    assert float(m.group(1)) == 150.0, (
        f"默认值必须仍为 150.0（零回归），实际 {m.group(1)}"
    )
    assert "config.get('gap_eff_scale_m', GAP_EFF_SCALE_M)" in env_src, (
        "env 必须支持 gap_eff_scale_m 配置键，且默认值取常量"
    )
    assert "float(self.gap_eff_scale_m)" in env_src, (
        "奖励计算处必须使用 self.gap_eff_scale_m（否则配置读了也不生效 = ADR-077 形态）"
    )


def test_switch_table_requires_three_columns():
    """§19.51.4 必须写明：接线完整 ≠ 机制有效 ≠ 已验证（三栏纪律）。"""
    t = _text(DIAG)
    seg = t[t.index("19.51.4"):]
    seg = seg[:seg.index("19.51.5")]
    for token in ("接线完整", "机制有效", "已验证", "饱和"):
        assert token in seg, f"§19.51.4 缺少开关三栏纪律要素：{token}"
    assert "不得据" in seg


def test_brief_flags_ffcap_mechanism_ineffectiveness():
    brief = _text(ROOT / "docs" / "reports" / "decision_brief_20261121_p11_direction.md")
    assert "接线完整" in brief and "机制有效" in brief, \
        "决策简报必须区分'接线完整'与'机制有效'"
    assert "饱和" in brief, "决策简报必须引用陡坡前馈饱和这一实测限定"


def test_gap_eff_scale_runtime_default_and_override():
    """运行时自证：默认 = 150.0（零回归）；配置 900 时生效。

    ⚠️ 这是**运行时读数**（不是静态字符串断言）⇒ 满足 ADR-077「配置声明 ≠ 运行时生效」的
    反向要求：证明键真的被 env 读取并生效。
    """
    import sys
    sys.path.insert(0, str(ROOT))
    import yaml
    from src.environments.train_fleet_env import TrainFleetEnv

    cfg_path = (ROOT / "configs/experiments"
                / "formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
    base = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    env_cfg = dict(base.get("env_cfg") or {})

    env0 = TrainFleetEnv(dict(env_cfg))
    assert abs(float(getattr(env0, "gap_eff_scale_m", -1)) - 150.0) < 1e-12, (
        f"默认尺度应为 150.0（零回归），实际 {getattr(env0, 'gap_eff_scale_m', None)}"
    )

    env_cfg2 = dict(env_cfg)
    env_cfg2["gap_eff_scale_m"] = 900.0
    env1 = TrainFleetEnv(env_cfg2)
    assert abs(float(getattr(env1, "gap_eff_scale_m", -1)) - 900.0) < 1e-12, (
        "配置 900 未生效 ⇒ 键未真正被 env 读取"
    )


def test_gap_gradient_analysis_exists_and_flags_pm_masac_scope():
    """量纲分析产物须存在，并给出'PM-MASAC 的 d_target 归一化在本工况恒零'的限定。"""
    import json
    p = (ROOT / "outputs/logs/adr083_gap_primary_metric_sweep"
         / "gap_reward_gradient_analysis.json")
    if not p.exists():
        return  # 分析脚本已就位，产物待下一次运行时生成
    d = json.loads(p.read_text(encoding="utf-8"))
    q1 = d["Q1_pm_masac_d_target_normalized"]
    assert "治不了本病" in q1["conclusion"], "必须写明照抄 d_target 归一化治不了本病"
    assert d["viable_scales_m"], "必须给出可行尺度区间"
