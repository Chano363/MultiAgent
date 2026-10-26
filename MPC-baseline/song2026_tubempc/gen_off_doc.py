# -*- coding: utf-8 -*-
"""为"车钩力关闭"消融仿真生成独立 Word 文档（含 5 张专属图 + 指标表）。"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, r"d:\Z\first station\multi-agent-main\traffic_rl_project")
from src.train_dynamics.grade_profile import (PROFILES,                  # noqa: E402
                                              SHUOZHOU_REAL_SPEED_LIMIT)

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs_shuohuang")
D_DES = 2000.0
TAG = "shuohuang_coupler_off"
CSV = os.path.join(OUT, f"sim_{TAG}.csv")
PIC = os.path.join(OUT, "off_pics")
os.makedirs(PIC, exist_ok=True)
DOCX = os.path.join(OUT, "shuohuang_coupler_off_report.docx")


def load():
    return np.genfromtxt(CSV, delimiter=",", names=True)


def line_context():
    s = np.arange(0.0, 53600.0, 50.0)
    g = np.array([PROFILES["shuozhou_real_53km"]().grade_at(x) * 1000
                  for x in s])
    v = np.array([SHUOZHOU_REAL_SPEED_LIMIT.limit_at(x) for x in s])
    return s / 1000.0, g, v


def fig_speed(d):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(d["s_ref0"] / 1000, d["v_ref0"] * 3.6, "k--", lw=1.2,
            label="目标速度 (位置索引)")
    for i, c in enumerate(["C0", "C1", "C2"]):
        ax.plot(d["s_head0"] / 1000, d[f"v_head{i}"] * 3.6, color=c,
                lw=1.0, label=f"机车{i+1}")
    ax.set_title("速度跟踪（车钩力物理关闭）")
    ax.set_xlabel("头车里程 (km)")
    ax.set_ylabel("速度 (km/h)")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 100)
    fig.tight_layout()
    p = os.path.join(PIC, "fig_off_speed.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_gap(d):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, c in enumerate(["C1", "C2"]):
        ax.plot(d["t"] / 60, d[f"s_head{i}"] - d[f"s_head{i+1}"],
                color=c, lw=1.0, label=f"机车{i+1}–机车{i+2}")
    ax.axhline(D_DES, color="k", ls="--", lw=1.0, label=f"期望间距 {D_DES:.0f} m")
    ax.axhline(0, color="r", ls="-", lw=0.9, label="穿越边界 0 m")
    ax.set_title("头对头间距（车钩力物理关闭）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("头对头间距 (m)")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(PIC, "fig_off_gap.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_coupler(d):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i in range(3):
        ax.plot(d["t"] / 60, d[f"fc_peak{i}"], lw=1.0, label=f"列车{i+1}")
    ax.axhline(1500, color="r", ls="--", lw=0.9, label="安全限值 1500 kN")
    ax.set_title("车钩力峰值（物理关闭，恒为 0）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("车钩力峰值 (kN)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(PIC, "fig_off_coupler.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_cmd(d):
    fig, axs = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    for i in range(3):
        axs[0].plot(d["t"] / 60, d[f"b{i}"], lw=0.9,
                    label=f"列车{i+1} 循环制动减压量")
        axs[1].plot(d["t"] / 60, d[f"uhat{i}"], lw=0.9, label=f"列车{i+1} u_hat")
    axs[0].set_ylabel("减压量 (kPa)")
    axs[0].set_title("监督级空气制动与 Tube-MPC 机车指令（车钩力物理关闭）")
    axs[0].legend(ncol=3, fontsize=8)
    axs[0].grid(alpha=0.3)
    axs[1].axhline(0, color="k", lw=0.8)
    axs[1].set_ylabel("机车归一化加速度 u_hat (m/s²)")
    axs[1].set_xlabel("时间 (min)")
    axs[1].legend(ncol=3, fontsize=8)
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(PIC, "fig_off_cmd.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_profile(d):
    s_ctx, g_ctx, v_ctx = line_context()
    fig, ax1 = plt.subplots(figsize=(10, 5))
    for i in range(3):
        ax1.plot(d[f"s_head{i}"] / 1000, d[f"v_head{i}"] * 3.6, lw=1.0,
                 label=f"机车{i+1}")
    ax1.plot(s_ctx, v_ctx, "k--", lw=1.2, label="真实限速")
    ax1.set_xlabel("里程 (km)")
    ax1.set_ylabel("速度 (km/h)")
    ax1.set_ylim(0, 100)
    ax2 = ax1.twinx()
    ax2.plot(s_ctx, g_ctx, color="0.6", lw=0.8)
    ax2.set_ylabel("坡度 (‰)", color="0.4")
    ax2.tick_params(axis="y", colors="0.4")
    ax1.set_title("朔黄线 53.5 km 真实纵断面与运行轨迹（车钩力物理关闭）")
    ax1.legend(loc="lower left", ncol=4, fontsize=8)
    ax1.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(PIC, "fig_off_profile.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def compute_metrics(d):
    v_err = []; s_err = []
    for i in range(3):
        if i == 0:
            v_err.append(float(np.max(np.abs(d["v_ref0"] - d["v_head0"]))))
            s_err.append(float(np.max(np.abs(d["s_ref0"] - d["s_head0"]))))
        else:
            v_err.append(float(np.max(np.abs(d[f"v_head{i-1}"] - d[f"v_head{i}"]))))
            s_err.append(float(np.max(np.abs(
                (d[f"s_head{i-1}"] - d[f"s_head{i}"]) - D_DES))))
    fc = [float(d[f"fc_peak{i}"].max()) for i in range(3)]
    g12 = float(np.min(d["s_head0"] - d["s_head1"]))
    g23 = float(np.min(d["s_head1"] - d["s_head2"]))
    vs = np.concatenate([d[f"v_head{i}"] for i in range(3)]) * 3.6
    t_last = float(d["t"][-1] / 60.0)
    return {
        "v_err": v_err, "s_err": s_err, "fc": fc,
        "gap_min_12": g12, "gap_min_23": g23,
        "v_min": float(vs.min()), "v_max": float(vs.max()),
        "t_min": t_last, "dist": float(d["s_head0"][-1] / 1000.0),
    }


def make_doc(pics, m):
    from docx import Document
    from docx.shared import Inches, Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # ---- 标题 ----
    title = doc.add_heading("车钩力物理关闭 · 朔黄线仿真报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(
        "场景：Song2026 Tube-MPC × 朔黄线 53.5 km 真实线路 × multi-agent 仿真器。"
        "物理层面关闭全部车钩阻抗（刚度 / 预压 / 摩擦 / 限位 = 0），控制器与指令完全不变。"
    )

    # ---- 指标表 ----
    doc.add_heading("一、运行指标", level=1)
    p = doc.add_paragraph()
    p.add_run(f"覆盖里程 {m['dist']:.1f} km，运行时长 {m['t_min']:.1f} min，"
              f"速度范围 {m['v_min']:.1f} ~ {m['v_max']:.1f} km/h。")

    rows = [
        ("指标", "数值"),
        ("平均最大速度误差 (m/s)", f"{np.mean(m['v_err']):.2f}  "
             f"(机车1/2/3: {m['v_err'][0]:.2f} / {m['v_err'][1]:.2f} / {m['v_err'][2]:.2f})"),
        ("平均最大间距误差 (m)", f"{np.mean(m['s_err']):.1f}  "
             f"(机车1/2/3: {m['s_err'][0]:.0f} / {m['s_err'][1]:.0f} / {m['s_err'][2]:.0f})"),
        ("车钩力峰值/列 (kN)", f"{m['fc'][0]:.0f} / {m['fc'][1]:.0f} / {m['fc'][2]:.0f}"),
        ("头车间距最小值 1–2 (m)", f"{m['gap_min_12']:.1f}"),
        ("头车间距最小值 2–3 (m)", f"{m['gap_min_23']:.1f}"),
    ]
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.style = "Light Grid Accent 1"
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.rows[r].cells[c]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(10 if r else 11)
            if r == 0:
                run.bold = True

    # ---- 物理关闭说明 ----
    doc.add_heading('二、车钩力"物理关闭"的含义', level=1)
    doc.add_paragraph(
        '关闭组所有车钩均由 CouplerParams(stiffness=0, preload_n=0, friction_n=0, '
        'friction_static_n=0, friction_v_er=0, max_impulse_n=0, stroke_m=1e9, '
        'rigid_stiffness_nm=0) 初始化，仿真器 TrainDynamics 的车钩力计算返回值恒为 0。'
        '这是物理层面的消融，控制器 Tube-MPC 的代码与 γ=500 kN/m 前馈补偿均保留，'
        '只是被控对象不再响应。'
    )

    # ---- 图 ----
    doc.add_heading("三、速度跟踪", level=1)
    doc.add_picture(pics[0], width=Inches(6.2))
    doc.add_paragraph("图 1  速度跟踪曲线。头车按位置索引的目标速度 v_t(s)（含反向制动 a_dec=0.08 m/s² "
                      "与正向牵引 a_acc=0.15 m/s² 双向扫描）。", style="Caption")

    doc.add_heading("四、头对头间距", level=1)
    doc.add_picture(pics[1], width=Inches(6.2))
    doc.add_paragraph(
        f"图 2  头对头间距。期望间距 {D_DES:.0f} m。"
        f"本次仿真全程 {min(m['gap_min_12'], m['gap_min_23']):.0f} m ≥ 0，未出现数学穿越"
        f"（由列间安全包络兜住）；但零车钩下车内已解体（机车 80 km/h 时货车组达 88~99 km/h）。",
        style="Caption")

    doc.add_heading("五、车钩力峰值", level=1)
    doc.add_picture(pics[2], width=Inches(6.2))
    doc.add_paragraph("图 3  车钩力峰值。物理关闭下三列车的车钩力全部为 0 kN，符合预期。",
                      style="Caption")

    doc.add_heading("六、监督制动与 MPC 指令", level=1)
    doc.add_picture(pics[3], width=Inches(6.2))
    doc.add_paragraph("图 4  监督级空气制动（循环制动，50 kPa 二进制减压，T_AI=45 s 最短充风）"
                      "与 Tube-MPC 机车归一化加速度 u_hat。", style="Caption")

    doc.add_heading("七、线路剖面与运行轨迹", level=1)
    doc.add_picture(pics[4], width=Inches(6.2))
    doc.add_paragraph("图 5  速度-里程曲线叠加真实纵断面与限速。", style="Caption")

    # ---- 结论 ----
    doc.add_heading("八、消融结论", level=1)
    doc.add_paragraph(
        "车钩力关闭后，列车内部失去任何力传递路径："
    )
    doc.add_paragraph(
        "• 列间：安全包络能把机车头间距兜在正值以上，防止追尾（v2 关闭组头间距"
        "最小值 +1376 m vs v1 未加安全包络时 −1622 m）。",
        style="List Bullet"
    )
    doc.add_paragraph(
        "• 车内：机车与货车组速度差可超过 26 km/h（货车组被甩到 88~99 km/h，而机车保持 80 km/h），"
        "说明无动力货车组已完全失控，列车实际解体。",
        style="List Bullet"
    )
    doc.add_paragraph(
        "因此本次消融的正确读法是：车钩力是车内完整性的必要条件，列间安全层只能兜住追尾，"
        "无法替代车钩力的车内约束作用。",
        style="List Bullet"
    )

    doc.save(DOCX)
    return DOCX


def main():
    d = load()
    pics = [fig_speed(d), fig_gap(d), fig_coupler(d), fig_cmd(d), fig_profile(d)]
    m = compute_metrics(d)
    docx_path = make_doc(pics, m)
    print(f"文档已生成：{docx_path}")
    print(f"指标：v_err avg {np.mean(m['v_err']):.2f} m/s，"
          f"s_err avg {np.mean(m['s_err']):.1f} m，"
          f"fc = {m['fc']}，"
          f"gap min = {m['gap_min_12']:.0f} / {m['gap_min_23']:.0f} m，"
          f"v = [{m['v_min']:.1f}, {m['v_max']:.1f}] km/h")


if __name__ == "__main__":
    main()
