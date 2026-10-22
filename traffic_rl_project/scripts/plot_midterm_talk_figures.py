"""中期答辩 PPT 配图生成（数据图 + 框图）。

用途（生图规范：数据与绘图分离，从已归档数据/源码内嵌线路数据直接重画，不重跑仿真）：
    python scripts/plot_midterm_talk_figures.py data    # 英文数据图：49.6km 纵断面 + 车钩力柱状
    python scripts/plot_midterm_talk_figures.py blocks  # 中文框图：计划进度条 / 环境模块 / MARL 架构
    python scripts/plot_midterm_talk_figures.py all

输出目录：ppt_talk/midterm_20261018/images/
运行环境：Windows Anaconda（D:/Anaconda/python.exe，含 matplotlib + Microsoft YaHei）。

数据来源：
- 49.6 km 纵断面 = src/train_dynamics/grade_profile.py::profile_shuozhou_ningwuxi_beidaniu_49km
  （真实线路数据，0.1km 粒度合并为 50 坡段，高程由坡度积分重建，零基点）。
- 页 9 对照三柱（1268.9 / 777.1 / 768.1 kN）= 诊断日志 2026-09B X 系列受控实验
  （X4-a 在飞波锁 + no_rl 对照），手工数据内嵌；1000 kN 限值线 = ADR-040 验收线。
  2026-10-20 归因更正：原"信用分配改进实验"口径与一手记录不符，已作废
  （真实语义 = 在飞波锁受控实验，见 fig_coupler_credit docstring）。
- 页 8 对照图（惩罚信号 + 拦截）= docs/logs/diagnostics/DIAGNOSTICS_2026-10.md
  「改造-2026-10-01」：C 表（生产函数解析核对：超限项 6·min(pn−1,2)，pn≥3 触顶 12）+
  D on/off 隔离对照（ab_safety_vetoed 0 → 35 次，同一确定性策略 12000 步窗口）+
  A_on 充风约束拒绝新增源 6657 次；改造前曲线按 C 表增量口径 −0.2·peak_norm 绘制。
  均为前期两万吨方案（ADR-039 之前）数字，图题带"前期方案"标注。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from matplotlib.lines import Line2D

OUT = ROOT / "ppt_talk" / "midterm_20261018" / "images"
DPI = 300

# 中文字体（框图用）；数据图英文用默认 DejaVu
CJK = ["Microsoft YaHei", "SimHei"]


# ---------------------------------------------------------------- 数据图 ----
def fig_profile_49km() -> None:
    """朔黄线宁武西→北大牛 49.6 km 真实纵断面（高程 + 坡度双面板，中文标注）。"""
    from train_dynamics.grade_profile import profile_shuozhou_ningwuxi_beidaniu_49km

    _setup_cjk()
    prof = profile_shuozhou_ningwuxi_beidaniu_49km()
    segs = prof.segments
    total_m = 49600.0
    starts = [s.start_m for s in segs]
    ends = starts[1:] + [total_m]
    grades = [s.grade_permille for s in segs]

    # 高程由坡度积分重建（零基点）：elev_drop = grade_frac * length
    elev = [0.0]
    for s, e in zip(segs, ends):
        elev.append(elev[-1] + (s.grade_permille / 1000.0) * (e - s.start_m))
    km = [x / 1000.0 for x in starts + [total_m]]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10.5, 5.6), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.0]}
    )
    ax1.plot(km, elev, color="#1f4e79", lw=2.4)
    ax1.fill_between(km, elev, color="#1f4e79", alpha=0.12)
    ax1.set_ylabel("高程 (m)", fontsize=14)
    ax1.tick_params(labelsize=12)
    ax1.grid(alpha=0.3, lw=0.6)
    ax1.set_title("朔黄线宁武西—北大牛 49.6 km 真实纵断面", fontsize=15)

    ax2.step(km, grades + [grades[-1]], where="post", color="#c0504d", lw=1.8)
    ax2.axhline(0.0, color="#888888", lw=0.8)
    ax2.set_ylabel("坡度 (‰)", fontsize=13)
    ax2.set_xlabel("里程 (km)", fontsize=14)
    ax2.tick_params(labelsize=12)
    ax2.grid(alpha=0.3, lw=0.6)
    ax2.annotate("最陡 -12.0‰", xy=(16.9, -12.0), xytext=(21.5, -7.4),
                 fontsize=11, color="#c0504d",
                 arrowprops=dict(arrowstyle="-", color="#c0504d", lw=0.9))

    fig.align_ylabels()
    fig.tight_layout()
    fig.savefig(OUT / "fig_profile_49km.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig_coupler_credit() -> None:
    """关键问题二（页 9）：受控对照实验分离决策因素与物理因素（前期方案口径，中文标注）。

    2026-10-20 归因更正（负责人拍板）：原图题"信用分配改进降低车钩力峰值"与一手
    记录不符——1268.9 → 777.1 kN 的真实语义为「在飞波锁」受控实验（锁死 RL 新增
    空气制动源，诊断 09B X4-a），官方结论"疗效确证但不是可部署解"（AB 杠杆全锁）。
    页 9 诚实重构：图改为对照三柱，承载"决策因素与物理因素分离"证据；逐智能体
    贡献估计的量化收益待 10–11 月训练产出，图中不出现。

    数据来源（docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md §一/§二 X 系列实验）：
    - 基线策略（采样探索态、无锁）1268.9 kN / 越限 29 步；
    - 锁定新增空气制动源（在飞波锁）777.1 kN / 0 越限（与闸门开关无关）；
    - 纯规则基线（no_rl 对照）768.1 kN / 0 越限。
    锁源后 ≈ 纯规则水平 ⇒ 破线由策略新增空气制动源（决策因素）造成，物理滞后不破线。
    口径纪律：全部为前期两万吨方案（ADR-039 之前）数字，图题带"前期方案"标注。
    """
    _setup_cjk()
    labels = ["基线策略", "锁定新增\n空气制动源", "纯规则基线"]
    vals = [1268.9, 777.1, 768.1]
    colors = ["#8c9aa6", "#2a9d8f", "#2b5d8a"]

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    bars = ax.bar(labels, vals, width=0.52, color=colors, edgecolor="white")
    ax.axhline(1000.0, color="#d62728", ls="--", lw=1.8)
    ax.text(2.42, 1025, "1000 kN 限值", color="#d62728", fontsize=12.5,
            ha="right", va="bottom")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 28, f"{v:.1f}",
                ha="center", fontsize=14, fontweight="bold")
    ax.annotate("", xy=(1.06, 745), xytext=(0.18, 1240),
                arrowprops=dict(arrowstyle="-|>", color="#1a1a1a", lw=1.5,
                                connectionstyle="arc3,rad=-0.25"))
    ax.text(0.66, 1150, "-38.8%", fontsize=14, color="#1a1a1a", fontweight="bold")
    ax.set_ylabel("车钩力峰值 (kN)", fontsize=14)
    ax.set_ylim(0, 1450)
    ax.tick_params(labelsize=13)
    ax.set_title("前期方案：受控对照实验分离决策因素与物理因素", fontsize=15)
    ax.grid(axis="y", alpha=0.3, lw=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig_coupler_credit.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig_signal_safety() -> None:
    """关键问题一（页 8）：学习信号与安全底线的改造前后对照（前期方案口径，中文标注）。

    2026-10-20 简化（负责人拍板）：图内解释文字全部删除、改页面文案与备注承载——
    只留曲线 / 柱 / 最小图例；"速度带收益 +6 参考线""充风约束 6657 次"等口径说明下架。

    数据来源（docs/logs/diagnostics/DIAGNOSTICS_2026-10.md「改造-2026-10-01」）：
    - 面板 A 改造后曲线 = 生产函数 _calculate_reward_decomposed 解析核对（C 表）：
      超限项 = 6·min(pn−1, 2)，pn=0.5/1.0/1.5/3.0/5.0 → 0/0/3/12/12，pn≤1 恒为 0。
    - 面板 A 改造前曲线 = 原车钩力整形项 −0.2·peak_norm（C 表增量口径核对：
      pn 1.0→1.5 惩罚仅增 0.1），线性、无超限跳变。
    - 面板 B = D on/off 隔离对照（同一确定性策略、12000 步窗口）：
      ab_safety_vetoed 0（off，危险源直通动力学）→ 35（on，env 侧真丢弃非空新增源）。
    口径纪律：全部为前期两万吨方案（ADR-039 之前）数字，图题带"前期方案"标注。
    """
    _setup_cjk()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.6, 4.7),
                                   gridspec_kw={"width_ratios": [1.5, 1.0]})

    # 面板 A：越线惩罚曲线（改造前 / 改造后）
    pn = np.linspace(0.0, 5.2, 261)
    before = 0.2 * pn
    after = np.where(pn <= 1.0, 0.0, 6.0 * np.minimum(pn - 1.0, 2.0))
    ax1.plot(pn, before, color="#8c9aa6", lw=2.6, label="改造前")
    ax1.plot(pn, after, color="#2a9d8f", lw=2.8, label="改造后")
    ax1.axvline(1.0, color="#d62728", ls="--", lw=1.8, label="1000 kN 限值")
    ax1.legend(loc="upper left", fontsize=12, frameon=False)
    ax1.set_xlabel("车钩力峰值 / 限值", fontsize=13)
    ax1.set_ylabel("单步惩罚量级（奖励量纲）", fontsize=13)
    ax1.set_xlim(0, 5.2)
    ax1.set_ylim(0, 13.2)
    ax1.tick_params(labelsize=12.5)
    ax1.grid(axis="y", alpha=0.3, lw=0.6)
    ax1.set_axisbelow(True)

    # 面板 B：危险空气制动源拦截对照（同一策略 12000 步窗口，口径见备注）
    labels = ["改造前", "改造后"]
    vals = [0, 35]
    ax2.bar(labels, vals, width=0.44, color=["#8c9aa6", "#2a9d8f"],
            edgecolor="white")
    ax2.text(0, 1.0, "0", ha="center", va="bottom", fontsize=14,
             fontweight="bold", color="#1a1a1a")
    ax2.text(1, 36.2, "35", ha="center", va="bottom", fontsize=14,
             fontweight="bold", color="#1a1a1a")
    ax2.set_ylabel("危险空气制动源拦截（次）", fontsize=13)
    ax2.set_ylim(0, 42)
    ax2.tick_params(labelsize=12.5)
    ax2.grid(axis="y", alpha=0.3, lw=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle("前期方案：越线重罚与安全拦截改造前后对照", fontsize=15.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig_signal_safety.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- 框图 ----
def _setup_cjk() -> None:
    plt.rcParams["font.sans-serif"] = CJK
    plt.rcParams["axes.unicode_minus"] = False


def _box(ax, x, y, w, h, text, fc="#eef4fb", ec="#2b5d8a", fs=13, lw=1.5,
         dashed=False, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=fc, ec=ec, lw=lw,
                                linestyle="--" if dashed else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color="#1a1a1a", linespacing=1.55,
            fontweight="bold" if bold else "normal")


def _arrow(ax, p1, p2, label=None, fs=11.5, dashed=False, color="#444444",
           lw=1.6, rad=0.0, lab_xy=None, lab_color="#333333"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=17,
                                 lw=lw, color=color,
                                 linestyle="--" if dashed else "-",
                                 connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=3, shrinkB=3))
    if label:
        mx = (p1[0] + p2[0]) / 2 if lab_xy is None else lab_xy[0]
        my = (p1[1] + p2[1]) / 2 if lab_xy is None else lab_xy[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs,
                color=lab_color, linespacing=1.4)


def fig_timeline() -> None:
    """页 10：横向里程碑时间轴（对照立项计划，9 节点含未来 4 节点）。

    2026-10-20 弃用（负责人拍板）：页 10 改为成果表 + 下一步计划进度条
    （fig_gantt_plan），本图不再被大纲引用，保留仅作历史备查。
    """
    _setup_cjk()
    nodes = [
        ("2026.06", "文献调研与\n技术方案确立", "done"),
        ("2026.07", "MAPPO 算法\n框架验证", "done"),
        ("2026.07-09", "动力学仿真环境\n搭建与校验", "done"),
        ("2026.08-09", "多智能体\n问题建模", "done"),
        ("2026.09-至今", "规则控制标定与\n训练准备", "doing"),
        ("2026.11", "综合测试与\n对比评估", "todo"),
        ("2026.12", "论文初稿", "todo"),
        ("2027.01-02", "策略优化与\n补充实验", "todo"),
        ("2027.03-04", "项目总结与\n成果整理", "todo"),
    ]
    fig, ax = plt.subplots(figsize=(13.8, 3.6))
    ax.plot([-0.35, 8.35], [0, 0], color="#9aa5b1", lw=2.5, zorder=1)
    for i, (date, name, st) in enumerate(nodes):
        if st == "done":
            face, edge = "#2b5d8a", "#2b5d8a"
        elif st == "doing":
            face, edge = "#ffd8a8", "#e07b39"
        else:
            face, edge = "white", "#9aa5b1"
        ax.plot([i], [0], "o", ms=15, mfc=face, mec=edge, mew=2.0, zorder=3)
        ax.text(i, 0.34, name, ha="center", va="bottom", fontsize=12,
                linespacing=1.5)
        ax.text(i, -0.30, date, ha="center", va="top", fontsize=11,
                color="#555555")
    handles = [
        Line2D([], [], marker="o", ls="", mfc="#2b5d8a", mec="#2b5d8a", ms=11,
               label="已完成"),
        Line2D([], [], marker="o", ls="", mfc="#ffd8a8", mec="#e07b39", ms=11,
               label="进行中"),
        Line2D([], [], marker="o", ls="", mfc="white", mec="#9aa5b1", ms=11,
               label="待做"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=11.5, ncol=3,
              frameon=False, bbox_to_anchor=(1.0, -0.16))
    ax.set_xlim(-0.55, 8.55)
    ax.set_ylim(-1.15, 1.35)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "fig_timeline.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig_gantt_plan() -> None:
    """页 10：下一步计划进度条（甘特式横条，2026.09–2027.06，中文标注）。

    行 1 = 进行中（橙），行 2–6 = 未来计划（蓝）；红竖虚线 = 当前（2026.10 下旬）。
    论文投稿节点口径（拍板 #8）：只写"论文投稿与检索"，不写死会议名
    （口头备答：EI 检索国际会议，2027 年 6 月底前完成检索）。
    """
    _setup_cjk()
    # x 轴：0 = 2026.09 月初，每格 1 个月，10 = 2027.07 月初（覆盖至 2027.06 底）
    rows = [
        ("规则控制标定与训练准备", 0.0, 2.0, "#e07b39"),
        ("综合测试与对比评估", 2.0, 3.0, "#2b5d8a"),
        ("论文初稿", 3.0, 4.0, "#2b5d8a"),
        ("策略优化与补充实验", 4.0, 6.0, "#2b5d8a"),
        ("项目总结与成果整理", 6.0, 8.0, "#2b5d8a"),
        ("论文投稿与检索", 8.0, 10.0, "#2b5d8a"),
    ]
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    for i, (name, start, end, color) in enumerate(rows):
        ax.barh(i, end - start, left=start, height=0.52, color=color,
                edgecolor="white")
    ax.axvline(1.65, color="#d62728", ls="--", lw=1.8, zorder=3)
    ax.text(1.50, -0.72, "当前", color="#d62728", fontsize=12.5, ha="right",
            va="center", fontweight="bold")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=12.5)
    ax.set_ylim(5.65, -1.05)  # 行 0 在顶部；顶部留"当前"标注空间
    xlabels = ["2026.09", "2026.10", "2026.11", "2026.12", "2027.01",
               "2027.02", "2027.03", "2027.04", "2027.05", "2027.06", ""]
    ax.set_xticks(range(11))
    ax.set_xticklabels(xlabels, fontsize=11.5)
    ax.set_xlim(-0.05, 10.05)
    ax.grid(axis="x", alpha=0.35, lw=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    handles = [Patch(fc="#e07b39", label="进行中"),
               Patch(fc="#2b5d8a", label="计划")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.09),
              ncol=2, frameon=False, fontsize=12)
    ax.set_title("下一步计划进度安排", fontsize=15)
    fig.tight_layout()
    fig.savefig(OUT / "fig_gantt_plan.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig_env_modules() -> None:
    """页 5：列车纵向动力学仿真环境模块框图。"""
    _setup_cjk()
    fig, ax = plt.subplots(figsize=(11.0, 7.2))
    ax.set_xlim(-2.9, 12.3)
    ax.set_ylim(0.4, 10.6)
    ax.axis("off")

    # 输入层
    _box(ax, 2.5, 8.8, 5.0, 1.0, "控制指令输入（逐车）\n电制动深度 · 空气制动档位",
         fs=13, bold=True)
    # 动力学核心
    _box(ax, 1.2, 3.6, 7.6, 4.6, "", fc="#f7fafd")
    ax.text(5.0, 7.75, "列车纵向动力学核心（半隐式 Euler 积分）", ha="center",
            fontsize=13.5, fontweight="bold")
    inner = [
        ("牵引力", 1.5, 6.05), ("电制动", 3.9, 6.05),
        ("空气制动\n充/缓解波传播", 6.3, 5.85),
        ("Davis\n基本阻力", 1.5, 4.15), ("坡道附加阻力", 3.9, 4.35),
        ("车钩非线性\n缓冲器迟滞", 6.3, 4.15),
    ]
    for text, x, y in inner:
        _box(ax, x, y, 2.2, 1.35, text, fc="white", fs=11.5, lw=1.2)
    # 输出层
    _box(ax, 2.5, 1.9, 5.0, 1.0, "输出：逐车位置 / 速度\n+ 车钩断面力",
         fs=13, bold=True)
    # 主流程箭头
    _arrow(ax, (5.0, 8.8), (5.0, 8.25))
    _arrow(ax, (5.0, 3.6), (5.0, 2.95))
    # ATP 侧挂
    _box(ax, 9.6, 6.6, 2.4, 1.1, "列车自动防护\n（ATP）", fc="#fdeeee", ec="#c0504d",
         fs=12.5)
    _arrow(ax, (9.6, 7.15), (8.85, 7.15), label="限速保护", fs=11,
           lab_xy=(9.2, 7.9))
    # Gym 接口
    _box(ax, -2.7, 1.6, 2.6, 1.5, "Gym 标准接口\n（强化学习接入）",
         fc="#eef7f0", ec="#2a7a4b", fs=12)
    _arrow(ax, (-0.1, 2.75), (2.5, 2.4))
    _arrow(ax, (2.5, 2.05), (-0.1, 2.35))
    fig.tight_layout()
    fig.savefig(OUT / "fig_env_modules.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig_marl_arch() -> None:
    """页 6：MARL 架构（3 个机车智能体 · CTDE）。"""
    _setup_cjk()
    fig, ax = plt.subplots(figsize=(11.5, 7.4))
    ax.set_xlim(0, 12.6)
    ax.set_ylim(0, 10.2)
    ax.axis("off")

    # 三个列车智能体（纵排）
    trains = [("列车 1\n1 台机车智能体 + 108 节货车", 7.0),
              ("列车 2\n1 台机车智能体 + 108 节货车", 4.4),
              ("列车 3\n1 台机车智能体 + 108 节货车", 1.8)]
    for text, y in trains:
        _box(ax, 4.0, y, 4.1, 1.5, text, fs=12.5, bold=False)
    # 集中训练器
    _box(ax, 9.4, 4.2, 2.9, 2.0, "集中训练器\nMAPPO", fs=13.5, bold=True)
    # 观测 / 动作（列车 ↔ 训练器，实线细箭头）
    obs = [((8.1, 8.0), (9.4, 5.9)), ((8.1, 5.15), (9.4, 5.25)),
           ((8.1, 2.3), (9.4, 4.5))]
    act = [((9.4, 4.9), (8.1, 7.6)), ((9.4, 4.6), (8.1, 4.75)),
           ((9.4, 4.3), (8.1, 2.6))]
    for p1, p2 in obs:
        _arrow(ax, p1, p2, color="#2b5d8a", lw=1.3)
    for p1, p2 in act:
        _arrow(ax, p1, p2, color="#2a7a4b", lw=1.3)
    ax.text(8.75, 9.05, "观测\n速度误差·间距误差\n车钩力·位置", fontsize=11,
            ha="center", color="#2b5d8a", linespacing=1.4)
    ax.text(8.75, 1.0, "动作\n电制动 · 空气制动解耦", fontsize=11, ha="center",
            color="#2a7a4b", linespacing=1.4)
    # 虚线：轨迹汇总 / 共享策略更新
    _arrow(ax, (5.5, 8.5), (10.4, 6.25), label="轨迹汇总", fs=11.5, dashed=True,
           rad=-0.25, lab_xy=(11.1, 8.3))
    _arrow(ax, (10.4, 4.15), (6.5, 1.78), label="共享策略更新", fs=11.5,
           dashed=True, rad=-0.2, lab_xy=(9.9, 2.2))
    # 底部环境
    _box(ax, 2.6, 0.35, 4.6, 1.0, "列车纵向动力学环境", fs=13, bold=True)
    # 环境反馈（扇形曲线到三个列车左缘）
    _arrow(ax, (4.0, 1.35), (4.0, 1.8), color="#c0504d", lw=1.4)
    _arrow(ax, (3.2, 1.35), (4.0, 4.9), color="#c0504d", lw=1.4, rad=0.32)
    _arrow(ax, (2.7, 1.35), (4.0, 7.5), color="#c0504d", lw=1.4, rad=0.36)
    ax.text(1.25, 4.6, "车钩力 · 间距 · 速度反馈", fontsize=11.5, color="#c0504d",
            rotation=90, ha="center", va="center")
    fig.tight_layout()
    fig.savefig(OUT / "fig_marl_arch.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- 入口 ----
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part in ("data", "all"):
        fig_profile_49km()
        fig_coupler_credit()
        fig_signal_safety()
        print(f"[data] -> {OUT}")
    if part in ("blocks", "all"):
        fig_gantt_plan()
        fig_env_modules()
        fig_marl_arch()
        print(f"[blocks] -> {OUT}")


if __name__ == "__main__":
    main()
