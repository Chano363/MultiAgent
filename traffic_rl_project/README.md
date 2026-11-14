# 重载列车群组协同控制（Train Fleet RL）

用**多智能体强化学习**控制万吨重载列车编队：每台机车一个智能体，直接选**档位级动作**（`ed_cmd` + `ab_notch`，0 = 缓解），规则层降级为 **veto** 通道（车钩 ≤1000 kN 硬约束 / 最短充风 / ATP）。目标是在长大下坡区段同时做到速度同步、间距保持与车钩纵向冲动抑制。

| 项 | 值 |
| :--- | :--- |
| 研究对象 | 朔黄线 49.6 km 真实剖面；3 列万吨级 `1+0` 编组（每列 1 机车 + 108 货车，10988 t），共 3 个智能体 |
| 主配置 | `configs/experiments/formation_ed_ab_3train_1plus108.yaml` |
| 验收口径 | 车钩断面力绝对峰值 ≤ 1000 kN（ADR-040，**待验证目标**，非已达成） |
| 对比基线 | 规则基线 / Tube MPC（Song2026 架构）/ 本方法 |

**现在在做什么 → [`docs/PROJECT_PIPELINE.md`](docs/PROJECT_PIPELINE.md) §〇**。全仓唯一的「现在」层；本文件不复述状态，也不写"下一步"。

## 阶段脉络

本项目前身是无人机编队 MAPPO 控制（阶段一，已完结）。两阶段共用同一套 MARL + CTDE 方法论，阶段一留下的是 MAPPO 实现与调参经验，**不是**需要继续维护的代码。

| | 阶段一：无人机编队 | 阶段二：重载列车编队（本仓库主体） |
| :--- | :--- | :--- |
| 状态 | ✅ 已完结（2026-08） | 进行中，进度见 §〇 |
| 算法 | MAPPO（CTDE），Best Reward 235.5 | MAPPO 复用 `src/algorithms/mappo_agent.py` |
| 仿真器 | gym-pybullet-drones（已移除） | NeTrainSim 纵向动力学 → 自封装 Gym 环境 |
| 留存 | 代码与产物均不存在，仅存档：[`docs/logs/progress/ARCHIVE_PHASE1_UAV.md`](docs/logs/progress/ARCHIVE_PHASE1_UAV.md) | 本仓库全部代码；阶段一的 MAPPO 实现仍被复用 |

## 快速开始

环境：WSL2 Ubuntu + conda 环境 `traffic_rl`（Python 3.10，GPU 训练，不重复安装）。

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

# 训练（配置驱动，新增实验线只加 YAML，不改框架）
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus108.yaml --seed 0

# 短跑冒烟（改单个键不改文件）
python run_training.py --experiment <cfg>.yaml --override env_cfg.max_steps=60 --episodes 3
```

长跑**不要**从 IDE 内置终端起进程（客户端关闭会连带杀掉 WSL 进程，已发生 3 次）。启动方式见 `docs/rules/EXECUTION_RULES.md` §常驻启动。

## 目录结构

```
run_training.py          # 唯一训练入口（YOLO 风格：CLI + YAML 全配置）
configs/experiments/     # 能进论文的正式配置；探针配置不入库
src/
├── train_dynamics/      # 纵向动力学（NeTrainSim 公式、车钩、制动力）
├── environments/        # Gym 封装（train_fleet_env.py = 主环境）
├── controllers/         # 规则 / MPC / 安全层等底层控制器
├── algorithms/          # MAPPO（阶段一复用）
├── trainer/             # 训练循环、配置 schema、rollout
├── evaluation/          # 评估与诊断脚本（多数为一次性，见 §0.6 C2）
├── networks/ utils/
tests/                   # pytest
scripts/                 # 运维脚本
docs/                    # 全部文档，入口 docs/README.md
outputs/                 # 实验产物（不入库，本机约 18 GB，勿提交）
history/ reference/      # 历史与外部参考代码（死代码，不参与构建）
```

## 三个会让你白跑一天的点

1. **`outputs/` 不入库，clone 下来是空的。** 没有"拉下来就能复现论文数字"这回事：复评/重绘前先确认已有归档目录（`outputs/sim_validation/…`），没有就从头训。
2. **三个输出目录要一起换。** 只改 `checkpoint_dir`、放着 `results_dir` / `figures_dir` 不管，后两者会落回主配置路径并**覆写历史产物**（LRN-20261001-009）。冒烟与调试必须整套重定向。
3. **YAML 键名写错不会报错。** 代码里 `config.get(k, default)` 遍布，键名拼错只悄悄用默认值——现象是"参数改了但没生效"。改完配置先核对 metadata 里记录的实际生效值。

其余硬约束（长跑不得挂 IDE、验证默认整程、改动验收口径）见 [`../AGENTS.md`](../AGENTS.md)；规范正本见 [`docs/rules/EXECUTION_RULES.md`](docs/rules/EXECUTION_RULES.md)。

## 文档入口

读书顺序：**本文件 → `docs/PROJECT_PIPELINE.md` §〇 → `docs/rules/EXECUTION_RULES.md`**，查东西去 [`docs/README.md`](docs/README.md)（唯一索引）。

| 想找 | 去哪 |
| :--- | :--- |
| 在跑什么、下一步、挂起项、工程债 | [`docs/PROJECT_PIPELINE.md`](docs/PROJECT_PIPELINE.md) §〇 |
| 干活前必读的规范与易错点 | [`docs/rules/EXECUTION_RULES.md`](docs/rules/EXECUTION_RULES.md) |
| 研究定位 / 创新点 / 与同类工作差异 | [`docs/RESEARCH_POSITIONING.md`](docs/RESEARCH_POSITIONING.md) |
| 改码前速查（动力学 / 安全 / 训练 / MPC） | [`docs/knowledge/`](docs/knowledge/) |
| 踩坑与决策记录 | [`docs/logs/learnings/LEARNINGS.md`](docs/logs/learnings/LEARNINGS.md) · [`docs/logs/decisions/DECISIONS.md`](docs/logs/decisions/DECISIONS.md) |
