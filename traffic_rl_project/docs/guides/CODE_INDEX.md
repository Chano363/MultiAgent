---
title: 代码与配置索引
date: 2026-09-01
status: active
owner: Owner
supersedes: partial（自 PROJECT_PIPELINE.md 抽出，内容零丢失）
---


## 五、代码与配置索引

### 阶段一代码结构（`src/`）

| 路径                                      | 职责                                    |
| :-------------------------------------- | :------------------------------------ |
| `main.py`                               | 入口：train / continue / test 三模式        |
| `environments/formation_control_env.py` | 编队 Gym 环境（包装 MultiHoverAviary VEL 模式） |
| `algorithms/mappo_agent.py`             | MAPPO（CTDE + KL 早停，**唯一收敛算法**）        |
| `algorithms/optimized_ppo.py`           | PPO（不稳定，不推荐）                          |
| `algorithms/sac_agent.py`               | SAC（后期退化）                             |
| `algorithms/optimized_dqn.py`           | DQN（未验证）                              |
| `trainer/train_loop.py`                 | 传统训练循环 + 收敛检测                         |
| `agent_lightning_integration.py`        | Agent Lightning 编排训练（默认路径）            |
| `utils/`                                | 图表、结果存储、指标跟踪                          |

### 阶段二代码结构（新增，P0/P0.5 已完成）

| 路径                             | 职责                                            |
| :----------------------------- | :-------------------------------------------- |
| `train_dynamics/`              | 列车纵向动力学（NeTrainSim 公式 + 多体车钩）                 |
| `train_dynamics/resistance.py` | Davis 阻力公式                                    |
| `train_dynamics/tractive.py`   | 牵引力（功率/粘着约束 + throttle 曲线）                    |
| `train_dynamics/braking.py`    | Karwatzki 制动 + **离散空气制动档位（EB/SB）+ 机车电制动（连续）** |
| `train_dynamics/coupler.py`    | 车钩力（质量-弹簧-阻尼）                                 |
| `train_dynamics/train.py`      | 多体动力学积分器 + **空气制动波速传播**（纵向冲动来源）               |
| `train_dynamics/params.py`     | 机车/货车/车钩参数                                    |
| `environments/train_env.py`    | 列车编队 Gym 环境（电制动/空气制动分离 + 车钩力 1000kN 指标）       |
| `safety_layer.py`              | **规则式 ATP 安全层**（限速/车钩力 1000kN/间距约束，动作前修正）     |
| `tests/test_train_dynamics.py` | 动力学数值验证（18 测试）                                |
| `tests/test_train_env.py`      | 环境闭环验证（8 测试）                                  |
| `tests/test_safety_layer.py`   | 安全层 + 制动/电制动/传播验证（14 测试）                      |

### 配置文件

| 文件                                    | 用途                                        |
| :------------------------------------ | :---------------------------------------- |
| `configs/train_config.yaml`           | 每算法超参数（`training.hyperparameters.<algo>`） |
| `configs/env_config.yaml`             | 环境参数（num\_drones / 间距 / 奖励权重）             |
| `configs/agent_lightning_config.yaml` | Agent Lightning 调优配置                      |

### 输出目录

| 路径                                          | 内容                         |
| :------------------------------------------ | :------------------------- |
| `outputs/checkpoints/`                      | 训练检查点（ep\*.pt，已 gitignore） |
| `outputs/results/<algo>_formation_results/` | results.json/yaml + charts |
| `outputs/deploy/`                           | 最佳模型 + 配置快照 + 标注曲线         |

***
