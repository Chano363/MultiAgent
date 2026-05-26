# 无人机编队控制强化学习项目

基于强化学习的无人机群组编队控制研究项目，使用 gym-pybullet-drones 专业物理仿真器。

## 项目目标

1. **保持编队队形**：无人机之间保持恒定的相对位置
2. **稳定飞行控制**：维持编队整体稳定飞行
3. **抗扰动能力**：减少外部扰动对编队的影响
4. **提高控制效率**：优化编队控制策略

## 技术栈

- **框架**: PyTorch, Gymnasium
- **算法**: PPO (Proximal Policy Optimization), DQN
- **仿真**: gym-pybullet-drones (专业物理仿真器)
- **优化**: Agent Lightning

## 项目结构

```
traffic_rl_project/
├── configs/                # 配置文件
│   ├── env_config.yaml     # 环境配置
│   ├── train_config.yaml   # 训练配置
│   └── agent_lightning_config.yaml
├── src/                    # 源代码
│   ├── algorithms/         # 强化学习算法
│   │   ├── __init__.py
│   │   ├── optimized_dqn.py
│   │   └── optimized_ppo.py
│   ├── environments/       # 环境定义
│   │   ├── __init__.py
│   │   └── formation_control_env.py
│   ├── networks/           # 神经网络
│   │   └── __init__.py
│   ├── scripts/            # 脚本
│   │   └── agent_lightning_train.py
│   ├── utils/              # 工具函数
│   │   └── __init__.py
│   ├── agent_lightning_integration.py
│   └── main.py
├── outputs/                # 输出目录
│   ├── logs/
│   ├── checkpoints/
│   └── results/
├── docs/                   # 文档
│   └── technical_report.md
└── requirements.txt
```

## 核心文件说明

| 文件                         | 功能                             |
| -------------------------- | ------------------------------ |
| `formation_control_env.py` | 基于 gym-pybullet-drones 的编队控制环境 |
| `optimized_ppo.py`         | 优化的 PPO 算法                     |
| `optimized_dqn.py`         | 优化的 DQN 算法                     |
| `agent_lightning_train.py` | Agent Lightning 训练脚本           |
| `main.py`                  | 主入口文件                          |

## 状态空间

每个无人机状态：

- 位置 (x, y, z)
- 速度
- 姿态角
- 与编队中心的相对位置

## 动作空间

每个无人机4维动作：

- 4个旋翼的转速控制

## 奖励函数

- 编队保持奖励
- 速度奖励
- 平滑性惩罚
- 碰撞惩罚
- 能量效率奖励

