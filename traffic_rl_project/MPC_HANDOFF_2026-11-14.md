# MPC_HANDOFF_2026-11-14 · Tube MPC 基线（ADR-042 两基线之一）

> **交接对象**：接手 MPC 基线实现的下一个人（或未来的我）。
> **使命**：主表 Formation-MPC 行——ADR-042（2026-10-19 拍板）定核心 claim = 相比**两基线**（规则层 D-Rule + Tube MPC）改善列距保持与速度差收敛，H1/H2 均要求"优于两基线"。**Tube MPC 是主表必需对照，从未被删除**（ADR-067 决策四②曾误判终止，已撤回更正）。

---

## 1. 一句话现状

求解器与适配层代码已完成并通过单测（L1–L3），物理同源已证实（无需移植物理）；**正式基线数字尚未产出**——v1 因参考表单位 bug 作废，v2 有四个实现层问题待修（§4），修复后重跑（每次约 24 min）即可出数。

## 2. 代码地图（全部在主仓 `traffic_rl_project/`）

| 文件 | 内容 | 状态 |
|---|---|---|
| `src/mpc_baseline/params.py` | 主仓口径参数（M_LOCO=188 t、M_WAGON_GROUP=5 400 t、V_LIM=75/3.6、D_DES=1 434.5 m、DT_MPC=1.0 s）；Song2026 表 3 权重 Q=diag(0.5,0.5)/R=0.1/P=diag(0.6,0.4) 原样保留 | ✅ 单测过 |
| `src/mpc_baseline/tube_mpc.py` | 求解器：zba `tube_mpc.py`（146 行）**逐行保真移植**，只换 import。接口 `solve(x0, v_ref0, a_ref, d2) → û*` | ✅ 单测 7/7 |
| `tests/test_tube_mpc_baseline.py` | 零误差→零输入 / 方向性 / 输入收紧边界（式 56）/ tube 宽度 / 主仓参数抽查 | ✅ 7/7 |
| `src/evaluation/evaluate_mpc_tube.py` | L2 状态构造（误差状态 x0，符号约定 **x0[1]=v_ref−v_actual**，正=低于参考）+ L3 执行器（û→thr/ED/AB 反解，50 kPa 循环制动 + 45 s 充风）+ ETCS 式列间安全包络 + ref_speed_table 参考 | ⚠️ 有 §4 问题 |
| `docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` §6 | 移植设计规格（三层架构 + 参数对齐表 + 陷阱清单） | ✅ 已按 §4 修订版更新 |
| `docs/knowledge/song2026_tubempc_复现报告.md` | zba 复现报告归档（原在 zba 分支，2026-11-14 复制入主仓） | ✅ |

运行方式：`python src/evaluation/evaluate_mpc_tube.py --out_dir <dir> --coupler mt2 --max_steps 31500 --seed 0`

## 3. 物理同源：已证实，不要再怀疑这件事

- `zba` 复现报告 **§4** 白纸黑字：朔黄 53.5 km 对比的被控对象 = 主库 `TrainDynamics`（MT-2 车钩 / Newmark-β / 牵规法空气制动），**物理层未改一行**，逐车建模 55 质点/列。`tube_mpc.py` 一行未改。
- `LRN-20261113-001` 原判「plant 不同源」**只看了 §1–3 的简化复现层（9 质点 plant.py），是误判**，已加更正段。简化复现层的历史使命（证明求解器忠实于论文）已完成。
- **zba 分支处置（2026-11-14）**：worktree `D:\Code\MultiAgent\traffic_rl_zba\` 已删除；全部内容保留在 **`zba` 分支及 `origin/zba`**（提交 7b79a81），需要时 `git checkout zba` 或 `git worktree add ../traffic_rl_zba zba` 恢复。复现报告已归档主仓。
- 论文场景复现的偏差（下坡跟踪 5.4 m/s、车钩 809 vs 论文 330 kN）系论文未公开监督细节 + 循环制动二进制特性，**不改进、不进主表**；主表只需"忠实实现 + 本文场景表现"。

## 4. 待修的四个实现层问题（v2 评估暴露，2026-11-14 01:35）

按优先级排序，**全部修完再出正式基线**：

1. **提前终止未解**：只跑 7395 步（t=2465 s，s=45.78 km）就退出，`full_route=false`，终止原因未查明。先查 `evaluate_mpc_tube.py` 主循环的退出条件（疑似有隐藏的 break / NaN 传播触发）。
2. **`gap_lead` 前 ~1300 s 为 NaN**：列间安全包络 `v_allow = sqrt(v_lead² + 2·A_EB·净空)` 早期对列 1/2 失效嫌疑（NaN 进比较恒 False）。怀疑前车尾位置在起步段未初始化正确。修好前安全包络不可信。
3. **`fc_peak ≠ 0` 但车钩已物理置零**：`CouplerParams_stub` 全零阻抗下 `fc_peak` 却报 1296 kN——**该 peak 的语义未核实**（可能取自虚拟测量而非实际阻抗力）。主对比关车钩（ADR-042），fc 指标要么修语义、要么明确不报。
4. **满制动压不住速度**：后段 v=71.9 vs v_ref=56.7，uhat=-6.21（下限）、ED=0.80（p_d≤0.8 限幅）、AB=1.00 仍减不下来 ⇒ ED→力映射标度或 AB 循环制动参数存疑。对照 zba `shuohuang_sim.py:397-444` 的映射逐行核。

**修复验证顺序**：先 2（NaN）→ 1（终止）→ 4（制动标度）→ 3（fc 语义）。每步用 `--max_steps 600` 冒烟（约 50 s），最后全程 31500 步（约 24 min，solve 10.6 ms/步）。

## 5. 作废记录（不要引用）

| 产物 | 状态 | 原因 |
|---|---|---|
| `outputs/results/mpc_baseline/tube_v1_20261114/` | ⛔ INVALID | ref 表 `v_mps` 误乘 3.6，参考线 59→212 km/h，MPC 追假参考（末速 159.8）。旁有 `INVALID_V1_UNIT_BUG.txt`。**已修**：tbl_v 直读 + `V_CAP_MPS=75/3.6` 绝对封顶 |
| zba v2 朔黄数字（686/840/684 kN @5 600 t） | 中间记录 | 编组/场景与主仓不同，不进主表 |

## 6. 出数后的对照纪律（写作红线）

- 对照基线 = **规则层未调参 1 294 kN**（W3-3 定稿，band 100% / ATP 15 547 / 末速 59.7）+ 本 MPC 行 + D-RL。
- **MPC 行不比车钩**（ADR-033/034：显式关车钩约束，只主张编队指标：列距保持 / 速度带）。
- 引用任何"更优"必须并列代价口径（ATP 触发、速度带）——2026-11-13 rel60 教训（1 213 是 20 倍 ATP 换的）。
- metadata 全记录（`build_metadata`：mpc 参数、solve_ms、场景口径）——AGENTS 红线 5。
- 三方同物理同场景（主仓 49.6 km / 10 988 t / 4 300 m / 60 km/h / d_eff 128.7 / 75 口径 ADR-068）——同源性自动成立。

## 7. 场景参数卡（当前实现值）

| 项 | 值 | 来源 |
|---|---|---|
| 线路 | 朔黄 49.6 km 剖面（53.5 km 为**错误数据，弃用**——用户 2026-11-14 拍板） | 主仓 PROFILES |
| 编组 | 10 988 t ×3 列（1+108，HXD3B 188 t/9 600 kW） | consist_10kt_1plus108 |
| 起点/初速 | 4 300 m / 60 km/h | ADR-068 |
| 列间头距 | 1 424.7 m（与主仓 env reset 一致）；D_DES=1 434.5 m | 主仓口径 |
| MPC 视界 | H=5 × DT=1.0 s（zba 值恰与主仓 decision_interval=10×0.1 s 一致） | ✅ 无需改 |
| 循环制动 | 50 kPa 减压 + 45 s 最短充风 + AB 施加/缓解迟滞 ±0.5 km/h | Song2026 式 2-24 |
| 安全包络 | A_EB=0.15 m/s²，MIN_GAP_AIR=150 m | zba v2 |

---

*写于 2026-11-14 上午，交接时 W4-v2 训练（ep41–60，ed_idle 修复）并行进行中，与本基线无资源冲突。*
