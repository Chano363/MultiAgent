# 无人机编队控制强化学习项目

基于强化学习的无人机群组编队控制研究项目，使用 gym-pybullet-drones 专业物理仿真器，默认集成 Agent Lightning 优化框架。

## 🚀 快速开始

### 环境配置

```bash
# 激活 Conda 环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl

# 安装依赖
pip install -r requirements.txt
```

### 启动训练（默认使用 Agent Lightning）

```bash
# 基础训练（PPO算法，3架无人机，自动收敛检测）
python src/main.py

# 自定义训练参数
python src/main.py --algorithm PPO --episodes 500 --num_drones 3

# 使用 DQN 算法
python src/main.py --algorithm DQN --episodes 1000

# 禁用自动收敛检测（训练固定回合数）
python src/main.py --no_convergence --episodes 1000
```

### 断点续训（增量训练）

```bash
# 从检查点继续训练
python src/main.py --mode continue --checkpoint outputs/checkpoints/ppo_formation_ep100.pt

# 继续训练并调整参数
python src/main.py --mode continue --checkpoint outputs/checkpoints/ppo_formation_ep100.pt --episodes 1000
```

### 测试模型

```bash
# 测试训练好的模型
python src/main.py --mode test --checkpoint outputs/checkpoints/ppo_formation_ep500.pt

# 测试时启用可视化渲染
python src/main.py --mode test --checkpoint outputs/checkpoints/ppo_formation_ep500.pt --render
```

### 训练输出

训练完成后自动生成以下输出：

```
outputs/
├── checkpoints/          # 模型检查点（每50回合保存）
│   └── ppo_formation_ep500.pt
├── results/              # 训练结果
│   ├── ppo_formation_results.json    # 详细结果数据
│   ├── ppo_formation_results.yaml    # YAML格式结果
│   └── ppo_formation_training_results.png  # 可视化图表
└── logs/                 # 训练日志
```

---

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
| `agent_lightning_train.py` | Agent Lightning 训练脚本（默认使用） |
| `main.py`                  | 主入口文件（集成 Agent Lightning）    |

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--mode` | str | train | 运行模式：train/continue/test |
| `--algorithm` | str | PPO | 算法：PPO/DQN |
| `--episodes` | int | 500 | 训练回合数（或直到收敛） |
| `--num_drones` | int | 3 | 无人机数量 |
| `--device` | str | cuda | 计算设备 |
| `--checkpoint` | str | None | 检查点路径（断点续训/测试） |
| `--config` | str | configs/train_config.yaml | 训练配置文件 |
| `--env_config` | str | configs/env_config.yaml | 环境配置文件 |
| `--no_convergence` | flag | False | 禁用自动收敛检测 |
| `--render` | flag | False | 启用可视化渲染 |

## 可视化输出

训练完成后自动生成可视化图表：

1. **训练奖励曲线** - 展示每回合奖励变化趋势
2. **损失曲线** - 展示训练损失变化
3. **收敛检测** - 自动检测训练是否收敛
4. **结果数据** - JSON/YAML格式的详细训练结果

## 断点续训特性

- 支持从检查点继续训练
- 自动加载历史奖励数据
- 保留最佳奖励记录
- 支持调整训练参数后继续训练

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