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


---

## [LRN-20260903-001] correction

**Logged**: 2026-09-03T03:00:00Z
**Priority**: high
**Status**: resolved
**Area**: evaluation-protocol

### Summary
`evaluate_m1_m3_long.py` 默认 `MAX_STEPS=35000`（35km 剖面专用），历史论文协议是朔黄线主剖面 **3000 步**。未传 `--max_steps 3000` 直接评估会跑 35000 步 → 间距漂移巨大（2400m+）、reward 崩到 -160万，被误判为"100% 动力学下 M1 策略失效/追尾 12811 步"。

### Details
**问题背景**: 100% 动力学下 M1 重训完成后，用 `evaluate_m1_m3_long.py m1 <ckpt> --etcs --n_seed 1` 评估，reward=-160万、间距漂移 2453m、追尾 48 步；加 5-seed 随机化后追尾 12811 步。误以为 M1 训练失效。

**错误方法(失败)**: 直接看 reward 绝对值判定"崩溃"，未先核对评估协议步数与历史一致。

**根本原因**: 该脚本默认 `MAX_STEPS = 35000  # 对齐 35km 剖面（~16.7m/s巡航 → ~35km ≈ 2100s → 21000步；留余35000步）`。历史论文主对比（朔黄线 23.8km）是 **3000 步**（`eval_phys2_m1_5seed.py --steps 3000`）。35km 剖面步数长 11.7×，列车跑完全程后继续跑 → 间距自然漂移、reward 累积大负。

**解决方案**: 评估命令统一加 `--max_steps 3000`。修正后 M1 +14697 / M3 +21099 / MPC-fair +3353 / MPC-dir -200548 / DQN-fair +8274 / Coast +24392（全 0 追尾，车钩力 323-559kN）。

**预防**:
1. 用 `evaluate_m1_m3_long.py` 前必查脚本内 `MAX_STEPS` 默认值，与目标剖面/历史协议对齐。
2. 评估协议（步数/seed/剖面）应先从历史结果文件（`outputs/*.txt`、`eval_summary.json`）核对，而不是从脚本默认值推断。
3. 大负 reward / 超大间距漂移先怀疑"步数协议不匹配"，再怀疑策略失效。

### Suggested Action
所有 100% 动力学重跑评估命令统一带 `--max_steps 3000`（朔黄线主剖面）。

### Metadata
- Source: conversation
- Related Files: traffic_rl_project/src/evaluation/evaluate_m1_m3_long.py, traffic_rl_project/src/evaluation/eval_phys2_m1_5seed.py
- Tags: evaluation-protocol, max-steps, heavy-haul, reward-scaling
- Pattern-Key: evaluation.max-steps-mismatch
