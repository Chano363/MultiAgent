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
# 阶段二列车动力学/环境测试（40 个测试）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python -m pytest tests/ -q

# 阶段一无人机训练（历史命令，MAPPO 唯一收敛）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/main.py --mode train --algorithm MAPPO --episodes 500

# gym-pybullet-drones 测试（阶段一）
cd /mnt/d/Code/MultiAgent/gym_pybullet_drones
pytest tests/
```

无 linter/typechecker/formatter 配置。遵循 PEP 8。

## 阶段二研究定位（重要）

**核心创新点：车钩力 + 多列群组 分层（Hierarchical）MARL**。

现有工作要么"多列群组但简化掉车钩力"（虚拟耦合 VCTS），要么"有车钩力但只做单列"。
本项目把两者结合：单列车厢级（车钩力 ≤ 1000kN）+ 多列群组级（安全间距），并论证"群组控制不能忽略车钩力"。

分层框架：
```
层级一（多列群组）: 每列列车=智能体, 安全间距约束, 生成宏观驾驶曲线
层级二（单列车厢级）: 每节车厢=智能体, 车钩力≤1000kN (ATP安全层), 跟随曲线
```

详见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md`。

## 阶段二当前进度

| 子任务 | 状态 |
|:--|:--|
| P0 列车动力学 Gym 环境（`train_env.py` + `train_dynamics/`） | ✅ 完成 |
| P0.5 仿真升级：电制动/空气制动波速传播/ATP 安全层/车钩力指标 | ✅ 完成（40 测试） |
| P0.5 研究定位 + 文献库搭建（docs/papers/） | ✅ 完成 |
| P1 MAPPO 迁移 + 基线训练 | ⬜ 下一步 |
| P2 奖励消融/多算法对比/阶段二报告 | ⬜ |
| P3 层级一（多列群组）环境 + 对比实验 | ⬜ |

## 阶段二列车仿真设计

**动力学**（`src/train_dynamics/`，NeTrainSim 公式 + 多体扩展）：
- 多体积分器 `train.py`：每车独立质点，受力 = 牵引 − 制动 − Davis阻力 ± 坡度 + 车钩力
- **制动** `braking.py`：
  - **电制动（ED）**：连续可调，仅机车，功率+粘着约束
  - **空气制动（AB）**：离散档位（RELEASE/MIN/SERVICE/EMERGENCY），**沿车列按制动波速向后传播**（常用 200m/s、紧急 250m/s）——纵向冲动的主要物理来源
- **车钩力** `coupler.py`：质量-弹簧-阻尼，牛顿第三定律成对抵消

**环境**（`src/environments/train_env.py`，`TrainFormationEnv`）：
- 状态（每车 4 维）：速度误差、与前车间距误差、车钩力、位置
- 动作（每车 1 维）：throttle ∈ [-1,1]，>0 牵引（仅机车）、<0 制动
- 奖励：−0.5·速度误差 − 0.3·间距误差 − 0.15·平均冲动 − 0.15·峰值冲动 + 超限惩罚

**安全层**（`src/safety_layer.py`，`SafetyLayer`）：
- 规则式 ATP：限速、车钩力 ≤ 1000kN、列车间距下限
- 在动作喂给动力学前修正，纯规则无学习参数
- 后续可叠加 CBF（QP 求解）做理论对标

## Gotchas（会坑你）

| 问题 | 解决 |
|---|---|
| YAML `3e-4` 解析成字符串 | 用十进制：`0.0003` |
| Action dim mismatch | 环境交互 reshape `(num_drones,4)`；transition 存储拉平 12 维（阶段一遗留） |
| Loss 恒 0 | 确保 `batch_size ≤ n_steps`，否则 buffer 永远不满 |
| INFO 日志不打印 | 脚本入口 `logging.basicConfig(level=logging.INFO)` |
| **制动传播被 dt 吞掉** | 传播延迟按**车辆累计长度/波速**算（真实重载数百米→数秒延迟），不要用车钩 free_length |
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

- `traffic_rl_project/docs/PROJECT_PIPELINE.md` — **pipeline 总览 + 下一步，先读这个**
- `traffic_rl_project/docs/RESEARCH_POSITIONING.md` — **阶段二研究定位 + 创新点 + 文献库（20+ 论文）**
- `traffic_rl_project/docs/learning_report.md` — 阶段一完整技术报告
- `traffic_rl_project/docs/training_results_standardized.md` — 阶段一学术成果报告
- `traffic_rl_project/docs/PAPER_DOWNLOAD_LINKS.md` — 开放获取论文手动下载网址
- `traffic_rl_project/docs/MCP_DEPLOYMENT.md` — scholar-search-mcp 部署说明
- `.learnings/LEARNINGS.md` — 踩坑记录

## 文献库（docs/papers/）

- **PDF（10 篇）**：Tang 2020（多机车 RL+车钩力）、Fu 2019（钩缓约束）、Huang 2025（专家系统+DRL）、Zhang 2025（20kT 制动）、Heineken 2023（最优控制节能）、Yang 2024（蚁群节能）、Guo 2025（MARL 车队）、魏咪（车钩力分层）、樊运新（3万吨纵向冲动）、杨敏（车钩间隙）
- **arXiv 源码（3 篇）**：2504.19480（LLM 奖励设计）、2003.03327（智能列车运行）、2312.06858_full（车队 MARL）
- **MCP**：`scholar-search` 已配置（Semantic Scholar + arXiv 双通道），详见 `docs/MCP_DEPLOYMENT.md`

## Code conventions

- PEP 8
- 训练脚本入口配置 logging
- 临时脚本用后即删
- 检查点定期保存；只使用专业仿真器，禁止 mock 环境
- **`.codebuddy/mcp.json` 已 gitignore**（含 API key，勿提交）
