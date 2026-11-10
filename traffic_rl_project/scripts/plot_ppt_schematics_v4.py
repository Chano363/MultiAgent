# -*- coding: utf-8 -*-
"""中期答辩 PPT 示意图参考底稿（v4，学姐 PPT 风格复刻）。

风格 tokens（对照学姐开题 PPT slide13/15/23）：
  - 白底；框体 = 白填充 + 深蓝(navy #2F4A7A)描边、黑粗体文字、红色关键词强调；
  - 分组框 = 蓝色虚线圆角框；连接 = 白填充蓝描边块箭头；
  - 结论框 = 红描边圆角框；时间线 = 蓝色渐变蛇形粗带 + 上下交替日期。

产出 7 张 PNG 到 ppt_talk/midterm_20261018/images/示意底稿/：
  fig_v4_framework.png   四层总体框架（P8）
  fig_v4_content1.png    内容一架构 ①②③（P9 上半）
  fig_v4_content2.png    内容二链式执行层（P10 上半）
  fig_v4_content3.png    五层链路图（P11 上半）
  fig_v4_bars.png        越限对照柱状（P11 下半）
  fig_v4_timeline.png    蛇形时间线（P14）
  fig_v4_gui.png         平台框图（P13）
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

NAVY = "#2F4A7A"      # 主深蓝（描边/标题/时间线深段）
NAVY_D = "#1F3358"    # 更深蓝（时间线末段）
RED = "#C00000"       # 红色强调
LBLUE = "#DCE6F2"     # 浅蓝面板填充
LORANGE = "#FDF2E2"   # 浅橙面板填充
LGRAY = "#F4F6FA"     # 浅灰蓝面板填充
MB = "#8FAADC"        # 中蓝（时间线中段）
LL = "#C9D4E8"        # 淡蓝（时间线起段）

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "ppt_talk", "midterm_20261018", "images", "示意底稿")


def new_ax(w=10.0, h=5.6):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.canvas.draw()
    return fig, ax


def rich(ax, x, y, segs, fs=11, va="center", align="left"):
    """一行多色文字：segs = [(text, color)]，全部加粗。align: left/center。"""
    fig = ax.figure
    rend = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    objs, cur = [], x
    for text, color in segs:
        t = ax.text(cur, y, text, fontsize=fs, color=color, va=va, ha="left",
                    fontweight="bold")
        ext = t.get_window_extent(rend)
        dx = inv.transform((ext.width, 0))[0] - inv.transform((0, 0))[0]
        objs.append(t)
        cur += dx
    if align == "center" and objs:
        total = cur - x
        for t in objs:
            p = t.get_position()
            t.set_position((p[0] - total / 2, p[1]))
    return cur


def box(ax, x, y, w, h, ec=NAVY, fc="white", lw=2.0, ls="-", rounding=0.08):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=%.3f" % rounding,
                 facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls))


def dashframe(ax, x, y, w, h, label=None):
    """蓝色虚线分组框 + 左上粗体标签。"""
    box(ax, x, y, w, h, ec=NAVY, fc="none", lw=1.6, ls=(0, (6, 4)), rounding=0.05)
    if label:
        ax.text(x + 0.18, y + h - 0.26, label, fontsize=12, color="black",
                fontweight="bold", va="center")


def block_arrow_down(ax, cx, y_top, y_bot, w=0.52, head=0.26, ec=NAVY, fc="white"):
    yb = y_bot + head
    pts = [(cx - w / 2, y_top), (cx + w / 2, y_top), (cx + w / 2, yb),
           (cx + w * 0.82, yb), (cx, y_bot), (cx - w * 0.82, yb), (cx - w / 2, yb)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, lw=1.5))


def block_arrow_right(ax, xl, xr, cy, w=0.5, head=0.28, ec=NAVY, fc="white"):
    xb = xr - head
    pts = [(xl, cy - w / 2), (xb, cy - w / 2), (xb, cy - w * 0.82),
           (xr, cy), (xb, cy + w * 0.82), (xb, cy + w / 2), (xl, cy + w / 2)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, lw=1.5))


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved:", path)


# ---------------------------------------------------------------- P8 四层框架
def fig_framework():
    fig, ax = new_ax(10.0, 5.6)
    # 左缘纵标签（四行，y = 行中心）
    rail = [(5.06, "研究目标"), (3.83, "关键问题"), (2.16, "研究进展"), (0.54, "验证评价")]
    for yc, lab in rail:
        box(ax, 0.25, yc - 0.42, 1.35, 0.84, fc=NAVY, ec=NAVY, rounding=0.06)
        ax.text(0.925, yc, lab, fontsize=12.5, color="white",
                fontweight="bold", ha="center", va="center")
    x0, W = 1.95, 7.8
    bw, gap = 2.5, 0.15
    bx = [x0 + i * (bw + gap) for i in range(3)]
    bcx = [v + bw / 2 for v in bx]

    # 第一层：研究目标（红标题 + 关键词条）
    box(ax, x0, 4.68, W, 0.76)
    rich(ax, x0 + W / 2, 5.22, [("面向长大下坡的重载列车群组协同控制方法研究", RED)],
         fs=13.5, align="center")
    rich(ax, x0 + W / 2, 4.92, [("安全列距 · 车钩力红线 · 速度一致", "black")],
         fs=11, align="center")

    # 第二层：关键问题（研究难点一/二/三，关键词着色）
    dqs = [("研究难点一", [("如何实现多列车", "black")], [("协同决策", NAVY)]),
           ("研究难点二", [("如何保证循环制动下的", "black")], [("车钩力安全", RED)]),
           ("研究难点三", [("如何验证控制方法的", "black")], [("全程有效性", NAVY)])]
    for i, (h_, l1, l2) in enumerate(dqs):
        box(ax, bx[i], 3.30, bw, 1.05)
        ax.text(bcx[i], 3.30 + 0.80, h_, fontsize=11, color="black",
                fontweight="bold", ha="center")
        rich(ax, bcx[i], 3.30 + 0.44, l1, fs=10.5, align="center")
        rich(ax, bcx[i], 3.30 + 0.16, l2, fs=10.5, align="center")

    # 第三层：研究进展（同列对齐难点 + 进展小框）
    cts = [("研究进展一", "多智能体编队决策", "三列训练环境已建成"),
           ("研究进展二", "车钩力安全与规则执行", "安全层校验已闭环接入"),
           ("研究进展三", "仿真验证与动作预判", "全程验证链已搭建")]
    for i, (h_, t, s) in enumerate(cts):
        box(ax, bx[i], 1.50, bw, 1.32)
        ax.text(bcx[i], 1.50 + 1.04, h_, fontsize=10, color=NAVY,
                fontweight="bold", ha="center")
        ax.text(bcx[i], 1.50 + 0.72, t, fontsize=10.5, color=NAVY,
                fontweight="bold", ha="center")
        box(ax, bx[i] + 0.12, 1.50 + 0.12, bw - 0.24, 0.42)
        ax.text(bcx[i], 1.50 + 0.33, s, fontsize=9, color="black", ha="center")

    # 跨列总结线
    rich(ax, x0 + W / 2, 1.22, [("多智能体决策促协同，规则与安全层保安全，仿真孪生验全程", NAVY)],
         fs=11, align="center")

    # 第四层：验证评价
    box(ax, x0, 0.18, W, 0.72)
    ax.text(x0 + W / 2, 0.68, "闭环仿真与性能评价", fontsize=11, color="black",
            fontweight="bold", ha="center")
    rich(ax, x0 + W / 2, 0.38, [("列距误差 ｜ 列间速度差 ｜ 车钩力峰值 ｜ ATP 触发次数 ", "black"),
                                ("（49.6 km 全程剖面）", NAVY)], fs=10, align="center")

    # 层间块箭头
    for ytop, ybot in ((4.66, 4.42), (3.28, 2.90), (1.48, 1.32)):
        for cx in bcx:
            block_arrow_down(ax, cx, ytop, ybot, w=0.34, head=0.16)
    save(fig, "fig_v4_framework.png")


# ------------------------------------------------------- P9 上半 内容一架构
def fig_content1():
    fig, ax = new_ax(10.0, 3.2)
    # body: 每行 = [(text, color), ...] 分色段
    bs = [(0.30, 2.70, "①", [("编队", "black"), ("上下文观测", RED)],
           [[("列距 · 相对速度", "black")],
            [("前方坡度 · ", "black"), ("列尾压强就绪度", RED)]]),
          (3.55, 2.90, "②", [("机车级智能体 × 3", "black")],
           [[("每台机车 = 一个智能体", RED)],
            [("ED 连续动作 + AB 离散档位", "black")],
            [("（MAPPO）", "black")]]),
          (7.00, 2.70, "③", [("底层执行", "black")],
           [[("列内规则循环制动", "black")],
            [("动作经", "black"), ("车钩力安全层", RED), ("校验后下发", "black")]])]
    for bx, bw, num, title, body in bs:
        box(ax, bx, 0.45, bw, 2.25)
        ax.text(bx + 0.28, 2.42, num, fontsize=13, color=NAVY, fontweight="bold")
        rich(ax, bx + 0.62, 2.42, title, fs=12.5)
        n = len(body)
        cx = bx + bw / 2
        for k, line in enumerate(body):
            yk = 1.55 + (n - 1 - 2 * k) * 0.30
            rich(ax, cx, yk, line, fs=10.5, align="center")
    block_arrow_right(ax, 3.08, 3.47, 1.58, w=0.42, head=0.22)
    block_arrow_right(ax, 6.53, 6.92, 1.58, w=0.42, head=0.22)
    save(fig, "fig_v4_content1.png")


# --------------------------------------------------- P10 上半 内容二执行链
def fig_content2():
    fig, ax = new_ax(10.0, 3.6)
    chain = [("上层决策动作", ["ED / AB 目标指令"]),
             ("规则循环制动执行器", ["制动—缓解—再充风节奏"]),
             ("车钩力安全层", ["动作侧强制校验"]),
             ("ATP 防护", ["超速与危险操作拦截"])]
    bw, bh, y0 = 1.78, 1.5, 1.35
    xs = [0.30, 2.28, 4.26, 6.24]
    for i, ((t, sub), bx) in enumerate(zip(chain, xs)):
        fc = LBLUE if i == 2 else "white"
        box(ax, bx, y0, bw, bh, fc=fc)
        ax.text(bx + bw / 2, y0 + bh - 0.42, t, fontsize=10.5, color="black",
                fontweight="bold", ha="center", va="center")
        ax.text(bx + bw / 2, y0 + 0.42, sub[0], fontsize=9.0, color="#404040",
                ha="center", va="center")
        if i < 3:
            block_arrow_right(ax, bx + bw + 0.04, bx + bw + 0.26, y0 + bh / 2,
                              w=0.36, head=0.18)
    # 右侧栏：红线指标（红描边圆角框）
    box(ax, 8.10, y0 - 0.35, 1.80, bh + 0.7, ec=RED, lw=2.4, rounding=0.1)
    ax.text(9.0, y0 + bh + 0.05, "常规调速包络内", fontsize=9.5, color="black",
            fontweight="bold", ha="center", va="center")
    rich(ax, 9.0, y0 + bh - 0.32, [("车钩力 ≤ 1000 kN", RED)], fs=10, align="center")
    ax.plot([8.30, 9.70], [y0 + 0.62, y0 + 0.62], color=RED, lw=1.2)
    rich(ax, 9.0, y0 + 0.30, [("安全硬顶 2250 kN", "black")], fs=9.5, align="center")
    # 顶部流程说明
    ax.text(4.14, 3.35, "学习定策，规则执行：安全不依赖策略是否学到",
            fontsize=11, color=NAVY, fontweight="bold", ha="center")
    save(fig, "fig_v4_content2.png")


# --------------------------------------------------- P11 上半 五层链路图
def fig_content3():
    fig, ax = new_ax(10.0, 5.6)
    layers = [
        ("真实线路与车辆数据", None),
        ("高保真仿真", None),
        ("动作预演（未来数秒车钩力响应）", None),
        ("策略与安全层", None),
        ("界面平台与小车验证（硬件在环）", None),
    ]
    x0, W, bh, gap = 1.35, 7.3, 0.66, 0.30
    y = 5.6 - 0.42 - bh
    for t, red_sub in layers:
        box(ax, x0, y, W, bh)
        if red_sub:
            rich(ax, x0 + W / 2, y + bh / 2,
                 [(t, "black"), ("（" + red_sub + "）", RED)], fs=11.5, align="center")
        else:
            ax.text(x0 + W / 2, y + bh / 2, t, fontsize=11.5, color="black",
                    fontweight="bold", ha="center", va="center")
        if y > 0.4:
            block_arrow_down(ax, x0 + W / 2, y - 0.02, y - gap + 0.02, w=0.40, head=0.20)
        y -= bh + gap
    save(fig, "fig_v4_content3.png")


# ---------------------------------------------- P12 主视觉 验证链+能力栏
def fig_verify():
    fig, ax = new_ax(11.6, 5.6)

    # ---------- ① 高保真仿真面板（淡蓝） ----------
    p1x, p1y, p1w, p1h = 0.15, 2.95, 7.25, 2.50
    box(ax, p1x, p1y, p1w, p1h, fc=LBLUE)
    ax.text(p1x + 0.20, 5.14, "① 高保真仿真：全列纵向动力学与制动系统建模",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    bw, bh_, by = 1.62, 1.50, 3.42
    bxs = [p1x + 0.20 + i * (bw + 0.12) for i in range(4)]
    caps = ["单节车辆纵向动力学", "MT-2 缓冲器特性", "空气制动波传播", "49.6 km 线路高程"]
    for i, bx in enumerate(bxs):
        box(ax, bx, by, bw, bh_, fc="white")
        ax.text(bx + bw / 2, by + 0.14, caps[i], fontsize=8, color="black",
                fontweight="bold", ha="center", va="center")
    # (a) 公式框
    ax.text(bxs[0] + bw / 2, by + 0.92,
            r"$m_i a_i = F_i^{+} - F_i^{-}$" + "\n" + r"$-\ F_{g,i} - F_{\mathrm{air},i}$",
            fontsize=9, color="black", ha="center", va="center")
    # (b) MT-2 迟滞 mini
    mx, my = bxs[1] + 0.28, by + 0.55
    mw, mh = 1.05, 0.72
    t = np.linspace(0, 1, 60)
    load = 1500 * np.tanh(6 * (t - 0.08)) + 300 * t
    unload = 1500 * np.tanh(6 * (t - 0.30)) + 300 * t - 550
    ax.plot(mx + t * mw, my + load / 1500 * mh * 0.5 + mh * 0.25, color=NAVY, lw=1.4)
    ax.plot(mx + t * mw, my + unload / 1500 * mh * 0.5 + mh * 0.25 - 0.06,
            color=RED, lw=1.4, linestyle=(0, (4, 2)))
    # (c) 制动波传播 mini（楔形推进）
    wx, wy = bxs[2] + 0.24, by + 0.42
    ww, wh = 1.15, 0.85
    for k in range(5):
        frac = 0.22 + k * 0.19
        shade = [LBLUE, "#C7D6EE", "#9FB8DE", "#6E93C8", NAVY][k]
        ax.add_patch(Polygon([(wx, wy + wh * (k) / 5),
                              (wx + ww * frac, wy + wh * (k) / 5),
                              (wx + ww * frac, wy + wh * (k + 1) / 5),
                              (wx, wy + wh * (k + 1) / 5)],
                             fc=shade, ec="white", lw=0.6))
    ax.text(wx + ww / 2, wy - 0.045, "波头沿列传播", fontsize=6.5, color="#404040",
            ha="center", va="top")
    # (d) 线路高程 mini
    px, py = bxs[3] + 0.24, by + 0.42
    pw_, ph_ = 1.15, 0.85
    gx = np.linspace(0, 1, 120)
    gy = 0.55 - 0.38 * gx - 0.10 * np.sin(gx * 9)
    ax.plot(px + gx * pw_, py + gy * ph_, color=NAVY, lw=1.6)
    ax.plot([px, px + pw_], [py, py], color="#888888", lw=0.8)
    ax.plot([px, px], [py, py + ph_], color="#888888", lw=0.8)
    ax.text(px + pw_ / 2, py - 0.045, "宁武西 → 北大牛", fontsize=6.5,
            color="#404040", ha="center", va="top")
    ax.text(p1x + p1w / 2, 3.14, "制动波速、缓冲器特性等关键参数与实测对齐",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")

    # ---------- ② 动作预演面板（淡橙） ----------
    p2x, p2w = 7.55, 3.90
    box(ax, p2x, p1y, p2w, p1h, fc=LORANGE)
    ax.text(p2x + 0.20, 5.14, "② 动作预演：下发前预估车钩力",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    box(ax, p2x + 0.20, by, p2w - 0.40, bh_, fc="white")
    ax.text(p2x + p2w / 2, by + 0.14, "预演响应与仿真实测对比", fontsize=8,
            color="black", fontweight="bold", ha="center", va="center")
    tx = np.linspace(0, 6, 80)
    base = 1150 - 320 * np.exp(-((tx - 3.4) / 1.5) ** 2) + 90 * np.sin(tx * 2.2)
    ax.plot(p2x + 0.45 + tx / 6 * (p2w - 0.90),
            by + 0.52 + (base - 800) / 400 * 0.55, color=NAVY, lw=1.6)
    ax.plot(p2x + 0.45 + tx / 6 * (p2w - 0.90),
            by + 0.52 + (base - 800) / 400 * 0.55 + 0.035,
            color=RED, lw=1.3, linestyle=(0, (4, 2)))
    ax.plot([p2x + 2.55, p2x + 2.75],
            [by + 1.22, by + 1.22], color=NAVY, lw=1.6)
    ax.text(p2x + 2.82, by + 1.22, "预演", fontsize=7, color=NAVY,
            fontweight="bold", va="center")
    ax.plot([p2x + 2.55, p2x + 2.75], [by + 1.06, by + 1.06],
            color=RED, lw=1.3, linestyle=(0, (4, 2)))
    ax.text(p2x + 2.82, by + 1.06, "实测", fontsize=7, color=RED,
            fontweight="bold", va="center")
    ax.text(p2x + p2w / 2, 3.14, "预演与实测相符，超限动作提前拦截",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")

    # ---------- ③ 全程验证与部署面板（浅灰蓝） ----------
    p3y, p3h = 0.15, 2.55
    box(ax, 0.15, p3y, 11.30, p3h, fc=LGRAY)
    ax.text(0.35, 2.50, "③ 全程验证：基线运行、指标评价与部署测试",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    chain = [("规则控制与安全层", ""), ("49.6 km 全程剖面运行", ""),
             ("指标评价", "列距 · 列间速度差 · 车钩力"), ("界面平台与小车部署", "")]
    cbw, cbh, cy = 2.35, 0.78, 1.30
    cxs = [0.45 + i * (cbw + 0.55) for i in range(4)]
    for i, (t, sub) in enumerate(chain):
        box(ax, cxs[i], cy, cbw, cbh, fc="white")
        if sub:
            ax.text(cxs[i] + cbw / 2, cy + cbh - 0.26, t, fontsize=9.5,
                    color="black", fontweight="bold", ha="center", va="center")
            ax.text(cxs[i] + cbw / 2, cy + 0.24, sub, fontsize=7.5,
                    color="black", ha="center", va="center")
        else:
            ax.text(cxs[i] + cbw / 2, cy + cbh / 2, t, fontsize=9.5,
                    color="black", fontweight="bold", ha="center", va="center")
        if i < 3:
            xb0, xb1 = cxs[i] + cbw + 0.05, cxs[i] + cbw + 0.50
            mid = cy + cbh / 2
            ax.add_patch(Polygon([(xb0, mid - 0.07), (xb1 - 0.16, mid - 0.07),
                                  (xb1 - 0.16, mid - 0.15), (xb1, mid),
                                  (xb1 - 0.16, mid + 0.15), (xb1 - 0.16, mid + 0.07),
                                  (xb0, mid + 0.07)], fc=NAVY, ec=NAVY, lw=0.5))
            if i == 0:
                ax.text((xb0 + xb1) / 2, mid + 0.24, "控制指令", fontsize=7,
                        color="#404040", ha="center", va="bottom")
    # 回传虚线
    ry = cy - 0.22
    ax.plot([cxs[3] + cbw / 2, cxs[0] + cbw / 2], [ry, ry], color=NAVY, lw=1.2,
            linestyle=(0, (5, 3)))
    ax.plot([cxs[0] + cbw / 2, cxs[0] + cbw / 2], [ry, cy - 0.04], color=NAVY,
            lw=1.2, linestyle=(0, (5, 3)))
    ax.plot([cxs[3] + cbw / 2, cxs[3] + cbw / 2], [ry, cy - 0.04], color=NAVY,
            lw=1.2, linestyle=(0, (5, 3)))
    ax.annotate("", xy=(cxs[0] + cbw / 2, cy - 0.04),
                xytext=(cxs[0] + cbw / 2, ry),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.2))
    ax.text((cxs[0] + cxs[3] + cbw) / 2, ry - 0.02, "状态反馈", fontsize=7,
            color="#404040", ha="center", va="top")
    ax.text(0.15 + 11.30 / 2, 0.42, "规则控制基线完成全程运行，预演把超限动作拦截在决策下发之前",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")
    save(fig, "fig_v4_verify.png")


# --------------------------------------------------------- P14 蛇形时间线
def fig_timeline():
    fig, ax = new_ax(10.0, 5.6)
    nodes = [
        ("2026.09–11", "规则控制标定与训练准备", "（已完成基线标定）", "top"),
        ("2026.11–12", "综合测试与对比评估", "（进行中）", "bot"),
        ("2026.12–2027.01", "论文初稿", "", "top"),
        ("2027.01–03", "三列策略优化与补充实验", "", "bot"),
        ("2027.03–05", "项目总结与成果整理", "", "top"),
        ("2027.05–07", "论文投稿与检索", "", "bot"),
    ]
    xs = np.array([1.2, 2.8, 4.4, 6.0, 7.6, 9.2])
    # 蛇形粗带：基线 y=2.9，两个下凹钩
    xg = np.linspace(0.35, 9.85, 600)
    yg = 2.9 - 0.55 * np.exp(-((xg - 3.6) / 0.30) ** 2) \
               - 0.55 * np.exp(-((xg - 6.8) / 0.30) ** 2)
    bands = [(0.35, 3.0, LL), (3.0, 5.2, MB), (5.2, 7.6, NAVY), (7.6, 9.85, NAVY_D)]
    for xa, xb_, c in bands:
        m = (xg >= xa) & (xg <= xb_)
        ax.plot(xg[m], yg[m], color=c, lw=13, solid_capstyle="round", zorder=1)
    # 节点竖箭头 + 文字（1/3/5 在上，2/4/6 在下）
    band_colors = [LL, LL, MB, MB, NAVY, NAVY_D]
    for i, (date, task, st, side) in enumerate(nodes):
        x = xs[i]
        yr = 2.9 - 0.55 * np.exp(-((x - 3.6) / 0.30) ** 2) \
                   - 0.55 * np.exp(-((x - 6.8) / 0.30) ** 2)
        c = band_colors[i]
        if side == "top":
            ax.annotate("", xy=(x, 4.30), xytext=(x, yr + 0.10),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=3.0,
                                        mutation_scale=20))
            ax.text(x, 4.62, date, fontsize=12.5, color="black", fontweight="bold",
                    ha="center")
            rich(ax, x, 5.08, [(task, "black"), (st, RED)], fs=10.5, align="center")
        else:
            ax.annotate("", xy=(x, 1.50), xytext=(x, yr - 0.10),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=3.0,
                                        mutation_scale=20))
            ax.text(x, 1.18, date, fontsize=12.5, color="black", fontweight="bold",
                    ha="center")
            rich(ax, x, 0.72, [(task, "black"), (st, RED)], fs=10.5, align="center")
    save(fig, "fig_v4_timeline.png")


# ------------------------------------------------------------- P13 平台框图
def fig_gui():
    fig, ax = new_ax(10.0, 4.2)
    # 左栏：界面平台（四模块）
    box(ax, 0.40, 0.70, 4.30, 3.05)
    rich(ax, 2.55, 3.42, [("界面平台", "black")], fs=13, align="center")
    mods = [("算法管理", None), ("仿真运行", None), ("数据记录", None),
            ("分析服务", None)]
    mw, mh = 1.86, 0.50
    for i, (t, st) in enumerate(mods):
        row, col = divmod(i, 2)
        mx = 0.62 + col * (mw + 0.16)
        my = 2.52 - row * (mh + 0.14)
        box(ax, mx, my, mw, mh, lw=1.6, rounding=0.06, ec=NAVY)
        rich(ax, mx + mw / 2, my + mh / 2, [(t, "black")], fs=10.5, align="center")
    # 右栏：小车硬件在环
    box(ax, 6.60, 0.70, 3.00, 3.05)
    ax.text(8.10, 3.42, "小车部署测试台（硬件在环）", fontsize=12.5, color="black",
            fontweight="bold", ha="center")
    ax.text(8.10, 2.15, "欠驱动特性验证\n部署链路联调\n人机界面演示", fontsize=11,
            color="#404040", ha="center", va="center", linespacing=1.8)
    # 中间双向箭头 + 接口标签
    ax.annotate("", xy=(6.50, 2.55), xytext=(4.80, 2.55),
                arrowprops=dict(arrowstyle="<|-|>", color=NAVY, lw=2.0,
                                mutation_scale=18))
    ax.annotate("", xy=(6.50, 1.55), xytext=(4.80, 1.55),
                arrowprops=dict(arrowstyle="<|-|>", color=NAVY, lw=2.0,
                                mutation_scale=18))
    ax.text(5.65, 2.85, "统一数据接口", fontsize=10.5, color=NAVY,
            fontweight="bold", ha="center")
    ax.text(5.65, 1.25, "算法下发 / 数据回传", fontsize=10.5, color=NAVY,
            fontweight="bold", ha="center")
    ax.text(5.0, 0.22, "两个平台与仿真环境以统一数据接口衔接，构成算法—仿真—实物验证链",
            fontsize=11, color=NAVY, fontweight="bold", ha="center")
    save(fig, "fig_v4_gui.png")


def fig_env():
    """P10 三列编组环境示意图：49.6 km 剖面 + 三列车块 + 列距/速度差标注"""
    fig, ax = new_ax(10.0, 4.4)

    def px(km):        # 里程 → 画面 x
        return km / 49.6 * 9.2 + 0.4

    def py(elev):      # 高程 → 画面 y（1600→1.5, 1790→3.1）
        return 1.5 + (elev - 1600) / 190.0 * 1.6

    # 剖面：宁武西 → 北大牛 连续下坡（示意折线，画在画面坐标系内）
    xm = [0, 8, 16, 24, 34, 42, 49.6]
    ze = [1780, 1762, 1740, 1712, 1668, 1642, 1630]
    xs = [px(v) for v in xm]
    ys = [py(v) for v in ze]
    ax.plot(xs, ys, color=NAVY, lw=2.2)
    ax.fill_between(xs, ys, 0.30, color="#EDF1F7", zorder=0)
    ax.text(px(1.0), py(1745), "宁武西", fontsize=10.5, color="#404040")
    ax.text(px(44.6), py(1638), "北大牛", fontsize=10.5, color="#404040")
    ax.annotate("连续长大下坡　最大坡度 −12‰", xy=(px(24), py(1700)), fontsize=11,
                color=RED, fontweight="bold", ha="center")
    # 三列车块（1+0：单机车 + 货车）
    def train(km0, col, lab):
        x0 = px(km0)
        box(ax, x0, 0.42, 1.42, 0.34, fc=col[0], ec=col[1], lw=1.4)
        box(ax, x0 + 1.46, 0.42, 1.86, 0.34, fc="#FFFFFF", ec=col[1], lw=1.2)
        ax.text(x0 + 0.71, 0.59, "机车", fontsize=9, ha="center", va="center",
                color=col[1], fontweight="bold")
        ax.text(x0 + 2.39, 0.59, "货车 × 108", fontsize=9, ha="center",
                va="center", color="#404040")
        ax.text(x0 + 1.64, 0.98, lab, fontsize=11, ha="center",
                color=col[1], fontweight="bold")
    cols = [("#FBEAEA", RED), ("#E8EEF4", NAVY), ("#E4F1E4", "#2E7D32")]
    train(6, cols[0], "列车 1"), train(19, cols[1], "列车 2"), train(33, cols[2], "列车 3")
    # 列距（双箭头）
    def gap(a, b, lab):
        xa, xb = px(a), px(b)
        y = 0.24
        ax.annotate("", xy=(xb, y), xytext=(xa, y),
                    arrowprops=dict(arrowstyle="<|-|>", color="#555555", lw=1.2,
                                    mutation_scale=11))
        ax.text((xa + xb) / 2, 0.06, lab, fontsize=10, ha="center", color="#404040")
    gap(6, 19, "列距 L12"), gap(19, 33, "列距 L23")
    # 观测标注
    ax.annotate("", xy=(px(6) + 0.7, 1.30), xytext=(px(6) + 0.7, 1.90),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.3,
                                mutation_scale=12))
    ax.text(px(6) + 0.85, 1.98, "观测：邻列相对距离 / 相对速度 / 列尾充风",
            fontsize=10.5, color=NAVY, ha="left")
    ax.text(0.4, 3.95, "三列群组在 49.6 km 剖面上的相对状态（示意）", fontsize=11.5,
            color="black", fontweight="bold")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.3)
    ax.axis("off")
    save(fig, "fig_v4_env.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    fig_framework()
    fig_content1()
    fig_content2()
    fig_content3()
    fig_verify()
    fig_timeline()
    fig_gui()
    fig_env()


if __name__ == "__main__":
    main()
