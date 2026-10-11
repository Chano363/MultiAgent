# Tasks

- [ ] Task 1: 根 `AGENTS.md` 文档索引去重为 README 指针
  - [ ] SubTask 1.1: 删除「何时读什么（文档索引）」区的逐条文档清单，改为指向 `traffic_rl_project/docs/README.md`（唯一索引入口）+ `docs/rules/README.md`（规范/模板）的单行指针，保留「校验能力边界」警示
  - [ ] SubTask 1.2: 复核 `docs/README.md`「快速导航」+「核心思想 → 文档映射」已覆盖全部任务触发类型（改 / 建 / 审 / 排障 / 优化）；若缺则补一行，不新建索引文件
  - [ ] SubTask 1.3: 验证 —— `python scripts/check_agents_links.py` exit 0；`audit.py .`（仓库根）无新增违规、AGENTS.md token 数不上升

- [ ] Task 2: P0-① 规则基线 M0 · 53km 完整剖面（现行口径）
  - [ ] SubTask 2.1: 核对 `--mode decompose_m0` 语义（规则基线、不载入 RL 权重）与其可用性
  - [ ] SubTask 2.2: 运行评估（`--grade shuozhou_real_53km --max_steps 36000 --mode decompose_m0 --out_suffix _p0_m0_rule_53km`）
  - [ ] SubTask 2.3: 记录完整命令 / seed / `physics_version`；确认结果 JSON 落盘于 `outputs/results_decompose/`（不覆盖旧文件）

- [ ] Task 3: P0-① RL 基线 M1(`last`) · 53km 完整剖面（现行口径重算）
  - [ ] SubTask 3.1: 锁定与既有 53km 资产同源 ckpt（`outputs/checkpoints_formation/seed0_nep1400/mappo_fleet_last_ep841_dec_ad2_cp_seed0_seed0.pt`），保证与历史可比
  - [ ] SubTask 3.2: 运行评估（`--mode decompose_m1 --grade shuozhou_real_53km --max_steps 36000 --out_suffix _p0_m1_last_53km`）
  - [ ] SubTask 3.3: 记录命令 / seed / `physics_version`；确认落盘不覆盖

- [ ] Task 4: P0-② AB 通道对照 M1 + `--mask_lever ab` · 53km 完整剖面
  - [ ] SubTask 4.1: 用**同 ckpt / 同 seed / 同剖面 / 同步数**，仅追加 `--mask_lever ab` 运行（`--out_suffix _p0_m1_maskab_53km`）
  - [ ] SubTask 4.2: 记录命令 / seed；确认落盘不覆盖
  - [ ] SubTask 4.3: 说明该 mask 的真实语义（RL 完全退出 AB 决策：既不能抑制、也不能提前触发 AB；仅 ED 杠杆生效）

- [ ] Task 5: 汇总三行对比 + 留痕 + ADR 状态更新
  - [ ] SubTask 5.1: 生成对比表（断面力峰值 / 破线（准）车厢·步 / band_rate / 末速 / ab_steps / reward），标注 `physics_version` 与 rollout 模式
  - [ ] SubTask 5.2: 追加 `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md` 小节 `### 诊断-2026-10-01-P0 三行基线（现行口径）`（数据表 + 完整命令 + seed/配置 + 物理/机制解释）
  - [ ] SubTask 5.3: 更新 `docs/logs/decisions/DECISIONS.md` ADR-021 状态行：标注 P0 完成 + **AB 通道净正/净负裁定**（并说明是否触发后续 P1/P2/P3 取舍）
  - [ ] SubTask 5.4: 同步当日流水 `.codebuddy/memory/2026-10-01.md`

# Task Dependencies

- Task 2 / 3 / 4 依赖 Task 1（用户要求"做完之后"再执行）
- Task 5 依赖 Task 2 / 3 / 4 全部完成
- Task 2 / 3 / 4 相互独立、理论上可并行；但本机 GPU/CPU 与 53km 全剖面耗时受限，**按 3 → 4 → 2 串行**执行（先出 RL 两行，规则行最耗时且最稳定，可最后）
- 结论性依赖：P1 / P2 / P3（ADR-021）**不在本次范围**，由 Task 5 的裁定结果决定是否启动