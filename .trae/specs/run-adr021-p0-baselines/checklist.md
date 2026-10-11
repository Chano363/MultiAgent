# Checklist

## Task 1 — AGENTS.md 索引去重

- [ ] 根 `AGENTS.md` 的「文档索引」区不再含逐条 `docs/...` 文件清单，仅指向 `docs/README.md`（+ `docs/rules/README.md`）
- [ ] 「校验能力边界」警示仍在 `AGENTS.md`（未被误删）
- [ ] `python scripts/check_agents_links.py` → exit 0
- [ ] `docs/README.md` 未被新建重复索引文件取代，仍是唯一索引入口

## Task 2/3/4 — P0 三行基线

- [ ] `outputs/results_decompose/` 下存在三份新结果 JSON（M0 / M1 last / M1 mask-ab），文件名含 `_53km`
- [ ] 三份 JSON 均含 `metadata.physics_version` 与**逐列明细**（`per_train` / `per_seed`）
- [ ] 三行使用**同一剖面**（`shuozhou_real_53km`）、**同一 `max_steps`**、**同一 `eval_seed`**，仅自变量不同
- [ ] 三行均按 `build_metadata` 内嵌 metadata（符合 `docs/rules/EXECUTION_RULES.md` 强制要求）
- [ ] **未覆盖**任何既有结果 JSON（`eval_decompose_decompose_m1_ms36000_*_53km.json` 等原文件仍在）
- [ ] 每条命令、seed、剖面、`physics_version` 已完整记录

## Task 5 — 留痕与决策闭环

- [ ] `DIAGNOSTICS_2026-10.md` 追加 `### 诊断-2026-10-01-P0 三行基线（现行口径）`，含数据表 + 完整复现命令 + seed/配置 + 物理/机制解释
- [ ] 该小节明确标注 **rollout 模式**（确定性驱动）与 `physics_version`，并说明 `--mask_lever ab` 的真实语义（RL 完全退出 AB 决策）
- [ ] `DECISIONS.md` ADR-021 状态行标注 **P0 完成** + **AB 通道净正/净负裁定**
- [ ] 若裁定与 ADR-020/021 既有表述冲突，已在**原位**追加"更正/修订"行（不覆写历史）
- [ ] `.codebuddy/memory/2026-10-01.md` 已同步
- [ ] 未改动任何物理 / 算法代码（`git status` 中 `src/` 无本次新增改动）

## 边界（不得越界）

- [ ] **未启动** P1 / P2 / P3（AB 最小充风时间 / per-agent advantage / 车钩力进目标 or safety filter）——须由 P0 裁定后再定
- [ ] 未对 append-only 日志做历史改写（仅追加小节）