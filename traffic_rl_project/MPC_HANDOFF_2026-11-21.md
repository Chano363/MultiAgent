# MPC_HANDOFF_2026-11-21 · Tube MPC 基线交接（给接手跑 MPC 的人）

> **临时交接文档，阅后即删，仓内同时最多一份。** 接手后把仍生效的结论迁入正式归宿：计划 → `docs/PROJECT_PIPELINE.md` §0.4，决策 → `docs/logs/decisions/DECISIONS.md`，归因 → `docs/logs/diagnostics/`，迁移完成即删，不留档、不追加（git 历史可追溯）。
> 本份取代 `develop` 分支上的 `MPC_HANDOFF_2026-11-14.md`（旧口径，见 §1）。

---

## 0. 交接方式：从 develop 拉，三件套定位

- 从 **`origin/develop`** 拉最新代码（75 口径 MPC 代码已合入 develop；个人分支不互相合并，一律并回 develop）。
- 定位任何文件、产物、结论一律用 **commit 号 + 仓库相对路径 + run_tag** 三件套。
- **禁止绝对路径**：所有路径相对仓库根 `traffic_rl_project/`。不要把任何盘符绝对路径（`X:/...`）写进代码、配置、文档、提交信息或汇报。
  - 你发来的 `F:/列车大创xmc/...`（你的仓库副本）和 `D:/Codex/Documents/ref_speed_table(1).npz`（我之前已经给你的表，就在你本机）都是**你本机路径**——git 交接后在别人机器上无效，只用来在本机找文件，**不要照抄进代码/配置/文档**。

## 1. 版本坑（最重要，先读）

你手里的旧 `MPC_HANDOFF_2026-11-14.md`（旧口径）对应的代码已过时。**一切以你从 `origin/develop` pull 下来的代码为准**——75 口径的改动已合入 develop，develop 与 ckb-dev 内容一致，不用再纠结分支。

| | 旧文档（11-14，已过时） | 现行（develop / ckb-dev，一致） |
|---|---|---|
| 期望头距 | `D_DES = 1434.5` m | **ADR-068 的 75 口径：`D_DES = 1424.7` m** |
| MPC 入口 | 298 行 | 382 行 |
| 交接文档 | `MPC_HANDOFF_2026-11-14.md` | 本份 |

老文档里写的"4 个待修实现层问题"是 2026-11-14 的状态；以你 pull 下来的代码和现有测试为准，不要用老文档的描述倒推现状。

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

## 3. 参考速度表：你手里已经有了，放到脚本期望的路径即可

- **你已经在手**：我之前给你的 `ref_speed_table(1).npz`（你本机 `D:/Codex/Documents/`，覆盖约 4.3–49.6 km、75 km/h）就是现行的 75 口径表。**不需要我再给你，也不需要你重新生成**——手里这份直接可用。
- **你唯一要做的动作**：入口脚本 `src/evaluation/evaluate_mpc_tube.py` 第 153 行硬编码从仓库相对路径 `outputs/sim_validation/phys_validation/refspeed_baseline_20261113_095953/ref_speed_table.npz` 加载表；这个 npz 被 `.gitignore` 排除、不随 git 分发，所以你 pull 完代码后该路径下是空的。把你手里那份**复制并改名为 `ref_speed_table.npz`**，放到上述路径（相对仓库根 `traffic_rl_project/`）即可开跑。
- **不要提交 npz**：仓库 `.gitignore` 第 67 行 `traffic_rl_project/outputs/**/*.npz` 已覆盖，别 `git add -f`；你跑出的核对产物 `trajectory.npz` 同样不 commit。
- **口径自检**：表内 `v_mps` 已是 m/s（上限 75/3.6），**不得再乘 3.6**——v1 曾误乘 3.6 使参考线 59→212 km/h、整次作废（`tube_v1_20261114/`，不要引用）。入口脚本已直读并封顶。
- **兜底（仅当手里那份丢失）**：若你本地另有基线归档 `fleet3_baseline_vmax75_20261113/trajectory.npz`，可用仓库里的 `python scripts/gen_ref_speed_table.py --npz <归档trajectory.npz> --out-root outputs/sim_validation/phys_validation` 再生；但 235 MB 的源归档不进 git，正常情况下用不上这条。

## 4. 你不需要先给我任何东西

- **启动运行无前置文件**：你不需要先向我提供 `result.json`、`trajectory.npz` 或任何文件就能开跑。
- **反而是我给你的**（都不是启动前置）：
  - 若我在现有仓库之外改过 MPC，我会把**提交号或代码路径 + 改了哪些参数**发你；
  - 若我之前跑过 MPC，我会把那次的 `result.json` + `trajectory.npz` 发你用于核对。
- 交接方向是**我 → 你**。你要做的只有三件事：从 develop pull 代码（§0）、把手里的表放到脚本期望的路径（§3）、按 §5 跑。

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
