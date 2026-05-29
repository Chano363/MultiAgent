# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260528-002] best_practice

**Logged**: 2026-05-28T20:00:00Z
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
gym-pybullet-drones VEL模式的方向归一化会导致Z轴偏置被稀释；正确的做法是移除人工抗重力偏置，让PID控制器自然处理重力补偿。

### Details
**问题背景**:
在FormationControlEnv中将SAC的3D动作转换为VEL模式的4D动作时，添加了Z轴抗重力偏置(desired_vel[:, 2] += bias)。但这个偏置在方向归一化后被大幅稀释——当X/Y分量较大时，归一化后的方向向量中Z分量变得非常小，导致爬升力不足。

**错误方法(失败)**:
1. `desired_vel[:, 2] += 0.15` → 归一化后Z被稀释
2. `desired_vel[:, 2] = desired_vel[:, 2] * 0.5 + 0.3` → 同样被稀释
3. `magnitude = np.maximum(magnitude, 0.2)` → 无法悬停，[0,0,0]动作也产生0.2 m/s速度

**根本原因**:
VEL模式内部(target_vel = SPEED_LIMIT * |magnitude| * direction)总是将direction归一化为单位向量。任何在归一化前添加的偏置都会被重新缩放。

**正确方法**:
- 移除所有人工偏置和下限
- 3D动作直接转换为VEL格式：direction=action[:3]/norm, magnitude=clip(norm, 0, 1)
- action=[0,0,0] → magnitude=0 → target_vel=[0,0,0] → PID积分项自动补偿重力
- gym-pybullet-drones的PID控制器已内置重力补偿机制

### Suggested Action
所有基于VEL模式的强化学习环境都应遵循此原则：不添加人工偏置，让底层PID处理物理补偿。

### Metadata
- Source: debugging
- Related Files: d:\Code\MultiAgent\traffic_rl_project\src\environments\formation_control_env.py, d:\Code\MultiAgent\gym_pybullet_drones\gym_pybullet_drones\envs\BaseRLAviary.py
- Tags: gym-pybullet-drones, VEL模式, PID, 重力补偿, 归一化
- Pattern-Key: env.vel_mode.direction_normalization

---

## [LRN-20260528-001] insight

**Logged**: 2026-05-28T18:30:00Z
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
项目是基于强化学习的无人机编队控制研究项目，使用gym-pybullet-drones物理仿真器和Agent Lightning优化框架。

### Details
项目结构包含两个主要部分：
1. **traffic_rl_project/** - 主项目目录，包含RL算法实现和Agent Lightning集成
2. **gym_pybullet_drones/** - 专业无人机物理仿真器

**核心技术栈**:
- **仿真器**: gym-pybullet-drones（支持多无人机仿真）
- **框架**: PyTorch + Agent Lightning
- **算法**: DQN、PPO、SAC
- **环境**: Windows 11 + WSL2 (Ubuntu 24.04) + CUDA

**核心文件**:
- `agent_lightning_integration.py`: Agent Lightning集成适配器，将RL训练路由到`Trainer.fit`流程
- `formation_control_env.py`: 基于gym-pybullet-drones的编队控制环境
- `optimized_ppo.py`/`optimized_dqn.py`/`sac_agent.py`: 三种强化学习算法实现

**项目目标**:
- 保持编队队形（无人机间恒定相对位置）
- 稳定飞行控制
- 抗扰动能力
- 提高控制效率

### Suggested Action
后续工作应关注：
1. 验证环境配置是否正确
2. 检查Agent Lightning集成是否完整
3. 运行训练脚本验证功能

### Metadata
- Source: conversation
- Related Files: traffic_rl_project/src/agent_lightning_integration.py, traffic_rl_project/src/environments/formation_control_env.py
- Tags: drone, reinforcement-learning, multi-agent, formation-control
- Pattern-Key: project.understanding.drone-rl

---

