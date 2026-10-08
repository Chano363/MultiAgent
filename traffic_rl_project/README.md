# Traffic RL Project

**两阶段递进式研究**：无人机编队 MAPPO 控制（已完成）→ 重载列车群组协同控制（进行中）

> 📋 **先读 [docs/PROJECT_PIPELINE.md](docs/PROJECT_PIPELINE.md)** —— 项目工作流程总览、当前进度、下一步行动计划

## 状态一览

| 阶段 | 状态 |
|:---|---:|
| 无人机编队环境（gym-pybullet-drones 3架 VEL模式） | ✅ |
| MAPPO CTDE训练收敛（Best Reward 235.5） | ✅ |
| Algorithm Lightning集成（断点续训、收敛检测） | ✅ |
| 列车动力学文献调研 | ✅ |
| 列车Gym环境搭建 | ⬜ |
| 列车编队MAPPO迁移 | ⬜ |

## 快速开始

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/main.py --mode train --algorithm MAPPO --episodes 500
```

环境要求：WSL2 Ubuntu 24.04 + Conda + Python 3.10 + NVIDIA GPU

## 项目结构

```
src/
├── main.py                          # train/test/continue 入口
├── agent_lightning_integration.py   # Agent Lightning LitAgent 适配
├── trainer/
│   ├── __init__.py
│   └── train_loop.py                # 训练循环（含 create_agent, train_agent）
├── environments/formation_control_env.py  # 无人机编队 Gym 环境
├── algorithms/
│   ├── mappo_agent.py               # MAPPO（唯一收敛的算法）
│   ├── sac_agent.py                 # SAC（后期策略退化）
│   └── optimized_ppo.py             # PPO（不稳定，不推荐）
└── utils/
configs/                             # YAML 超参数
docs/
├── learning_report.md               # 完整学习报告 → **新开发者第1步读这个**
└── training_results_standardized.md # 正式学术报告
docs/rules/EXECUTION_RULES.md        # 执行规范 → **开始干活前先读这个**
```

## 关键文档阅读顺序

0. [PROJECT_PIPELINE.md](docs/PROJECT_PIPELINE.md) — **Pipeline 总览 + 下一步计划（先读这个）**
1. [EXECUTION_RULES.md](docs/rules/EXECUTION_RULES.md) — 执行规范、易错点（必须先读）
2. [learning_report.md](docs/learning_report.md) — 全部技术细节、文献调研、下一步计划
3. [training_results_standardized.md](docs/training_results_standardized.md) — 正式训练结果报告

## 文档索引

| 文档 | 定位 |
|:--|:--|
| [PROJECT_PIPELINE.md](docs/PROJECT_PIPELINE.md) | 全项目工作流程 Pipeline、两阶段进度、下一步行动清单 |
| [EXECUTION_RULES.md](docs/rules/EXECUTION_RULES.md) | 执行规范（环境、训练、代码约束、metadata） |
| [learning_report.md](docs/learning_report.md) | 阶段一完整技术报告 |
| [training_results_standardized.md](docs/training_results_standardized.md) | 阶段一学术成果报告 |
| [ppt_plan.md](docs/ppt_plan.md) | 导师汇报 PPT 提纲 |
| [LEARNINGS.md](../.learnings/LEARNINGS.md) | 调试踩坑记录 |

## 易错点（节省排查时间）

| # | 问题 | 正确做法 |
|:-:|:---|:---|
| 1 | Agent Lightning 脚本永不退出 | `SharedMemoryExecutionStrategy` 必须设 `main_thread="algorithm"` |
| 2 | YAML中科学计数法被解析为字符串 | 用 `0.0003` 而非 `3e-4` |
| 3 | 动作维度不匹配报错 | 环境交互用 reshape（3×4），Transition存储用 flatten（12维） |
| 4 | Loss 始终为 0 | 检查 `batch_size ≤ n_steps`，否则buffer永远填不满 |
| 5 | Episode 第1步就截断 | pybullet-drones 默认 `x>2.0` 截断，编队任务改为 `x>20.0` |
| 6 | INFO日志不输出 | 脚本必须配置 `logging.basicConfig(level=logging.INFO)` |