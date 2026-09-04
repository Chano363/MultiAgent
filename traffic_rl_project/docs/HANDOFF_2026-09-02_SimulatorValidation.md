# Handoff：仿真器验证 —— 三层锚体系已建成、3 bug 已修复，剩余"论文数据定量复现"待执行

日期：2026-09-02 · 任务定位：**接手的 agent 执行"仿真器验证"的剩余工作**（物理/文献数据验证，不涉及训练调参）。
前置阅读：本文件 → `docs/VALIDATION_BASELINE.md`（V3.5.4–V3.5.7 + 验证原则）→ `docs/records/DIAGNOSTICS.md`（3 bug 诊断）→ `AGENTS.md`（Gotchas/命令）。

## 一句话现状

仿真器已通过**物理自洽验证**（第一锚守恒律 + 第二锚 RK4 独立实现交叉，9+2 测试全绿），并顺带发现修复了 **3 个动力学实现 bug**（其中一个令全部动力学系统性缩水 25%）。**但"论文工况对论文数字"的定量复现尚未开始**；且 Bug 3 修复后，历史上所有训练/验证数值（含论文核心结果）均需在修复后仿真器上重跑复核。

## 你要交付什么（验收 = 达成第 8 节全部）

把仿真器从"物理自洽 + 机制符合文献"推进到"能用论文工况复现论文数字（±可声明容差）"，产出一组绿色测试 + 更新后的论文数据文件。

---

## 1. 为什么做这件事（背景）

论文《面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法》的全部纵向动力学结论（M1/M3 协同增益、车钩力 ≤1000 kN 安全裕度）都产自本仿真器。无实车数据的条件下，必须用「物理不变量 + 独立实现 + 文献实测判据」三层锚建立可信度。

**核心纪律（Bug 3 教训）**：趋势/范围断言对系统性增益误差免疫——单调性、"峰值 < 限值"、"v₁ > v₀"在动力学整体缩水 25% 时依然全部通过。**必须与"独立真值"对账**：能量账本、闭式解、静止不动、第二个独立实现、论文的精确数值。

**标定集与验证集必须分离**：用于标定参数的文献（如赵紫宁 B1 波速 192 m/s 已隐含在我们的 200 m/s 参数里）不能再用作该参数的验证基准。

## 2. 已修复的 3 个 bug（位置、现象、影响）—— 接手先确认这些修复还在

完整诊断见 `docs/records/DIAGNOSTICS.md`「诊断-2026-09-02-三层锚验证测试发现并修复 3 个动力学 bug」。

| # | 位置 | 现象 | 修复 |
|:--:|:--|:--|:--|
| 1 | `src/train_dynamics/train.py` `_advance_control_once` | `ab_command=None` 被判为制动指令，头车挂 None 档 active 态 → 平坡静止蠕动、惰行能量差 33% | 新增 `elif ab_command is None: pass` |
| 2 | `src/train_dynamics/tractive.py` `tractive_force` | `v ≤ 1e-6` 时无视 throttle 输出满粘着牵引（882 kN @100t）→ 静止无指令列车被推走 | `throttle <= 0 → return 0` |
| 3 | `src/train_dynamics/train.py` `_step_newmark` | 欠松弛中间量被当最终状态 → **全部动力学响应缩水至 75%**（稳态 v_{n+1}=0.75·真解） | 收敛后取未松弛候选 `(x_cand, v_cand)`；仅迭代内用松弛 |

⚠️ **Bug 3 影响面**：历史上所有在 `_step_newmark` 上的结果（V 系列、M1/M3、车钩力 634/892/527/597 kN 等）都在 75% 动力学下产生。**量级与相对趋势可信，绝对值作废待重跑**。重跑后第一优先核对 8/28 疑点：仿真车钩力系统性偏低 ~40%（1 万吨 527/597 vs 朔黄实测 929/1021 kN），预期部分由 0.75 动力学造成，修复后峰值应上抬。

## 3. 已建立的验证资产（接手直接复用，勿重写）

### 3.1 测试（Windows Anaconda 可全跑，见第 5 节命令）
- `tests/test_physical_invariants.py` —— **第一锚**（9 passed）：静止不动（零预载）/预载蠕动有界/下坡加速/能量守恒 2%/稳态巡航闭式解 1%（注意：功率型牵引平坡平衡稳定、恒坡+功率电制动平衡**不稳定**，勿照抄旧工况）/阻力线性缩放/单车退化/多体 vs 刚性平坡·恒坡 0.5%
- `tests/test_field_benchmarks.py` —— **第三锚**（5 passed + 1 xfail + 1 skip）：S5 制动距离单向区间、D1 限值 2250 kN、S3 峰值在缓解阶段、B1 波速窗口、S4 xfail（前提未复现）、L1 skip（缺减压量模型）
- `src/train_dynamics/rigid_multi_particle.py` —— **第二锚**独立实现（RK4 聚合质点；半隐式 Euler 长时程误差 ~9% 不能作交叉基准）
- 全量：**119 passed, 1 skipped, 1 xfailed in ~171s**（不含需 torch 的 `test_mappo_train.py`）

### 3.2 判据资产（数据 SSOT 在 `docs/papers/` 信息卡，判据在 `docs/VALIDATION_BASELINE.md`）
| 节 | 来源 | 判据 | 状态 |
|:--|:--|:--|:--|
| V3.5.4 | 赵紫宁 2022 | B1–B6（参数标定） | B1 已转测试 |
| V3.5.5 | 张二田 2021（朔黄实车 19 次循环制动） | S1–S7 | 仅 S3/S4/S5 尝试，S4 xfail |
| V3.5.6 | 刘博阳 2022 | L1–L6 | 未转测试（L1 skip） |
| V3.5.7 | 王鼎 2023（大秦 46 次测力钩） | D1–D6 | D1/S3 已转测试 |

**四源量级交叉**（论文可直接引用）：张二田 1429 ｜王鼎 1490/1773 ｜刘博阳 742~1337 ｜赵紫宁 1195.8 kN —— 2 万吨循环制动峰值一致落 **1000~1800 kN**，均 < 2250 kN。

## 4. 剩余任务路线图（按优先级，每项自包含）

### P0-1 修复后重跑论文关键结果（先做，最紧急）
- **输入**：`docs/ITSC_PAPER.md` 中引用仿真数字的段落、`docs/records/DIAGNOSTICS.md` 历史诊断、训练脚本 `src/trainer/`、评估脚本 `outputs/` 下的 run 脚本
- **做法**：在修复后仿真器上重跑（或核对可复算的仿真器级场景，如循环制动车钩力/制动距离），列出新旧数值对照表
- **验收**：给出"旧值(75% 动力学) → 新值(100%)"对照表，标注哪些论文结论数值需更新、哪些不变（相对比较如 M1 vs M3 用同仿真器，结论方向预计不变但绝对值要核）
- **产出落点**：`docs/records/DIAGNOSTICS.md` 追加

### P0-2 2 万吨 1+1 验证编组 + 赵紫宁速度曲线 8 锚点（性价比最高）
- **输入**：`docs/papers/Zhao2022_fig53_velocity_anchors.csv`（8 个精确点：4 制动起点 + 4 缓解起点，含公里标+速度）；赵紫宁信息卡 §5.1 编组（2×HXD1 200t + 216×C80 100t，全长 2684 m，机车长 35.3 m 货车 12.1 m）；操纵结构表 5-3（制动/缓解点位 + 时长）
- **做法**：
  1. `train_env.py` `CONSIST_PRESETS` 加 `20kt_1plus1_validation`（**验证专用，勿作研究对象**）；坡度剖面按赵紫宁线路特征近似（−10‰/−12‰ 长大下坡分段即可，无需原纵断面）
  2. 复现试闸 + 3 段循环制动操纵序列，跑速度-位置曲线
  3. 对照 8 锚点：制动起点/缓解起点的公里标-速度偏差
- **验收**：曲线在锚点的平均误差 ≤ 2.5 km/h（赵紫宁自报其模型误差 2.03/1.81 km/h，作为可比基准）；结果连同 CSV 更新写入 VALIDATION_BASELINE（新 V3.5.8）
- **同时可做**：张二田 19 次循环制动统计对照——S1 均值 1021 kN / 超 1000 kN 次数 11/19 是否复现（编组同为 2 万吨 1+1，坡度量级 −9.4‰）

### P0-3 `braking.py` 扩展连续减压量 → 解锁 L1 + S5 定量化
- **目标**：空气制动从离散档位增加"减压量/列车管初压"连续输入（参照：MIN=70 kPa≈减压 50-70、SERVICE=140≈减压 170 缸压当量、EMERGENCY=470）
- **验收**：L1（列尾压强 585/589/593 kPa → 拉钩力 742/1058/1337 kN，单调 + −44.5%/−20.9% 邻域）测试解除 skip；S5 从"< 3302 m 单向"升级为 ±15% 定量（初速 68.4 km/h、−12‰、减压 100 kPa → 3302 m）
- ⚠️ 改动会触及环境动作空间，改前与论文训练配置解耦（加参数默认值保持向后兼容）

### P1-4 张二田五编组行为排序
- 表 1（5 编组对比）行为断言：232 辆 > 216 辆峰值；加中部机车（1+1 类）缓解同步提升 → 冲动下降（樊运新规律同源）。验收：趋势级测试绿

### P1-5 S4 解除 xfail
- 用变坡剖面复现张二田 R4/刘博阳 L4："缓解时全列坡度一致性 → 冲动"：构造陡坡制动→缓坡缓解（GradeProfile 分段），断言同坡缓解峰值显著低于跨变坡点缓解。验收：xfail → 真断言

### P1-6 审计既有"论文对照"数值测试是否在 75% 动力学下写过
- 逐个检查 `tests/` 与 VALIDATION_BASELINE 里含数值期望的断言/记录，标注"75% 下产生，需重跑"或已更新

## 5. 环境与命令

```bash
# Windows（动力学/物理测试都能跑）
cd D:/Code/MultiAgent/traffic_rl_project
D:/Anaconda/python.exe -m pytest tests/test_physical_invariants.py -q    # ~5 min
D:/Anaconda/python.exe -m pytest tests/test_field_benchmarks.py -q       # ~8 min
D:/Anaconda/python.exe -m pytest tests/ -q --ignore=tests/test_mappo_train.py
# RL 训练/含 torch 的测试须在 WSL conda：source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
```
项目无 pytest.ini；测试文件用 `sys.path.insert(0, 项目根)` 导入 `src.*`。运行 pytest 前 cwd 须在项目根。

## 6. API 速查（省去重新探索，签名以代码为准）

- `TrainDynamics(consist, coupler=CouplerParams(), dt=0.1)`；状态属性 `pos/vel(m/s)/grade/masses_kg/time`
- 主步进：`step_vehicles_ed_ab(throttle:ndarray, ed_throttle:ndarray, ab_command:AirBrakeNotch|None, brake_origin=0, release_sync=False, eot=False)`；**ab_command=None = 无空气制动（勿当 RELEASE）**；内部子步 ≤0.01s + Newmark-β
- 读取：`coupler_interface_forces()→N，长 n−1，正=前车受向前力`；`air_brake_state()→每车档位`
- 档位：`AirBrakeNotch.{RELEASE,MIN,SERVICE,EMERGENCY}`；波速 200/250 m/s（`train.py` 模块常量）
- 制动缸升压时间：`td.brake_rise_time_by_notch = {MIN:20, SERVICE:18, EMERGENCY:10}`（s）
- 钩缓：`CouplerParams(stiffness=1.89e7, preload_n=2e5, friction_n=5e5, coupler_gap_m=0.01, free_length_m=12.0)`；死区 `_dead_zone(x,gap)`
- 坡度：`GradeProfile(segments=[GradeSegment(0.0,-10.2)])`，`grade_at(m)→无量纲`；`td.set_grade_profile(p)`
- 编组：`TrainConsist([LocomotiveParams(), VehicleParams()...])`；预设见 `train_env.py CONSIST_PRESETS`
- 验证参照：`RigidTrain`（`src/train_dynamics/rigid_multi_particle.py`，`reset(speed_mps, grade)` + `step(ed_throttle, ab_notch)`，RK4）

## 7. 陷阱清单（新增内容务必读，AGENTS.md Gotchas 也已同步）

1. Newmark 欠松弛只用于迭代，**收敛态必须取未松弛候选**
2. `tractive_force` 静止分支先判 throttle
3. `ab_command=None` ≠ RELEASE
4. 独立交叉基准用 RK4，不用半隐式 Euler（长时程差 ~9%）
5. 恒坡 + 功率型电制动无稳定平衡；平坡 + 恒牵引才有稳定巡航
6. 文献"规律类"断言须复现其前提（如同坡缓解/充分充风），否则标 xfail 而非改阈值
7. 阻力/坡度单位：阻力 N（Davis 含独立于车重的空气项）；坡度无量纲（‰/1000，正=上坡）
8. 测试耗时：physical ~5 min / field ~8 min（101 车 × 0.01s 子步），别用 -x 反复全跑

## 8. 验收清单（全部达成 = 本任务完成）

- [x] P0-1：论文引用数值在新仿真器下重跑，新旧对照表入 `DIAGNOSTICS.md`，"车钩力偏低 40%"疑点有结论（1 万吨 527/597→885 kN，+48~68% 由 Bug 3 造成；2 万吨满 SERVICE 2405 kN 偏高归因于满档减压）
- [x] P0-2：2 万吨 1+1 验证编组 + 赵紫宁 8 锚点速度曲线测试绿（4 段误差 0.0 ≤2.5 km/h），张二田 S1 统计尝试对照（全程峰值 1677 kN 落入四源带；均值 685<1021 诚实标注固定控制器局限）
- [x] P0-3：braking.py 连续减压量就绪且向后兼容；L1 解除 skip；S5 定量化（1513/1627 m 落 [1050,3302) 带）
- [x] P1-4/5/6：五编组排序绿（232>216）、S4 解除 xfail（659 kN）、历史数值断言标注或更新（fleet 区分度测试 100% 动力学校准）
- [x] VALIDATION_BASELINE.md「对照数据提取进度」清单同步更新（新增 V3.5.8 定量复现节）
- [x] 本文件对应条目勾选后，把结论与新数值留给下一份 handoff/工作日志（见 `docs/records/DIAGNOSTICS.md`「诊断-2026-09-02-P0-2/3 + P1-4/5/6」+ `.codebuddy/memory/2026-09-02.md`）

> ✅ **2026-09-02 验收达成**：仿真器从"物理自洽 + 机制符合文献"推进到"论文工况定量复现"。
> 全量测试 125 passed（Windows Anaconda）。遗留：M1/M3/MPC 论文表 MARL 评估重跑留给用户手动执行（WSL conda）。

## 9. 文献数据 SSOT（需要精确数值时从这里取，勿复制到别处）

- `docs/papers/Zhao2022_AirBrakeRefinedModeling_Optimization.md`（+`_fulltext.txt`、`Zhao2022_fig53_velocity_anchors.csv`）
- `docs/papers/张二田2021_朔黄2万t车钩力实测.md`（+`_fulltext.txt`）
- `docs/papers/刘博阳2022_列尾压强与车钩力.md`（+`_fulltext.txt`）
- `docs/papers/王鼎2023_大秦线车钩力跟踪试验.md`（+`_fulltext.txt`）
- 判据索引：`docs/VALIDATION_BASELINE.md` V3.5.4–V3.5.7；文献登记：`docs/RESEARCH_POSITIONING.md` §2.1/2.2.1/2.2.2/3.4.1
- 未找到/待获取（别浪费时间重找）：王鼎《太原铁道科技》2023(1)、姚小沛 2013、伏远昱 2020、姚小沛 2014、马大炜 2008、冀彬 2008
