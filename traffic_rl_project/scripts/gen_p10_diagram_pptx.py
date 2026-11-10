# -*- coding: utf-8 -*-
"""生成 P10 右栏原生形状素材 PPTX：①②③架构图 + 三列编组环境示意图。
打开后框选复制到自己的答辩 PPT 页面即可（均为原生形状，可改字改色）。
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

NAVY = RGBColor(0x2F, 0x4A, 0x7A)
RED = RGBColor(0xC0, 0x00, 0x00)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY = RGBColor(0x55, 0x55, 0x55)
LIGHT = RGBColor(0xED, 0xF2, 0xF9)

FONT = "微软雅黑"


def set_font(run, size, color, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    r = run._r
    rPr = r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", FONT)


def add_box(slide, x, y, w, h, line=NAVY, fill=WHITE, lw=1.5, round_=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if round_:
        try:
            shp.adjustments[0] = 0.12
        except Exception:
            pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(lw)
    shp.shadow.inherit = False
    return shp


def add_text(slide, x, y, w, h, runs_lines, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE, space_after=2):
    """runs_lines: [[(text,size,color,bold),...], ...] 每个子列表=一段"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(2)
    tf.margin_top = tf.margin_bottom = Pt(1)
    for i, line in enumerate(runs_lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        for txt, size, color, bold in line:
            r = p.add_run()
            r.text = txt
            set_font(r, size, color, bold)
    return tb


def add_arrow_r(slide, x, y, w, h):
    shp = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y),
                                 Inches(w), Inches(h))
    shp.fill.solid(); shp.fill.fore_color.rgb = WHITE
    shp.line.color.rgb = NAVY; shp.line.width = Pt(1.2)
    shp.shadow.inherit = False
    return shp


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    # ============ 上：①②③ 架构图（右栏宽约 6.9"） ============
    bw, bh, y0 = 2.02, 1.95, 0.45
    xs = [0.35, 0.35 + bw + 0.42, 0.35 + 2 * (bw + 0.42)]
    # ①
    add_box(s, xs[0], y0, bw, bh, lw=1.4, round_=True)
    add_text(s, xs[0] + 0.08, y0 + 0.06, bw - 0.16, 0.42,
             [[("① ", 12, BLACK, True), ("编队上下文", 12, RED, True),
               ("观测", 12, BLACK, True)]])
    add_text(s, xs[0] + 0.08, y0 + 0.62, bw - 0.16, 1.2,
             [[("列距 · 相对速度", 10.5, BLACK, False)],
              [("前方坡度 · ", 10.5, BLACK, False),
               ("列尾充风状态", 10.5, RED, False)]])
    # ②
    add_box(s, xs[1], y0, bw, bh, lw=1.4, round_=True)
    add_text(s, xs[1] + 0.08, y0 + 0.06, bw - 0.16, 0.7,
             [[("② ", 12, BLACK, True), ("机车级智能体 × 3", 12, RED, True)],
              [("每台机车 = 一个智能体", 9.5, BLACK, False)]])
    add_text(s, xs[1] + 0.08, y0 + 0.95, bw - 0.16, 0.9,
             [[("电制动连续 + 空气制动离散", 10.5, BLACK, True)],
              [("（MAPPO）", 10, BLACK, False)]])
    # ③
    add_box(s, xs[2], y0, bw, bh, lw=1.4, round_=True)
    add_text(s, xs[2] + 0.08, y0 + 0.06, bw - 0.16, 0.42,
             [[("③ 底层执行", 12, BLACK, True)]])
    add_text(s, xs[2] + 0.08, y0 + 0.62, bw - 0.16, 1.2,
             [[("列内规则循环制动", 10.5, BLACK, False)],
              [("动作经", 10.5, BLACK, False),
               ("车钩力安全层", 10.5, RED, True),
               ("校验后下发", 10.5, BLACK, False)]])
    # 两个块箭头
    for i in (0, 1):
        add_arrow_r(s, xs[i] + bw + 0.06, y0 + bh / 2 - 0.16, 0.30, 0.32)

    # ============ 下：三列编组环境示意图（原生形状） ============
    gy = 3.05            # 环境图区顶
    gw = 6.85            # 总宽
    gx = 0.35
    # 标题行
    add_text(s, gx, gy, gw, 0.34,
             [[("三列群组决策环境（49.6 km 宁武西 → 北大牛）", 12, BLACK, True)]],
             align=PP_ALIGN.LEFT)
    # 剖面线（下降折线，用直线段拼）
    import math
    x_l, x_r = gx + 0.05, gx + gw - 0.05
    y_l, y_r = gy + 1.95, gy + 1.25      # 左高右低
    n = 4
    for k in range(n):
        xa = x_l + (x_r - x_l) * k / n
        xb = x_l + (x_r - x_l) * (k + 1) / n
        ya = y_l + (y_r - y_l) * k / n
        yb = y_l + (y_r - y_l) * (k + 1) / n
        ln = s.shapes.add_connector(1, Inches(xa), Inches(ya),
                                    Inches(xb), Inches(yb))
        ln.line.color.rgb = NAVY
        ln.line.width = Pt(2.0)
        ln.shadow.inherit = False
    # 起终点标注 + 坡度
    add_text(s, gx - 0.1, gy + 1.85, 1.0, 0.3,
             [[("宁武西", 9, GRAY, False)]], align=PP_ALIGN.LEFT)
    add_text(s, gx + gw - 1.05, gy + 1.62, 1.0, 0.3,
             [[("北大牛", 9, GRAY, False)]], align=PP_ALIGN.RIGHT)
    add_text(s, gx + 1.6, gy + 0.5, 3.8, 0.3,
             [[("连续长大下坡  最大坡度 −12‰", 10.5, RED, True)]])
    # 三列车组（机车小矩形 + 货车长矩形），骑在剖面线上
    def train(fx, color):
        cx = x_l + (x_r - x_l) * fx
        cy = y_l + (y_r - y_l) * fx
        loco_w, wag_w, th = 0.42, 0.56, 0.20
        n_wag = 3
        total = loco_w + 0.03 + n_wag * (wag_w + 0.02)
        x0 = cx - total / 2
        add_box(s, x0, cy - th - 0.03, loco_w, th, line=color, fill=None,
                lw=1.4)
        add_text(s, x0 - 0.15, cy - th - 0.36, loco_w + 0.3, 0.28,
                 [[("机车", 8.5, color, True)]])
        for j in range(n_wag):
            wx = x0 + loco_w + 0.03 + j * (wag_w + 0.02)
            add_box(s, wx, cy - th - 0.03, wag_w, th, line=color, fill=None,
                    lw=1.0)
        add_text(s, x0 + loco_w, cy + 0.14, total - loco_w, 0.28,
                 [[("…… 货车 × 108", 8.5, GRAY, False)]],
                 align=PP_ALIGN.CENTER)
    train(0.16, RED)
    train(0.48, NAVY)
    train(0.78, RGBColor(0x2E, 0x7D, 0x32))
    # 列距双箭头（在车组下方）
    def gap(fx1, fx2, lab):
        xa = x_l + (x_r - x_l) * fx1
        xb = x_l + (x_r - x_l) * fx2
        ya = y_l + (y_r - y_l) * fx1
        yb = y_l + (y_r - y_l) * fx2
        y = max(ya, yb) + 0.55
        ar = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(xa),
                                Inches(y), Inches(xb - xa), Inches(0.18))
        ar.fill.solid(); ar.fill.fore_color.rgb = LIGHT
        ar.line.color.rgb = GRAY; ar.line.width = Pt(1.0)
        ar.shadow.inherit = False
        add_text(s, (xa + xb) / 2 - 0.6, y + 0.16, 1.2, 0.26,
                 [[(lab, 9, BLACK, False)]])
    gap(0.18, 0.50, "列距 L12")
    gap(0.50, 0.82, "列距 L23")

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ppt_talk", "midterm_20261018", "P10_右栏素材_原生形状.pptx")
    prs.save(out)
    print("saved:", out)


if __name__ == "__main__":
    build()
