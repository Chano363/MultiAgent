# AGENTS.md

> **本文件 = 导航 + 立论指针入口**（不承载进度表、不复制研究阶段细节）。
> 环境/训练/留痕等**执行规范**见 `traffic_rl_project/docs/rules/EXECUTION_RULES.md`；进度流水见 `traffic_rl_project/docs/PROJECT_PIPELINE.md`；仿真设计/Gotchas/文献清单等细节已下沉到 `docs/`（见下方「何时读什么」）。

## Repo layout

- **`traffic_rl_project/`** — 实际研究项目（**当前主战场**）。两阶段递进式 RL 研究：
  - 阶段一：无人机编队控制（已完成，历史成果，其仿真器依赖已移除）
  - 阶段二：**重载列车群组协同控制（进行中，核心工作）**

## Environment

WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU。Python、conda、WSL 已装，**不要重装**。

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
```

- 网络访问/下载用 **Windows PowerShell**（不是 WSL）。
- Windows Anaconda 位于 `D:\Anaconda\python.exe`（用于原生调用 MCP 等）。

## Key commands

```sh
# 阶段二列车动力学/环境测试
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python -m pytest tests/ -q

# 阶段二主训练（53km，formation-aware 机车级 ED/AB；YAML 已按 ADR-017 达标：1400 ep / n_env 4 / BC 热启动 / long_eval）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed {0..4}

# 调试/冒烟（勿改 YAML 主值；必须同时重定向三个输出目录，否则会覆写历史产物 → LRN-20261001-009）
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 2 \
  --checkpoint_dir outputs/_smoke/ckpt --results_dir outputs/_smoke/results --override dirs.figures_dir=outputs/_smoke/figures
```

无 linter/typechecker/formatter 配置。遵循 PEP 8。

## 阶段二研究定位（立论主轴）

**论文题目**：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法
**研究对象**：一万吨级 1+1 重载列车群组（单机牵引万吨列车，1 机 + \~100 节货车，群组由多列组成）

**核心创新点：车钩力 + 多列群组 + 长大下坡 协同控制**（编队 = 最终目的，MARL = 实现手段）。现有长大下坡 RL 工作（Zhang2024 DQN、Liu2021 DDQN、Wang2025 DQN）**均明确忽略车钩力**（⚠️ 仅指这些单列、车钩力未入模者，**勿推广为"文献都忽略"**——Wang2026 单列重载 RL 已含车钩力、Song2026 多列 Tube-MPC 已含车钩力约束，见 `RESEARCH_POSITIONING.md` §1.2 / ADR-030；真空白 = "多列群组 × 车钩力 × MARL"）；本项目在长大下坡循环制动场景下**显式建模车钩力**，并扩展到多列群组协同。实现方式（2026-09-08 ADR-013）= **RL 定策 + 底层控制器安全执行**（非纯 RL 直控 100 车厢）。

> **⚠️ 主轴与 RL 落位（ADR-013，铁律）**：论文**最终目的是"编队"**（多列群组长大下坡保持安全列距 + 速度带一致 + 车钩力 ≤1000 kN）；MARL 只是手段。**仅保留一套 formation-aware RL = 机车级 ED/AB 分工**（每台机车 = 智能体，ED 连续 / AB 离散档位，以编队为上下文）；底层由列内规则循环制动 + 车钩力安全层确定性执行。**废止**"编队层 RL + 列内层 RL 两层叠加 = T-MARL"（ADR-012→013）。

```
编队目标（最终目的，非 RL）: 多列群组长大下坡协同（安全列距 + 速度带一致 + 车钩力≤1000kN）
       ↓ 由同一套 RL 承载（编队上下文）
RL 落位（唯一手段）: 机车级 ED/AB 分工，每台机车=智能体（ED 连续 / AB 离散档位）
       ↓ 目标速度/档位
底层执行（确定性）: 列内规则循环制动 + 车钩力安全层（enforce_coupler≤1000kN）
```

**立论 SSOT**：`docs/RESEARCH_POSITIONING.md` §1.3 / §1.3.1 / §1.5 / §1.6。

## 规范性问题（对比 / 立论铁律）

> **权威出处（SSOT）**：立论细节只认 `traffic_rl_project/docs/RESEARCH_POSITIONING.md` §1.5/§1.6 + `docs/logs/decisions/DECISIONS.md`（ADR 为准，截至 **2026-10-02** 最新为 **ADR-023**；具体覆盖关系与编号清单以 `DECISIONS.md` 为准，勿从本文件推断）；**勿从本文件/旧版本妄猜规范**——本文件只放要点指针。
> 原则：先想清楚"哪些不可让、哪些才叫卖点、MPC 怎么比才不失公允"，再写论文/做消融/加对比。
> **文档规范出处**：文档治理/角色/三态/判断树 = `docs/README.md` + `docs/rules/README.md`（唯一规范）。

- **主轴**：多列编队 + 队内车钩力 ≤1000 kN + 安全列距 = 不可逾越底线；AB+ED 分工、1+1 = 锦上添花（不当主线）。
- **MPC 对比只留 Regime A**（ADR-016，B 已废止）：不按坡道换 MPC 模型；MPC 逐线重喂该线 `grade_at` 图纸 + 在线标定 b0（公平标定），D-RL 跨线严格零微调。立论 = **"免重辨识成本"**（零重标定代价的 MARL ≈ 逐线重标定后的 MPC）；不再提供"MPC 不重辨识失配"论证。Protocol 逐实验标 A。**MPC 基线唯一 = `NMPCController`**（ADR-022：旧 `FairMPCController`/简化 MPC 已删除；主表显式 `--mpc_type nmpc`，历史 MPC 数值作废）。
- **车钩异构（E4-H）【SUPERSEDED，不承担立论】**：主 claim 只押"免重辨识成本"；`--hetero` 仅作可选鲁棒性（默认齐次零回归），不进正文主表。
- **训练/评估时域**（ADR-017，铁律）：三条独立维度不可混——① 单条 rollout 时域（on-policy 窗口）② 评估时域（覆盖剖面）③ 总训练量（episodes 预算）。**训练 = 短窗口；评估 = 独立完整剖面单独跑（非"多段拼接"）**；跨线方向 = 长复杂剖面训 → 未见过剖面验。**具体数值见 ADR-017，勿在本文件复制以免随 SSOT 漂移。**
- **车钩力定位**（ADR-014，**已由 ADR-021 决策 2 修订并落地执行**）：硬安全层（≤1000 kN）+ 观测上下文 + 安全层；**不作均值最小化对象**。现允许**受控的"超限"非线性项**进目标（`-6.0·min(peak_norm−1, 2.0)`，上界 −12；仅在 `peak_norm>1` 生效；仍不作均值最小化、安全叙事不归功于 MARL）——落地与量级核对见 `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「改造-2026-10-01」四、。指标口径 SSOT = `coupler_interface_forces()`（断面力，ADR-018）。

## 列车仿真设计（指针）

- 动力学 `src/train_dynamics/`（多体 `train.py` / 制动 `braking.py`：ED 连续 + AB 离散档位沿波速传播 / 车钩 `coupler.py`：MT-2 / 坡度 `grade_profile.py`）；环境 `src/environments/train_env.py`（`TrainFormationEnv`）；安全层 `src/safety_layer.py`（规则式 ATP）。
- **设计明细 + 引擎 Gotchas 见 `docs/VALIDATION_BASELINE.md` 附录 A / 附录 B**（2026-10-01 自本文件下沉，零内容丢失）。
- 关键铁律：**[ADR-011] 车钩统一 MT-2**（QKX100 已移除）；**[ADR-018] 指标口径 = 断面力**；**只使用专业仿真器，禁止 mock 环境**。

## Config files

- `traffic_rl_project/configs/experiments/formation_ed_ab_3train_1plus1.yaml` — **主训练配置**（formation-aware 机车级 ED/AB，3 列×1+1=6 agent，53km，curriculum 上限 1200 步）
- YAML `.get()` 路径需与 YAML 结构严格匹配，否则静默回退默认值（YAML 禁科学计数法，用 `0.0003`）。

## Code conventions

- PEP 8；训练脚本入口配置 `logging.basicConfig(level=logging.INFO)`。
- 临时脚本用后即删；检查点定期保存。
- **训练/评估必须落权威 metadata**（强制，见 `docs/rules/EXECUTION_RULES.md`）：训练走统一框架 `run_training.py`（`training_metadata_guard`）或 legacy 入口 `train_fleet` / `train_cyclic_braking`（`save_metadata`+`assert`）；评估用 `build_metadata` 内嵌结果 JSON 并时间戳归档。**不进此路径的结论不认可、不得引用。**
- **`.codebuddy/mcp.json` 已 gitignore**（含 API key，勿提交）。
- **产物目录（`outputs/`）规范**：按**产物类型**分组（checkpoints / results / figures / logs / sim_validation / smoke / deprecated），运行目录命名 = **语义前缀_时间戳**（禁裸 `run_<stamp>`）；**禁止脚本往 `outputs/` 根级或任意 cwd 落盘**。全文（含 R1–R6 与迁移表）见 `docs/rules/EXECUTION_RULES.md`「产物目录规范（outputs/ 布局）」。

## 生图规范（图表 / 曲线）

> 目的：图可复现、可重画、不误导；**改样式不重跑仿真**。全文见 `docs/rules/EXECUTION_RULES.md`「生图规范（图表 / 曲线）」。

- **数据与绘图分离（铁律）**：生图脚本必须能从**已归档数据**直接重画，**默认复用、不重跑仿真**；仅显式 `--source new`（或等价开关）时才重新仿真并新建归档。仿真数据缺失才允许重算，且**补存缺失数据**以便下次复用。
- **落盘二分**：**图 → 策展目录** `outputs/sim_validation/figures/<主题>/`（允许覆盖）；**原始数据 → 时间戳归档** `outputs/sim_validation/phys_validation/<语义前缀_时间戳>/`（不覆盖）。**禁止**为"只改样式"另建目录；选归档只认**真正含数据**的目录（**不可只看名字最新**）。
- **图内文字一律英文**（图题 / 轴标签 / 图例 / 注释 / colorbar），中文只留在代码注释与日志。**标题**用陈述式短语，**禁用** `vs`、斜杠堆术语、`A → B → C` 箭头串、中英混排（比较用 `A under B` / `A and B`）。
- **轴标签必须写明物理量 + 单位**（如 `Coupler force (kN)`、`Speed (km/h)`），位置轴写清含义；长轴用稀疏刻度；状态/色标给可读语义（如 `Air brake state (1 = applied)`）。
- 车钩力一律用**每车钩断面力（kN）**口径（ADR-018），安全线 1000 kN。

## 修改 / 追加文档方法论（强，Docs-as-Code）

> 目标：文档不膨胀、不误导、SSOT 不破坏。**日志类一律 append-only。**

**4 条判断规则（改/增前先问）**

1. **属于哪个角色？** 实验/诊断 → `logs/diagnostics/`（按月文件）；重大决策 → `logs/decisions/DECISIONS.md`（ADR）；踩坑/教训 → `logs/learnings/LEARNINGS.md`；工作计划 → `PROJECT_PIPELINE.md`；流水 → `.codebuddy/memory/`。判断树见 `docs/rules/README.md` 第四节。
2. **核心立论 vs 流水？** 立论（RESEARCH_POSITIONING / 论文 / 规范）可**覆盖式修订**（动机存档进 ADR）；流水**只追加**，历史结论绝不篡改，被推翻就在原位标 `superseded` 并指向新结果。
3. **文件会不会过大？** 单文件接近 ~200KB 必须按 `类型/时间` **物理拆分**（如 `DIAGNOSTICS_YYYY-MM.md`、`VERIFICATION_LOGS_V*.md`）；**删除文档不留 stub，一次性 Grep 全仓改写所有旧路径**。
4. **导航是否登记？** 新建/移动/拆分任何文档必须同步 `docs/README.md`（唯一索引入口），用 Grep 全仓改旧路径指向现存文件。

**日志类纪律**：文件末尾加 `### 小节-日期`；保留全部历史，不覆盖、不删除既有行。**禁止**为不存在的文档建空白占位页。

**反冗余三铁律**：① **孤儿文件即删**（无索引 + 字节相同 + 零引用）；② **构建垃圾进 `.gitignore`**（`*.aux` / `*.log` / `tmp_*`）；③ **备份可用 git 历史替代**（曾被提交且仍为 SSOT 的原始大文件绝不可删，可删的是拆分/改版时复制的临时快照）。

## 文献库（docs/papers/）

**论文双重用途**：既是文献引用，更是**项目正确性的验证基准**（见 `docs/VALIDATION_BASELINE.md`）。PDF（10 篇）+ arXiv 源码（3 篇）+ 信息卡全清单见 `docs/papers/` 与 `docs/RESEARCH_POSITIONING.md` §二。MCP `scholar-search` 已配置（Semantic Scholar + arXiv 双通道；需 `mcp==1.9.3`）。

- **从文献学到的经验必须登记引用文档**：凡从论文借鉴的思想 / 公式 / 设计 / 数据，或决策（ADR）/ 诊断调研中**据以定案**的文献解法，一律写入 `docs/REFERENCE_INDEX.md`（技术/公式 → 来源 → 本地文件 / DOI），禁止"用了不注明"；新增引用同步 `docs/papers/` + `refs.bib` + 该表（三处）。未核实到 DOI 的只给 venue/年份，不编号。

## 证据使用纪律（大经验）

> 目的：不拿二手当一手、不把已决当待定、不拿推断冒充事实。

1. **一手优先**：来源 / 口径 / 是否已决策，一律回一手核实 —— `docs/papers/` **实际文件清单**、`DECISIONS.md`、`RESEARCH_POSITIONING.md`。**索引/二手记录（含 `REFERENCE_INDEX` 的"无本地"）不得当终结论**。
2. **先读已定稿再开口**：SSOT + ADR + 已给结论是**硬约束**，先过一遍；**不把已决策的事当"待定"重提**（要提，先拿出推翻它的证据）。
3. **检索无命中 ≠ 不存在**：Grep 未命中时改用 Glob / LS **列目录确认**，再下结论。
4. **分清"明写"与"推断"**：只有文档明写的用于下结论；推断必须标为推断，禁止冒充事实。
5. **两侧物理同源**：训练 / 评估 / 对比基线必须共用**同一物理模型**；禁止"一边改物理、一边做对比"。

## 何时读什么（文档索引）

> 找任何文档先看 `traffic_rl_project/docs/README.md`（**唯一索引入口**：快速导航 + 核心思想→文档映射，覆盖 改/建/审/排障/优化 全部任务触发）。
> 文档规范 / 角色 / 模板 / 判断树 → `traffic_rl_project/docs/rules/README.md`。
> 各文档的「何时读」条件已由 README 承载，本文件不再复制清单。

> **⚠️ 校验能力边界（勿当万灵药）**：`scripts/check_agents_links.py`（见 `docs/rules/EXECUTION_RULES.md`）只保证**引用卫生**（ADR 编号存在 / docs 路径非断链 / 个别数值内联警示），**不保证**内容规范、不误导、不循环论证。三者分别靠：① 内容规范 = ADR review + 人审（机器查不了语义）；② 防误导 = 写前追问"这是流水还是立论、措辞是否含糊、推测是否写成结论"；③ **防循环论证 = 引用必须锚定外部独立权威**（原始论文 / DOI / 领域公认），**禁止用"本项目自己的历史"当作"外部标准证明"**。**请勿因存在校验而省略 ①②③ 的人工判断。**