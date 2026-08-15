# AGENTS.md

## Repo layout

根目录下有两个独立包：

- **`traffic_rl_project/`** — 实际的研究项目（**当前主战场**）。两阶段递进式 RL 研究：
  - 阶段一：无人机编队控制（已完成，历史成果）
  - 阶段二：**重载列车群组协同控制（进行中，核心工作）**
- **`gym_pybullet_drones/`** — 阶段一无人机仿真器的上游 fork（quadcopter 物理仿真）。阶段二列车项目**不再依赖**它，但保留作为阶段一成果的依赖。

## Environment

WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU。
Python、conda、WSL 已装，不要重装。

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
```

- 网络访问/下载用 **Windows PowerShell**（不是 WSL）。
- Windows Anaconda 位于 `D:\Anaconda\python.exe`（用于 CodeBuddy 原生调用 MCP 等）。

## Key commands

```sh
# 阶段二列车动力学/环境测试（69 个测试）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python -m pytest tests/ -q

# 阶段二 MAPPO 训练（长大下坡 + 万吨级 1+0）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/trainer/train_train.py --episodes 500 --preset 10kt_1plus0 --grade long_downhill

# 阶段一无人机训练（历史命令，MAPPO 唯一收敛）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/main.py --mode train --algorithm MAPPO --episodes 500

# gym-pybullet-drones 测试（阶段一）
cd /mnt/d/Code/MultiAgent/gym_pybullet_drones
pytest tests/
```

无 linter/typechecker/formatter 配置。遵循 PEP 8。

## 阶段二研究定位（重要）

**论文题目**：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法
**研究对象**：一万吨级 1+0 重载列车群组（单机牵引万吨列车，1机+~100节货车，群组由多列组成）

**核心创新点：车钩力 + 多列群组 + 长大下坡 分层（Hierarchical）MARL**。

现有长大下坡 RL 工作（Zhang2024 DQN、Liu2021 DDQN、Wang2025 DQN）**均明确忽略车钩力**；
本项目在长大下坡循环制动场景下**显式建模车钩力**，并扩展到多列群组协同。
自动控制 = MARL 训练出的控制器本身（无额外底层控制器）。

分层框架：
```
层级一（多列群组）: 每列万吨级列车=智能体, 安全间距约束, 生成宏观驾驶曲线
层级二（单列车厢级）: 每节车厢=智能体, 车钩力≤1000kN (ATP安全层), 跟随曲线
```

详见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md`。

## 阶段二当前进度

| 子任务 | 状态 |
|:--|:--|
| P0 列车动力学 Gym 环境（`train_env.py` + `train_dynamics/`） | ✅ 完成 |
| P0.5 仿真升级：电制动/空气制动波速传播/ATP 安全层/车钩力指标 | ✅ 完成（54 测试） |
| P0.5 研究定位 + 文献库搭建（docs/papers/） | ✅ 完成 |
| P0.75 验证基准：提取 6 篇论文数据 + coupler 间隙死区 + 多源制动 + 紧急制动上限 | ✅ 完成（54 测试通过） |
| P1 第9条 环境验证：修复 Davis 阻力 bug + 验证 20m/s 可达 | ✅ 完成（65 测试通过） |
| **P1.5 题目对齐前置**：长大下坡变坡剖面 + 万吨级 1+0 编组 + Zhang2024 验证基准 | ✅ 完成（65 测试通过） |
| P1 第15条 MAPPO 迁移到列车（train_train.py）+ 冒烟/短训验证 | ✅ 完成（69 测试通过） |
| P1 第16条 正式基线训练（长大下坡循环制动自动控制） | ⬜ |
| P2 奖励消融/多算法对比/阶段二报告 | ⬜ |
| P3 层级一（多列群组）环境 + 对比实验 | ⬜ |

## 阶段二列车仿真设计

**动力学**（`src/train_dynamics/`，NeTrainSim 公式 + 多体扩展）：
- 多体积分器 `train.py`：每车独立质点，受力 = 牵引 − 制动 − Davis阻力 ± 坡度 + 车钩力；空气制动支持**双向传播 + 多源制动**（`ab_sources`，分布式动力/尾部动力）
- **制动** `braking.py`：
  - **电制动（ED）**：连续可调，仅机车，功率+粘着约束
  - **空气制动（AB）**：离散档位（RELEASE/MIN/SERVICE/EMERGENCY），**沿车列按制动波速向后传播**（常用 200m/s、紧急 250m/s）——纵向冲动的主要物理来源
- **车钩力** `coupler.py`：质量-弹簧-阻尼 + **车钩间隙死区**（`_dead_zone`，`CouplerParams.coupler_gap_m` 默认 0.01m），复现杨敏"间隙→车钩力"规律，牛顿第三定律成对抵消
- **坡度剖面** `grade_profile.py`：`GradeProfile` 分段剖面 + 3 种预置（樊运新：长大下坡-10.2‰/缓坡变陡坡/V型坡），每步按车辆位置实时更新坡度

**环境**（`src/environments/train_env.py`，`TrainFormationEnv`）：
- 状态（每车 4 维）：速度误差、与前车间距误差、车钩力、位置
- 动作（每车 1 维）：throttle ∈ [-1,1]，>0 牵引（仅机车）、<0 制动
- **编组预设**：`consist_preset: '10kt_1plus0'`（1机+100货=10188t，论文研究对象）或 `default`
- **坡度剖面**：`grade_profile: 'long_downhill'/'gradual_to_steep'/'v_shape'`（长大下坡场景）
- 奖励：−0.5·速度误差 − 0.3·间距误差 − 0.15·平均冲动 − 0.15·峰值冲动 + 超限惩罚

**安全层**（`src/safety_layer.py`，`SafetyLayer`）：
- 规则式 ATP：限速、车钩力上限（**正常运行 1000kN / 紧急制动 2250kN**，Fu2019）、列车间距下限
- 在动作喂给动力学前修正，纯规则无学习参数
- 后续可叠加 CBF（QP 求解）做理论对标

## Gotchas（会坑你）

| 问题 | 解决 |
|---|---|
| YAML `3e-4` 解析成字符串 | 用十进制：`0.0003` |
| Action dim mismatch | 环境交互 reshape `(num_drones,4)`；transition 存储拉平 12 维（阶段一遗留） |
| Loss 恒 0 | 确保 `batch_size ≤ n_steps`，否则 buffer 永远不满 |
| INFO 日志不打印 | 脚本入口 `logging.basicConfig(level=logging.INFO)` |
| **Davis 阻力被放大 w 倍** | 空气阻力必须是标准 Davis 形式 `0.0018*C*A*V²`（独立于车重），不能 `area*cd*v²/w` 再乘 w（会把阻力放大数百倍，平衡速度被低估到 8m/s，20m/s 不可达）。已修复（见 VALIDATION_BASELINE V2） |
| **制动传播被 dt 吞掉** | 传播延迟按**车辆累计长度/波速**算（真实重载数百米→数秒延迟），不要用车钩 free_length |
| **安全层修正 → log_prob 失配 → 策略发散** | SafetyLayer 修正动作后必须用**实际执行动作**重算 log_prob 存储（`info['executed_actions']` + `agent.get_log_prob`），否则重要性采样失效，viol 每 10ep 爆 85 倍（V5.1 三层 bug 链之一） |
| **value_loss 爆炸 → 阈值误杀** | 多智能体累计 returns ~1e4-1e5，value 网络初始输出 0 → value_loss ~1e8 → 用 ValueNorm（PopArt）归一化 value 目标，不要用 `total_loss>1000` 硬编码阈值 |
| **mcp 2.0 崩溃** | scholar-search-mcp 需 `mcp==1.9.3`（2.0 移除 `@app.list_tools`） |
| **程序化下载论文被 403** | MDPI/Wiley/IEEE/Hindawi 反爬，开放获取论文用浏览器手动下载（见 `docs/PAPER_DOWNLOAD_LINKS.md`） |
| 网络下载 | 用 Windows PowerShell，别用 WSL |

## Algorithm status（阶段一结论，阶段二复用）

- **MAPPO**：唯一收敛算法（无人机 Best Reward 235.5），**迁移到列车复用**
- SAC：后期退化；PPO：不稳定；DQN：未验证

## Config files

- `traffic_rl_project/configs/train_config.yaml` — 每算法超参数（`training.hyperparameters.<algo>`，MAPPO 起步 `lr=5e-5, entropy=0.005`）
- `traffic_rl_project/configs/env_config.yaml` — 环境参数（阶段一 num_drones 为主）
- `traffic_rl_project/configs/agent_lightning_config.yaml` — Agent Lightning 优化配置（阶段一）

YAML `.get()` 路径需与 YAML 结构严格匹配，否则静默回退默认值。

## Project docs（按阅读优先级）

- `traffic_rl_project/docs/PROJECT_PIPELINE.md` — **pipeline 总览 + 任务列表（P0/P1/P2/P3，已完成的✅保留不删）+ 下一步，先读这个**
- `traffic_rl_project/docs/RESEARCH_POSITIONING.md` — **阶段二研究定位 + 创新点 + 文献库（20+ 论文）**
- `traffic_rl_project/docs/VALIDATION_BASELINE.md` — **论文→项目正确性验证基准**（仿真器公式/数据/算法对照，P1 前必读）
- `traffic_rl_project/docs/learning_report.md` — 阶段一完整技术报告
- `traffic_rl_project/docs/training_results_standardized.md` — 阶段一学术成果报告
- `traffic_rl_project/docs/PAPER_DOWNLOAD_LINKS.md` — 开放获取论文手动下载网址
- `traffic_rl_project/docs/MCP_DEPLOYMENT.md` — scholar-search-mcp 部署说明
- `.learnings/LEARNINGS.md` — 踩坑记录

## 文献库（docs/papers/）

**论文的双重用途**：既是文献引用，更是**项目正确性的验证基准**（见 `docs/VALIDATION_BASELINE.md`）——
- 仿真器公式/数据对照：Zhang2025（制动减压-压钩力）、杨敏（车钩间隙-车钩力）、樊运新（编组-冲动）、Tang2020（车钩力建模）、Fu2019（钩缓约束）
- 算法对照：Tang2020（多目标奖励）、Wang DQN（纵向冲动降幅基准）、Li CBF（安全层强化）、魏咪（分层框架）

- **PDF（10 篇）**：Tang 2020（多机车 RL+车钩力）、Fu 2019（钩缓约束）、Huang 2025（专家系统+DRL）、Zhang 2025（20kT 制动）、Heineken 2023（最优控制节能）、Yang 2024（蚁群节能）、Guo 2025（MARL 车队）、魏咪（车钩力分层）、樊运新（3万吨纵向冲动）、杨敏（车钩间隙）
- **arXiv 源码（3 篇）**：2504.19480（LLM 奖励设计）、2003.03327（智能列车运行）、2312.06858_full（车队 MARL）
- **MCP**：`scholar-search` 已配置（Semantic Scholar + arXiv 双通道），详见 `docs/MCP_DEPLOYMENT.md`

## Code conventions

- PEP 8
- 训练脚本入口配置 logging
- 临时脚本用后即删
- 检查点定期保存；只使用专业仿真器，禁止 mock 环境
- **`.codebuddy/mcp.json` 已 gitignore**（含 API key，勿提交）
