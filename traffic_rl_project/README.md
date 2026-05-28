# 无人机编队控制强化学习项目

基于强化学习的无人机群组编队控制研究项目，使用 gym-pybullet-drones 专业物理仿真器，默认集成 Agent Lightning 优化框架。

## 🚀 快速开始

### 环境配置要求

本项目必须在以下环境中运行，**不支持其他配置方式**：

- **操作系统**: Windows 11 + WSL2 (Ubuntu 24.04 LTS)
- **包管理器**: Conda (miniconda3)
- **计算设备**: NVIDIA GPU + CUDA
- **Python版本**: 3.10+

### 环境准备步骤

#### 步骤1：激活 Conda 环境

```bash
# 在 WSL2 Ubuntu 终端中执行
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
```

**注意**: 
- 确保已安装 miniconda3
- 确保已创建名为 `traffic_rl` 的 conda 环境
- 如果环境不存在，请先创建：`conda create -n traffic_rl python=3.10`

#### 步骤2：安装 PyTorch (GPU版本)

```bash
# 安装 PyTorch 2.0+ with CUDA 11.8 支持
pip install torch==2.0.0 torchvision==0.15.0 torchaudio==2.0.0 --index-url https://download.pytorch.org/whl/cu118
```

**验证 PyTorch GPU 支持**:
```bash
# 创建临时验证脚本
cat > verify_pytorch.py << 'EOF'
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
EOF

# 执行验证
python verify_pytorch.py

# 删除临时脚本
rm verify_pytorch.py
```

预期输出应显示 `CUDA available: True`

#### 步骤3：安装项目依赖

```bash
# 进入项目目录
cd /mnt/d/Code/MultiAgent/traffic_rl_project

# 安装所有依赖
pip install -r requirements.txt
```

**依赖列表**:
- gymnasium>=0.29.0
- gym-pybullet-drones>=2.1.0
- agentlightning
- numpy>=1.24.0
- matplotlib>=3.7.0
- tensorboard>=2.14.0
- tqdm>=4.65.0
- pyyaml>=6.0
- pybullet>=3.2.0
- scipy>=1.10.0

#### 步骤4：验证环境配置

```bash
# 验证所有关键依赖
python -c "
import torch
import gymnasium as gym
import pybullet
import agentlightning as agl
from gym_pybullet_drones.envs.MultiHoverAviary import MultiHoverAviary
print('✓ 所有依赖安装成功')
print(f'✓ PyTorch CUDA: {torch.cuda.is_available()}')
print(f'✓ PyTorch version: {torch.__version__}')
"
```

### 启动训练

#### 基础训练（SAC算法）

```bash
# 使用 SAC 算法训练 1000 回合，使用 GPU
python src/scripts/agent_lightning_train.py --algorithm SAC --episodes 1000 --device cuda
```

#### 从检查点继续训练

```bash
# 从最新检查点继续训练
python src/scripts/agent_lightning_train.py --algorithm SAC --episodes 1000 --device cuda --checkpoint outputs/checkpoints/sac_formation_ep130.pt
```

**训练参数说明**:
- `--algorithm`: 算法选择（SAC/PPO/DQN），推荐使用 SAC
- `--episodes`: 训练回合数
- `--device`: 计算设备，必须使用 `cuda`（GPU）
- `--checkpoint`: 检查点路径（可选，用于断点续训）

### 训练输出

训练完成后，输出文件位于 `outputs/` 目录：

```
outputs/
├── checkpoints/          # 模型检查点（每10回合保存）
│   ├── sac_formation_ep10.pt
│   ├── sac_formation_ep20.pt
│   └── sac_formation_ep100.pt
├── results/              # 训练结果
│   ├── sac_results.json
│   └── sac_formation_training_results.png
└── logs/                 # 训练日志
```

### 训练监控

训练过程中会实时显示以下指标：

```
Episode  100/1000 | Reward: +434.78 | Avg10: -563.99±503.08 | Best:  434.78 | Loss:  23.9654 | Speed:  1.14 m/s | FormationErr: 1.688 m | HeightErr: 0.771 m
```

**指标说明**:
- `Reward`: 当前回合总奖励
- `Avg10`: 最近10回合平均奖励 ± 标准差
- `Best`: 历史最佳奖励
- `Loss`: 训练损失
- `Speed`: 平均速度 (m/s)
- `FormationErr`: 编队误差 (m)
- `HeightErr`: 高度误差 (m)

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