# HANDOFF · PPT 剩余缺失完善 · 2026-08-31

> **用途**：本文件供**新对话**直接继续完善 PPT 用。所有缺失均已用脚本/源码定位到精确 HTML 锚点，可直接定位。
> **目标文件**：`d:\Code\MultiAgent\traffic_rl_project\ppt_talk\train-marl-talk.html`
> **注意**：本 PPT 曾被浏览器实时编辑，**多处空表框/空 div 是被清空导致的**，非刻意留白。

---

## 一、已完成的修复（无需重做，仅核对）

上一轮已用 `tmp_fill2.py` 填充 4 处表格 + 删除第13页说明，**已验证全部在位**：

| 页 | 位置 | 内容 | 验证 |
|:--|:--|:--|:--|
| 训练流程页 | 右侧/表格区 | **关键超参数表**（MAPPO、lr=5e-5、entropy=0.005、clip ε=0.2/4epoch、GAE λ=0.95 γ=0.99、Curriculum 300→1000→3000、600轨迹·best-checkpoint评估） | ✅ `Curriculum horizon` |
| 压力消融页 | 上侧/表格区 | **压力消融表**（100m: M-MARL+37,342/No-C+9,791/增益+27,551/追尾69；40m: +37,382/−11,137/+48,519/179）+ 尾注「M-MARL 100m训练、40m复用，两间距追尾恒0」 | ✅ `M-MARL 于 100 m 训练` |
| 规模扩展页 | 上侧/表格区 | **3列vs5列表**（增益+27,551/+1,970、追尾0/0、车钩力659/634kN） | ✅ `634 kN` |
| 跨线泛化页 | 大面积缺失区 | **phys2跨线表**（M-MARL复用+36,120/追尾0/623kN；No-C −6,688/追尾143） | ✅ `No-C（无协同）` |
| 规模扩展页 | 底部 | **已删说明文字**（「5列与3列名义场景初始态协议不同……」整段删除） | ✅ 已不在 |

---

## 二、仍缺失的 3 处（需新对话填充）

### 缺失 A —— 仿真器验证页：左侧空表框（@ pos 20672）

**现状 HTML**（`<div style="...padding:6px 14px">` 后紧跟空行即闭合，内部为空）：
```html
<div style="display:grid; grid-template-columns:1fr 1fr; gap:26px; align-items:start">
  <div>
    <div style="border:1px solid var(--stone); border-radius:16px; background:var(--iv-card); padding:6px 14px">
      <!-- 缺失：双基准对照数据表 -->
    </div>
    <div class="emphasis" style="font-size:14.5px; margin-top:14px">A、B 两基准<b>均在文献工况下通过</b> → 车钩力绝对量级可信，可支撑安全裕度结论。</div>
  </div>
  <div> ...右侧 基线对齐重建①(MT-2) ②(dt 0.01) ... </div>
</div>
```

**建议填充**：双基准(A基准/B基准)对照表，随 emphasis 文字「A、B 两基准均在文献工况下通过」。结构建议 3~4 行 × 3~4 列，如：

| 项目 | 基准值(文献) | 本仿真 | 判定 |
|:--|:--|:--|:--|
| 车钩力峰·基线A(张二田朔黄实测) | 929~1748 kN | 527/597 kN | ✅ 量级匹配 |
| 车钩力峰·基线B(樊运新编组3) | 952.6/1004.6 kN | ~527/597 kN | ✅ 量级匹配 |
| 车钩力上限(铁科院 Chu2025) | 1000 kN | SafetyLayer钳制 | ✅ 低于上限 |

> 数据来源：`docs/VALIDATION_BASELINE.md` 的 **V6.1（张二田实测929-1748kN、仿真527/597kN量级匹配）**、**V6.2（樊运新编组3=952.6kN拉/1004.6kN压）**、**V6.7（铁科院1000kN正常/1500kN常用/2250kN紧急）**。注意本页元素此前被浏览器清空，属于"原本有内容被清掉"，填充时尽量与右侧"基线对齐重建①②"呼应（提及 MT-2 重建后 6634→634kN 已对齐文献量级）。

---

### 缺失 B —— 主结果页：中部指标带（@ pos 24341）

**现状 HTML**（基线定义 div 之后、主对比图之前的一个空表框）：
```html
<div style="display:grid; grid-template-columns:1fr 1fr; gap:2px 20px; margin-top:2px">
  <span><b>M-MARL</b> 本文方法 ...</span>
  <span><b>No-C·无协同</b> ...</span>
  <span><b>DQN-fair</b> ...</span>
  <span><b>MPC</b> ...</span>
</div>
<div style="border:1px solid var(--stone); border-radius:16px; background:var(--iv-card); padding:4px 12px; margin-top:8px">
  <!-- 缺失：4模型核心指标摘要带 -->
</div>
<div style="display:grid; grid-template-columns:1.15fr 1fr; gap:24px; margin-top:8px; align-items:center">
  <div class="img"><img alt="主对比图" src="train-marl-talk/assets/fig_phys2_main_compare.png" ...>
  ...
</div>
```

**建议填充**：4 模型核心指标摘要带（横向一行，reward/追尾/车钩力峰值/间距min），数据来源于 `docs/VALIDATION_BASELINE.md`「主对比（朔黄线 3000 步）」：

| 模型 | reward | 追尾步数 | 车钩力峰(kN) | 间距min(m) |
|:--|:--:|:--:|:--:|:--:|
| **M-MARL** | **+37,342** | **0** | **659** | **175** |
| No-C | +9,791 | 69 | 543 | −45（追尾穿透） |
| DQN-fair | −15,215 | 157 | 463 | −116 |
| MPC | −115,622 | 0 | **1178（超限，红）** | 105 |

> 用色：M-MARL 该行手饰（如浅高亮底）；MPC 车钩力 1178kN 超 1000 限值，用红色/警示色标注，呼应下方图注「红线上限 1000 kN」。此表建议做成一行紧凑的 summary 卡片或 4 列分栏，别与下方主对比图重复堆叠过多。

---

### 缺失 C —— 训练流程页：5 个空 `<p></p>`（@ pos 22080~22689）

**现状**：流程图第 2~6 步的 `<p></p>` 描述为空（第1步"初始化"和第7步"全程评估"有文字）。5 个空步骤的 h4 标题分别为：

| 步骤 | h4 标题（已有） | 缺失的 `<p>` 描述（需补） |
|:--|:--|:--|
| CL | Curriculum 课程：horizon 300 → 1000 → 3000 步 | 建议：`缓解波速度随机化 → 鲁棒性提升` |
| ① | N 列车并行采样轨迹（600 eps） | 建议：`整列状态 s + 共享策略 π，并行收集回合数据` |
| ② | GAE 优势估计 · λ=0.95 γ=0.99 | 建议：`估计优势，减方差` |
| ③ | PPO clip 更新 · ε=0.2 · 4 epochs | 建议：`裁剪目标 + 熵正则（0.005）` |
| ④ | KL>0.015 → 提前停止 · 保存 best + final | 建议：`防策略突变，存双 checkpoint` |

> 建议补足简明描述，与第1步「共享策略 π + 集中式评论家 V · 3 个随机种子独立训练」、第7步「回报 / 追尾步数 / 峰值车钩力 / 最小间距」（已有）风格对齐。**文字尽量简短**，避免步骤块过高溢出。

---

## 三、操作提示（新对话必读）

1. **改文件方式**：`train-marl-talk.html` 是单文件，改前建议 `git status`/备份副本；用精确字符串替换（勿用正则跨多层，易 0 匹配），可仿照 `docs/HANDOFF_2026-08-31.md` 的既有数据核验。
2. **临时脚本**：改完即删 `tmp_*.py`；本文件提到的 `tmp_audit*.py` 已完成使命应删除。
3. **数据权威来源**：
   - 主对比/压力消融/健壮性/5列：`docs/VALIDATION_BASELINE.md`（末尾"主对比 3000 步"段）
   - 第二剖面 phys2：`docs/VALIDATION_BASELINE.md` 及 `docs/HANDOFF_2026-08-31.md`
   - 车钩力阈值：铁科院 Chu2025（1000kN 正常 / 1500kN 常用 / 2250kN 紧急）
4. **核验方式**：改后可用浏览器打开 `http://127.0.0.1:8631/train-marl-talk.html`（若服务已关：`cd ppt_talk && python -m http.server 8631`），逐页检查。**注意**：浏览器自动重排/编辑会把 HTML 中空表框清空，属已知现象——应在源文件（本 HTML）里直接用手改修复，而不是在浏览器可视化编辑器里补（易再次清空）。