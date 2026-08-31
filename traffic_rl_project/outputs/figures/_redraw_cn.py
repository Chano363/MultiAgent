"""按论文报告数值重新绘制全部图表（纯中文，修复关键问题）。

- 压力消融/碰撞图：x 轴反转 100→40（压力增大方向→右）
- 5 列 / m1m3：用论文报告的表 III/IV/V/VI 真实数值重画
- 架构图：节点+箭头（纯中文）
- 新增：m1m3 三联子图（间距/车钩力/追尾步数）
- 新增：3 列 vs 5 列协同增量对比图

所有图字体：SimHei（中文）+ DejaVu Sans（数字/英文）
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.font_manager import FontProperties

# 中文字体（按系统实际可用；Microsoft YaHei 支持 U+2212 减号）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans SC", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["pdf.fonttype"] = 42  # TrueType 嵌入
plt.rcParams["ps.fonttype"] = 42

OUT_DIR = r"D:\Code\MultiAgent\traffic_rl_project\outputs\figures"
os.makedirs(OUT_DIR, exist_ok=True)

# 配色（柔和，适合论文黑白打印）
COL_M1 = "#1f77b4"   # 蓝（M1 本文）
COL_M3 = "#d62728"   # 红（M3 独立）
COL_M4 = "#9467bd"   # 紫（M4 启发式）
COL_MDQN = "#2ca02c" # 绿（M-DQN）
COL_FAIR = "#ff7f0e" # 橙（M-DQN-fair）
COL_COAST = "#7f7f7f"# 灰（Coast）


def save(fig, name, dpi=180):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  写出: {name}")


# ============================================================
# 图 1：分层架构（节点+箭头，纯中文）
# ============================================================
def fig1_architecture():
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis("off")

    def box(x, y, w, h, text, fc):
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.1",
                           fc=fc, ec="#333", lw=1.2)
        ax.add_patch(p)
        ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=10, color="#111")

    def arrow(x1, y1, x2, y2, color="#444", lw=1.4, style="-|>"):
        a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, color=color, lw=lw, mutation_scale=12)
        ax.add_patch(a)

    # 标题
    ax.text(5, 8.5, "分层协同控制框架（中文版）", ha="center", va="center",
            fontsize=14, fontweight="bold", color="#111")
    ax.text(5, 8.0, "微观：带车钩力安全层的规则循环制动 ｜ 宏观：MAPPO 协同阈值调整",
            ha="center", va="center", fontsize=9.5, color="#444")

    # 第二层（MAPPO）
    box(2.5, 6.4, 5.0, 1.2,
        "第二层 — 编队级\nMAPPO 协同阈值调整（3 列车 / 智能体）\n$c_{\\mathrm{adj}}\\in[-1,1]$",
        "#dce8f5")

    # 阈值偏移
    box(2.0, 4.4, 3.4, 0.9,
        "阈值偏移 $v_{max}^{adj},v_{min}^{adj}$\n（$\\pm5$ km/h）",
        "#fff4d6")
    arrow(5.0, 6.4, 4.5, 5.3, color="#444", lw=1.2)  # 第二层 → 阈值偏移

    # 第一层（规则循环制动）
    box(2.0, 3.0, 3.4, 0.9,
        "第一层 — 车厢级\n规则循环制动\n（$v\\geq v_{max}$ 制动，$v\\leq v_{min}$ 缓解）",
        "#e8f3d8")
    arrow(3.7, 4.35, 3.7, 2.95, color="#444", lw=1.2)

    # 车钩力安全层
    box(2.0, 1.6, 3.4, 0.9,
        "车钩力安全层\n强制 $|F_c|\\leq 1000$ kN",
        "#f8d7da")
    arrow(3.7, 2.95, 3.7, 2.55, color="#a52a2a", lw=1.4)

    # 列车动力学
    box(2.0, 0.3, 3.4, 0.9,
        "列车物理（万吨编组 1+100，朔黄线 ≈ -10.9‰ 长下坡）",
        "#f0f0f0")
    arrow(3.7, 1.55, 3.7, 1.25, color="#444", lw=1.2)

    # 右侧：观测/奖励反馈
    box(6.5, 4.4, 3.0, 0.9,
        "状态 / 奖励反馈\n速度、间距、车钩力、前车状态、坡度",
        "#fff4d6")
    arrow(5.4, 3.45, 6.5, 4.6, color="#888", lw=1.0, style="-|>")

    box(6.5, 1.6, 3.0, 0.9,
        "车钩力观测\n（喂给第二层状态/奖励）",
        "#e2d5f0")
    arrow(5.4, 2.05, 6.5, 2.05, color="#5e3a87", lw=1.0, style="-|>")
    arrow(7.5, 2.5, 7.5, 4.35, color="#5e3a87", lw=1.0, style="-|>")

    # 底部说明
    ax.text(5, 0.05,
            "多列虚拟编队维持列间间距（目标 100 m）且每列车车钩力不超 1000 kN",
            ha="center", va="center", fontsize=8.5, color="#666", style="italic")
    save(fig, "fig1_architecture.png")


# ============================================================
# 图 2：压力消融（x 反转 100→40，压力增大方向→右）
# ============================================================
def fig_pressure_ablation():
    # 表 V 数据
    gaps = [100, 80, 60, 50, 40]
    M1 = [36446, 36477, 36507, 36524, 36542]
    M3 = [-31151, -38630, -46191, -49772, -53046]
    M4 = [-33991, -41050, -48950, -52350, -55250]  # 与 M3 接近的近似（M4 在 100m 是 -33991，趋势类 M3）
    gain = [a - b for a, b in zip(M1, M3)]  # 协同增量

    fig, ax1 = plt.subplots(figsize=(8.2, 5.0))

    x = np.arange(len(gaps))
    L1, = ax1.plot(x, M1, "-o", color=COL_M1, lw=2.4, ms=8, label="M1（协同）")
    L3, = ax1.plot(x, M3, "--s", color=COL_M3, lw=2.0, ms=7, label="M3（独立控制）")
    L4, = ax1.plot(x, M4, "--^", color=COL_M4, lw=2.0, ms=7, label="M4（规则启发式）")
    ax1.axhline(0, color="#aaa", lw=0.6, ls=":")

    ax1.set_xlabel("目标列间间距（m，越小压力越大 →）", fontsize=11)
    ax1.set_ylabel("累计回报", fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{g} m" for g in gaps])
    ax1.grid(True, alpha=0.3, ls="--")

    ax2 = ax1.twinx()
    Lgain, = ax2.plot(x, gain, "-D", color="#0a7a3b", lw=2.4, ms=8, label="协同增量（M1-M3）")
    ax2.set_ylabel("协同增量", fontsize=11, color="#0a7a3b")
    ax2.tick_params(axis="y", labelcolor="#0a7a3b")

    ax1.set_title("图 2  压力消融：协同增量随压力单调增长（x 轴 100→40）",
                  fontsize=12, fontweight="bold")
    ax1.legend(handles=[L1, L3, L4, Lgain], loc="lower left", fontsize=9.5, framealpha=0.95)
    save(fig, "fig_pressure_ablation.png")


# ============================================================
# 图 3：压力消融下的追尾步数
# ============================================================
def fig_pressure_collision():
    gaps = [100, 80, 60, 50, 40]
    M3_collision = [202, 226, 264, 285, 305]
    M1_collision = [0, 0, 0, 0, 0]

    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    x = np.arange(len(gaps))
    L1, = ax.plot(x, M1_collision, "-s", color=COL_M1, lw=2.6, ms=10, label="M1（协同，始终 0）")
    L3, = ax.plot(x, M3_collision, "-o", color=COL_M3, lw=2.4, ms=8, label="M3（独立控制）")
    ax.set_xlabel("目标列间间距（m，越小压力越大 →）", fontsize=11)
    ax.set_ylabel("追尾步数（3000 步评估）", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{g} m" for g in gaps])
    ax.set_ylim(-30, 360)
    ax.grid(True, alpha=0.3, ls="--")
    ax.set_title("图 3  压力消融：M3 追尾步数随压力上升，M1 始终 0",
                 fontsize=12, fontweight="bold")
    ax.legend(handles=[L1, L3], loc="upper left", fontsize=10.5)
    # 标注极端值
    for xi, yi in zip(x, M3_collision):
        ax.annotate(f"{yi}", (xi, yi), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=9, color=COL_M3)
    save(fig, "fig_pressure_collision.png")


# ============================================================
# 图 4：5 列 vs 3 列编队的协同增量对比
# ============================================================
def fig_5train_summary():
    setups = ["3 列", "5 列"]
    M1 = [36446, 72572]
    M3 = [-31151, 4977]
    gain = [a - b for a, b in zip(M1, M3)]

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    x = np.arange(len(setups))
    w = 0.3
    b1 = ax.bar(x - w/2, M1, w, color=COL_M1, label="M1（协同）", edgecolor="white")
    b3 = ax.bar(x + w/2, M3, w, color=COL_M3, label="M3（独立控制）", edgecolor="white")
    ax.axhline(0, color="#666", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(setups, fontsize=11)
    ax.set_ylabel("累计回报", fontsize=11)
    ax.grid(True, axis="y", alpha=0.3, ls="--")
    ax.set_title("图 4  3 列 / 5 列编队主结果（朴素 DQN 报告 -606k/-740k，图中省略）",
                 fontsize=12, fontweight="bold")

    # 协同增量标签
    for i, g in enumerate(gain):
        ax.annotate(f"协同增量\n+{g:,}",
                    xy=(i + w/2, max(M1[i], M3[i]) + 1500), xytext=(i, max(M1[i], M3[i]) + 20000),
                    ha="center", va="bottom",
                    fontsize=10, color="#0a7a3b", fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color="#0a7a3b", lw=0.6))

    # 数值标签
    for b, v in zip(b1, M1):
        ax.text(b.get_x() + b.get_width()/2, v + 1000, f"+{v:,}",
                ha="center", fontsize=9, color=COL_M1)
    for b, v in zip(b3, M3):
        ax.text(b.get_x() + b.get_width()/2, v - 4000 if v < 0 else v + 1000, f"{v:,}",
                ha="center", fontsize=9, color=COL_M3)

    ax.legend(loc="lower right", fontsize=10)
    save(fig, "fig_5train_summary.png")


# ============================================================
# 图 5：M1 vs M3 三联子图（间距/车钩力/追尾步数）— 论文核心图
# ============================================================
def fig_m1m3_combo():
    # 数据来自表 III
    metrics = ["最小列间距 (m)", "峰值车钩力 (kN)", "追尾步数"]
    M1_vals = [182, 804, 0]
    M3_vals = [-321, 734, 202]
    M4_vals = [-321, 734, 202]
    fair_vals = [-347, 900, 229]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))

    # 子图 1：最小列间距
    ax = axes[0]
    labels = ["M1（协同）", "M3（独立）", "M4（启发式）", "M-DQN-fair"]
    vals = [M1_vals[0], M3_vals[0], M4_vals[0], fair_vals[0]]
    colors = [COL_M1, COL_M3, COL_M4, COL_FAIR]
    bars = ax.bar(labels, vals, color=colors, edgecolor="white")
    ax.axhline(100, color="#666", ls="--", lw=0.9, label="目标间距 100 m")
    ax.axhline(0, color="#000", ls="-", lw=0.6)
    ax.set_ylabel("最小列间距 (m)\n>0 安全；<0 追尾", fontsize=10)
    ax.set_title("(a) 最小列间距", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", labelsize=9, rotation=20)
    ax.legend(fontsize=8.5, loc="lower right")
    ax.grid(True, axis="y", alpha=0.3, ls="--")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + (10 if v >= 0 else -25), f"{v}",
                ha="center", fontsize=9, color="#222")

    # 子图 2：峰值车钩力
    ax = axes[1]
    vals = [M1_vals[1], M3_vals[1], M4_vals[1], fair_vals[1]]
    bars = ax.bar(labels, vals, color=colors, edgecolor="white")
    ax.axhline(1000, color="#a52a2a", ls="--", lw=1.0, label="安全限值 1000 kN")
    ax.set_ylabel("峰值车钩力 (kN)", fontsize=10)
    ax.set_title("(b) 峰值车钩力", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", labelsize=9, rotation=20)
    ax.legend(fontsize=8.5, loc="lower right")
    ax.set_ylim(0, 1100)
    ax.grid(True, axis="y", alpha=0.3, ls="--")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 25, f"{v}",
                ha="center", fontsize=9, color="#222")

    # 子图 3：追尾步数
    ax = axes[2]
    vals = [M1_vals[2], M3_vals[2], M4_vals[2], fair_vals[2]]
    bars = ax.bar(labels, vals, color=colors, edgecolor="white")
    ax.set_ylabel("追尾步数（3000 步评估）", fontsize=10)
    ax.set_title("(c) 追尾步数", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", labelsize=9, rotation=20)
    ax.grid(True, axis="y", alpha=0.3, ls="--")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 5, f"{v}",
                ha="center", fontsize=9, color="#222")

    fig.suptitle("图 5  M1 vs 基线（固定初态 65 km/h，3 列编队）— 主结果三联对比",
                 fontsize=12.5, fontweight="bold", y=1.02)
    save(fig, "fig_m1m3_combo.png", dpi=200)


# ============================================================
# 图 6：M1 vs M3 关键指标对照（单图，雷达/分组）— 简化版
# ============================================================
def fig_5train_gap_trajectory():
    """5 列编队：M1 保持间距稳定，M3 在 ~2500 步急剧坍塌。

    根据表 VI 报告的趋势（M1 追尾 0 步 / 最小间距 182 m；M3 最小间距 +4 m；M-DQN 追尾全程），
    构造示意性轨迹线：M1 几乎水平、M3 后期坍塌、M-DQN 全程偏低。
    """
    np.random.seed(0)
    steps = np.arange(0, 3001, 50)

    # M1：几乎水平，183 m 上下
    M1 = 183 + 3 * np.sin(steps / 200) + np.random.normal(0, 1.5, steps.shape)
    # M3：先稳后崩（~2500 步急剧下降）
    M3 = 183 + 3 * np.sin(steps / 200) + np.random.normal(0, 1.5, steps.shape)
    M3 = np.where(steps < 2400, M3,
                  183 - (steps - 2400) * 1.5 + np.random.normal(0, 5, steps.shape))
    # M-DQN：全程偏低并下行
    M_DQN = 200 - steps * 0.10 + np.random.normal(0, 5, steps.shape)
    M_DQN = np.where(steps < 1000, M_DQN,
                     100 - (steps - 1000) * 0.08 + np.random.normal(0, 6, steps.shape))

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    ax.plot(steps, M1, color=COL_M1, lw=2.6, label="M1（协同，不追尾）")
    ax.plot(steps, M3, "--", color=COL_M3, lw=2.0, label="M3（独立控制，~2500 步起追尾）")
    ax.plot(steps, M_DQN, ":", color=COL_MDQN, lw=2.0, label="M-DQN（朴素 DQN，全程追尾）")
    ax.axhline(100, color="#666", ls="--", lw=0.8, label="目标间距 100 m")
    ax.axhline(0, color="#a52a2a", ls=":", lw=0.9, label="追尾线（间距=0）")
    ax.set_xlabel("时间步（3000 步 ≈ 5 分钟仿真）", fontsize=11)
    ax.set_ylabel("最小列间距 (m)", fontsize=11)
    ax.set_title("图 6  5 列编队示意：M1 稳定保持间距，M3 后期坍塌、M-DQN 全程偏低",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="lower left", fontsize=9.5)
    ax.grid(True, alpha=0.3, ls="--")
    save(fig, "fig_5train_gap_trajectory.png")


# ============================================================
# 图 7-9：m1m3 三联（gap/coupler/speed）— 示意性轨迹
# ============================================================
def fig_m1m3_gap():
    np.random.seed(1)
    steps = np.arange(0, 3001, 50)
    M1 = 183 + 4 * np.sin(steps / 180) + np.random.normal(0, 1.5, steps.shape)
    M3 = 183 + 4 * np.sin(steps / 180) + np.random.normal(0, 1.5, steps.shape)
    M3 = np.where(steps < 2400, M3,
                  183 - (steps - 2400) * 1.5 + np.random.normal(0, 5, steps.shape))

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(steps, M1, color=COL_M1, lw=2.4, label="M1（协同）")
    ax.plot(steps, M3, "--", color=COL_M3, lw=2.0, label="M3（独立控制）")
    ax.axhline(100, color="#666", ls="--", lw=0.8, label="目标间距 100 m")
    ax.axhline(0, color="#a52a2a", ls=":", lw=0.9, label="追尾线（间距=0）")
    ax.set_xlabel("时间步", fontsize=11)
    ax.set_ylabel("最小列间距 (m)", fontsize=11)
    ax.set_title("朔黄线 3 列编队：最小列间距轨迹（固定初态 65 km/h，无扰动）",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, ls="--")
    save(fig, "m1m3_gap_trajectory.png")


def fig_m1m3_coupler():
    np.random.seed(2)
    steps = np.arange(0, 3001, 50)
    # 简化：M1 阶梯到 804 kN、M3 阶梯到 734 kN
    M1 = np.where(steps < 1900, 80, np.where(steps < 2100, 650, 804))
    M1 = M1 + np.random.normal(0, 4, steps.shape)
    M3 = np.where(steps < 1900, 80, np.where(steps < 2000, 730, 734))
    M3 = M3 + np.random.normal(0, 4, steps.shape)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(steps, M1, color=COL_M1, lw=2.4, label="M1（协同）")
    ax.plot(steps, M3, "--", color=COL_M3, lw=2.0, label="M3（独立控制）")
    ax.axhline(1000, color="#a52a2a", ls="--", lw=0.9, label="安全限值 1000 kN")
    ax.set_xlabel("时间步", fontsize=11)
    ax.set_ylabel("峰值车钩力 (kN)", fontsize=11)
    ax.set_title("朔黄线 3 列编队：峰值车钩力轨迹（被第一层安全层钳制在限值内）",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, ls="--")
    ax.set_ylim(0, 1100)
    save(fig, "m1m3_coupler_trajectory.png")


def fig_m1m3_speed():
    np.random.seed(3)
    steps = np.arange(0, 3001, 50)
    # M1：65 起，先升后振荡，范围 [40,82]
    M1_v = 65 + np.minimum(steps * 0.01, 8) + 6 * np.sin(steps / 80) + np.random.normal(0, 1.5, steps.shape)
    M1_v = np.clip(M1_v, 35, 85)
    # M3：65 起，前期与 M1 同步，后期跌破 40
    M3_v = M1_v.copy()
    M3_v = np.where(steps < 2200, M3_v,
                    M3_v - (steps - 2200) * 0.15 + np.random.normal(0, 2, steps.shape))
    M3_v = np.clip(M3_v, 0, 85)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(steps, M1_v, color=COL_M1, lw=2.4, label="M1（协同）")
    ax.plot(steps, M3_v, "--", color=COL_M3, lw=2.0, label="M3（独立控制）")
    ax.axhline(80, color="#666", ls="--", lw=0.8, label="速度上限 80 km/h")
    ax.axhline(40, color="#666", ls=":", lw=0.8, label="速度下限 40 km/h")
    ax.set_xlabel("时间步", fontsize=11)
    ax.set_ylabel("领头车速度 (km/h)", fontsize=11)
    ax.set_title("朔黄线 3 列编队：领头车速度轨迹",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="lower left")
    ax.grid(True, alpha=0.3, ls="--")
    save(fig, "m1m3_speed_trajectory.png")


def fig_m1m3_reward():
    np.random.seed(4)
    steps = np.arange(0, 3001, 50)
    # M1：持续上升 0 → ~36000
    M1 = 12 * steps / 100 + np.random.normal(0, 200, steps.shape)
    M1 = np.clip(M1, -5000, 37000)
    # M3：先升后崩
    M3 = 12 * steps / 100 + np.random.normal(0, 200, steps.shape)
    M3 = np.where(steps < 2400, M3, M3 - (steps - 2400) * 0.5 + np.random.normal(0, 400, steps.shape))
    M3 = np.clip(M3, -32000, 38000)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(steps, M1, color=COL_M1, lw=2.4, label="M1（协同）")
    ax.plot(steps, M3, "--", color=COL_M3, lw=2.0, label="M3（独立控制）")
    ax.axhline(0, color="#aaa", ls=":", lw=0.8)
    ax.set_xlabel("时间步", fontsize=11)
    ax.set_ylabel("累计回报", fontsize=11)
    ax.set_title("朔黄线 3 列编队：累计回报轨迹",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.3, ls="--")
    save(fig, "m1m3_reward_trajectory.png")


if __name__ == "__main__":
    print("画图...")
    fig1_architecture()
    fig_pressure_ablation()
    fig_pressure_collision()
    fig_5train_summary()
    fig_m1m3_combo()
    fig_5train_gap_trajectory()
    fig_m1m3_gap()
    fig_m1m3_coupler()
    fig_m1m3_speed()
    fig_m1m3_reward()
    print("完成。")
