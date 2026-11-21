# MPC_HANDOFF_2026-11-21 · Tube MPC 基线交接（给接手跑 MPC 的人）

> **临时交接文档，阅后即删，仓内同时最多一份。** 接手后把仍生效的结论迁入正式归宿：计划 → `docs/PROJECT_PIPELINE.md` §0.4，决策 → `docs/logs/decisions/DECISIONS.md`，归因 → `docs/logs/diagnostics/`，迁移完成即删，不留档、不追加（git 历史可追溯）。
> 本份取代 `develop` 分支上的 `MPC_HANDOFF_2026-11-14.md`（旧口径，见 §1）。

---

## 0. 交接方式：从 develop 拉，三件套定位

- 从 **`origin/develop`** 拉最新代码（75 口径 MPC 代码已合入 develop；个人分支不互相合并，一律并回 develop）。
- 定位任何文件、产物、结论一律用 **commit 号 + 仓库相对路径 + run_tag** 三件套。
- **禁止绝对路径**：所有路径相对仓库根 `traffic_rl_project/`。不要把任何盘符绝对路径（`X:/...`）写进代码、配置、文档、提交信息或汇报。
  - 你发来的 `F:/列车大创xmc/...`（你本机的仓库副本）和 `D:/Codex/Documents/ref_speed_table(1).npz`（你本机的表）都是**你本机路径**，git 交接后失效——只用来在本机找文件，**不要照抄进仓库**。

## 1. 版本坑（最重要，先读）

| | 老文档（develop 分支） | 现行（ckb-dev，以此为准） |
|---|---|---|
| 参考表口径 | `D_DES = 1434.5` m | **ADR-068 的 75 口径：`D_DES = 1424.7` m** |
| MPC 入口 | 298 行 | 382 行 |
| 交接文档 | `MPC_HANDOFF_2026-11-14.md` | 本份 |

**以 `ckb-dev` 代码为准**，不要照老交接文档里的参数跑。老文档里写的"4 个待修实现层问题"是 2026-11-14 的状态；若 `ckb-dev` 上代码已不同，以代码和现有测试为准，不要用老文档的描述倒推现状。

## 2. 交接物清单（都已在仓库，pull 即有，无需单独传）

| 类别 | 仓库相对路径 |
|---|---|
| 参数 | `src/mpc_baseline/params.py` |
| 求解器 | `src/mpc_baseline/tube_mpc.py` |
| 评估入口 | `src/evaluation/evaluate_mpc_tube.py` |
| 单测 | `tests/test_tube_mpc_baseline.py` |
| 知识库 / 复现报告 | `docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md`、`docs/knowledge/song2026_tubempc_复现报告.md` |
| 参考表生成脚本 | `scripts/gen_ref_speed_table.py` |
| 实验配置（75 口径） | `configs/experiments/formation_ed_ab_3train_1plus108.yaml` |

## 3. 参考速度表：用本机的，但不进 git

- **现行 75 口径表**（相对路径）：`outputs/sim_validation/phys_validation/refspeed_baseline_20261113_095953/ref_speed_table.npz`（417 KB）+ 同目录 `ref_speed_meta.json`。覆盖约 4.3–49.6 km，`v_max = 75 km/h`。你本机那份 `ref_speed_table(1).npz` 若口径一致可直接用；核对 `ref_speed_meta.json` 的 `source_v_max_kmh=75.0`、`pos_max_m≈49601`。
- **不进 git**：仓库 `.gitignore` 第 67 行 `traffic_rl_project/outputs/**/*.npz` 已覆盖所有 npz。不要 `git add -f` 任何 npz，也不要把核对用的 `trajectory.npz` 提交。
- **`v_mps` 已是 m/s，不得再 ×3.6**——v1 就是误乘 3.6 当 m/s 用，参考线 59→212 km/h，整次作废（`tube_v1_20261114/`，旁有 `INVALID_V1_UNIT_BUG.txt`，不要引用）。入口脚本已直读并封顶 75/3.6。
- 若需**再生**：`python scripts/gen_ref_speed_table.py --npz <基线归档trajectory.npz> --out-root outputs/sim_validation/phys_validation`，源是 `fleet3_baseline_vmax75_20261113/trajectory.npz`（235 MB，本地归档，不进 git）。

## 4. 需要你提供的两样（都不阻塞启动）

1. **仓库外的 MPC 改动**：如果你在现有仓库之外继续改过 MPC，只需给 **提交号或代码路径 + 改了哪些参数**（本机看不到你仓库外的改动）。
2. **跑过的核对产物**：若已跑过 MPC，把该次的 `result.json` 和 `trajectory.npz` 发我核对（走网盘/本地传，**不 commit**）。这两样**不是启动运行的前置文件**。

## 5. 运行与验收

```sh
# 从仓库根 traffic_rl_project/ 执行
python src/evaluation/evaluate_mpc_tube.py \
  --out_dir outputs/results/mpc_baseline/<新run_tag> \
  --coupler mt2 --max_steps 31500 --seed 0
```

- `--max_steps 600`（约 50 s）只作冒烟，**不得当峰值或安全判据**；正式出数用全程 31500 步（49.6 km，约 24 min）。
- 完成判据以 **`result.json` 为准**，检查 `summary.full_route == true`。注意：MPC 入口当前**只产 `result.json` + `trajectory.npz` 两件，不产 `intervals.json`**（与通用长跑"三件齐"口径不同）——不要因为缺 `intervals.json` 就判为中断；若后续流程要求第三件，需先改入口脚本再确认。
- metadata 由 `build_metadata` 自动落（mpc 参数 / solve_ms / 场景口径 / 源码 sha256），**不要手改**。
- 长跑（>5 min）用 `schtasks` 独立进程树启动，不要挂在 IDE 终端；判活用 `pgrep` / `ps`，**不看日志末行**。被中断的目录保留并写 `ABORTED_BY_INTERRUPTION.txt`，不得引用。

## 6. 路径与产物规范（红线）

- `--out_dir` 用**新 run_tag**，不要复用历史目录（如 `tube_v1_20261114/`），否则覆写证据。
- 禁止脚本往 `outputs/` 根级落盘。
- 开跑前按 `docs/PROJECT_PIPELINE.md` §0.8.2 训练窗口启动检查单逐项核对并留痕；任一"否"不得开跑。
- 引用数值/文献先查 `docs/REFERENCE_INDEX.md` 与 `docs/VALIDATION_BASELINE.md`；禁止用本项目自己的历史当外部标准。

## 7. 出数后的对照纪律（写作红线）

- 对照 = 未调参规则层基线 + 本 MPC 行 + D-RL；**MPC 行不比车钩**（ADR-033/034 显式关车钩约束，只主张编队指标：列距保持 / 速度带）。
- 引用任何"更优"必须并列代价口径（ATP 触发、速度带）。
- 三方同物理同场景（主仓 49.6 km / 10 988 t / 4 300 m 起点 / 60 km/h 初速 / 75 口径 ADR-068），同源性自动成立。
- 读数跨机器不可互引；形态量（哪列承压）跨机器会翻转，判据靶子用后果量（peak / 超限步）。
