# 求解器口径与开训门槛状态记录（2026-11-04）

> 角色：**状态索引**，不是实验证据、不是立论。数值与结论仍以对应归档 `result.json` / `numerical_summary.json` 与 ADR 为准。
> 全文路径均为相对仓库根（`traffic_rl_project/` 起）。历史外部归档统一记作 `external_archive/<目录名>`（未随仓库迁移，仅作出处标记）。

## 1. 求解器时间线

| 日期 | 事件 | 位置 |
|---|---|---|
| 2026-08-30 | 生产侧引入 Newmark-β（β=1/4、γ=1/2）+ Picard 迭代，`newmark_max_iter=30`、`newmark_tol=1e-5`（**位移残差**判据）；不收敛静默回退欠松弛态 α=0.5 | `src/train_dynamics/train.py`（`_step_newmark`） |
| 2026-10-19 | 诊断侧分出实验求解器（解析切线 Newton、力残差判据、时间误差控制自适应步长），仅诊断为显式 opt-in | `src/evaluation/adaptive_newmark_candidate.py`、`newton_mechanics_candidate.py`、`error_controlled_mechanics.py` |
| 2026-11-01 | `solver` 标签机制：导入时捕获生产入口身份比对，实验求解器必须显式标签，禁止静默替换；metadata 记 `solver` | `src/evaluation/solver_registry.py` |
| 2026-11-04 | 阶梯消融 + 步长收敛定案：生产默认保留原 Newmark 公式，仅在每个 0.01 s 气动子步内做 0.0025 s **机械子步**；气动/波速仍按 0.01 s | `src/train_dynamics/train.py`（`mechanical_max_step`）；ADR-048 |

## 2. 生产与诊断同源铁律的落地位置

- **执行层**：`src/evaluation/solver_registry.py` —— `PRODUCTION_STEP_NEWMARK` 身份捕获、`SOLVERS` 白名单、`assert_active_solver()`、`runtime_solver_record()`；实验求解器只能经 `solver_context()` 显式切换。
- **只读观察豁免**：`src/evaluation/newmark_observer.py` —— `PURE_OBSERVERS` 白名单，观察器委托生产实现，不重贴标签。
- **归档层**：训练/评估 metadata 必带 `solver` 与 `newmark_mechanical_max_step`（`runtime_solver_record()`），缺字段的结论不得引用。
- **文档层**：`docs/rules/EXECUTION_RULES.md`（metadata 强制）+ `docs/logs/decisions/DECISIONS.md` ADR-048（口径变更的影响说明）。

## 3. 规则层当前状态（零 RL）

**单列 1+0（10988 t，1 机车 + 108 货车）**

- 70 km/h 冷起点、49.6 km 全程：**已通过**（见第 4 节证据与 ADR-048 后复跑归档）。
- 归档：`outputs/sim_validation/phys_validation/single_production_subcycle_70kmh_full_20261104/`。

**三列编队（3 × 1+0，3 智能体）**

- 80 km/h 冷起点主工况：**未通过**（`route_completed` 未达成）。旧归档 `outputs/sim_validation/phys_validation/fleet_production_edramp02_80kmh_full_20261104/` 在 t=301.5 s、5.91 km 处峰值 1007.99 kN 触发诊断早停。
- 70 km/h 冷起点 + 起点整体前移 2800 m（ADR-049）的"不早停"全程：`outputs/sim_validation/phys_validation/fleet3_production_subcycle_70kmh_full_unstopped_20261104/` —— `route_completed` 达成（均速 58.2 km/h），但**有效路段峰值 1288.5 kN**（t=1846.7 s、km33.6、中列第 47 号车钩），远超 1000 kN；数值侧 0 未收敛（378 万子步、残差 7.5e-6 m）。
- 70 km/h 冷起点 + 起点整体前移 2800 m 的早停版：t=103.5 s、1.77 km 处峰值 **1005.11 kN**（`outputs/sim_validation/phys_validation/fleet3_production_subcycle_70kmh_full_20261104/`）。
- 数值侧健康：两轮均 0 未收敛子步、最大位移残差 ~7e-6 m、平均迭代 1.0 ⇒ **越线不是求解器数值问题**。
- 已定位原因：
  1. **物理缺口**：满 ED 约 547 kN < 长大下坡维持 80 km/h 所需约 903 kN，循环制动周期内掉速不可避免；
  2. **充风门**：`ab_min_refill_s = 222 s` 限制 AB 源复用节奏，与 80 km/h 目标速度带不匹配；
  3. **起点条件（非设备故障）**：`init_speed_kmh` 恰等于 `v_max` 时安全层按 `vel >= max_speed - 1e-6` 判 overspeed；跟随车起点位于 km<0（未进 ETCS 覆盖区）触发 `etcs_permitted`。这两类合计造成 329 次"安全事件"，须按起点条件规范消除，不得当成设备/仿真缺陷。

## 4. 训练链路已验证证据（部分作废，2026-11-08 核对）

- 2026-10-21 全剖面 **BC 采集段**：`outputs/checkpoints/formation_10kt_1plus108/fullprof_20261021/seed0/results/run.log`，1 集 36000 步、3421 s（≈0.095 s/步）、生产默认 Newmark。
  - ⚠️ **该板次只作计时证据**：`run.log` 停在 BC 预训练之后（BC loss −2.406），**RL 循环一次都未进入**，目录内无 `.pt`、无训练历史。死因 = `curriculum: 36000:0` 被 YAML 1.1 解析成六十进制整数 2 160 000，`_parse_curriculum` TypeError（2026-11-08 已修复）。详见 `DIAGNOSTICS_2026-11.md` 小节（十三）。
- 2026-10-23 性能改动（numba 车钩核与缓存，`8e9c7a9`）parity 覆盖：`tests/test_coupler_numba_parity.py`，4 passed（两实现 200 步末态相对误差 < 1e-10）。
- 结论（2026-11-08 修订）：**仅"求解器与 BC 采集链路"可跑通，训练主循环未被验证**；"无需重复冒烟"一句作废，正式训练前须重新冒烟确认 RL 循环能进第 1 集。正式训练门槛仍是三列零 RL 全程 `route_completed`。

## 5. 当前开训门槛与阻塞项

| 门槛 | 状态 | 阻塞项 |
|---|---|---|
| 求解器口径定案 | **已定案**（ADR-048） | 旧 checkpoint 源码哈希失效，基线需重跑 |
| 单列 70 km/h 全程零 RL `route_completed` | **已达成** | — |
| 三列全程零 RL `route_completed` | **未达成** | 物理缺口 + 充风门 + 起点条件；工况初速按 ADR-049 下调至 70 km/h 复验 |
| 起点条件规范（初速 < v_max、跟随车 ≥ km0） | 已定案（ADR-049），落地待复验 | — |
| 奖励权重标定 | **暂缓** | 求解器刚定案，权重须在定案口径上重新标定 |

## 6. 仍待决策

1. 三列 70 km/h 全程若仍不通过，是否继续下调初速（65 km/h）或加大初始间距（代价见 ADR-049 备选表）。
2. 奖励速度带中心/半宽是否由固定 `[40,80]` km/h 改为"允许速度减制动距离余量"的动态上缘（现状成因、代码位置与修正方案见本文件第 6 节与 `src/environments/train_fleet_env.py` 的速度带实现）。
3. 训练规模口径：YAML 现行 1400 ep / 36000 步 / n_env 4 / `long_eval_interval 0`，而 `AGENTS.md` 与 `docs/knowledge/RL_TRAINING_EVAL_KNOWLEDGE_BASE.md` 仍为旧值，需统一后再启动正式训练。
