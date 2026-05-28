# PPO 到 SAC 算法转换经验总结

## 日期: 2026-05-28

---

## 1. 转换背景与动机

### 1.1 PPO 算法在当前任务上的表现问题

经过长时间训练（>1000 episodes），PPO 算法在无人机编队控制任务上存在以下问题：

| 问题 | 现象 | 原因分析 |
|------|------|----------|
| Loss 持续为 0 | 梯度从未有效更新 | 早期配置问题导致 buffer 始终小于 batch_size |
| 奖励波动剧烈 | 奖励曲线呈"锯齿状"，无法收敛 | PPO 的 clipped objective 导致策略更新保守 |
| 速度接近 0 | 智能体学会"静止不动"以避免惩罚 | 奖励函数设计问题，但 PPO 难以有效探索 |
| 收敛速度慢 | 需要数千轮才能达到 Best=34 | PPO 对连续动作空间的探索效率较低 |

### 1.2 为什么选择 SAC

SAC（Soft Actor-Critic）相比 PPO 的优势：

1. **最大熵框架**：鼓励策略保持探索，避免早熟收敛到次优解
2. **经验回放**：更高效地利用历史数据，提高样本效率
3. **双 Q 网络**：减少 Q 值过估计问题
4. **自动熵调整**：无需手动调节熵系数

---

## 2. 实施过程

### 2.1 SACAgent 实现

参考 `src/algorithms/sac_agent.py`，SAC 的核心组件：

```python
class SACAgent:
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,        # 软更新系数
        alpha: float = 0.2,         # 熵系数
        automatic_entropy_tuning: bool = True,  # 自动调整熵
        buffer_capacity: int = 1000000,
        batch_size: int = 256,
        device: str = 'cuda'
    ):
```

### 2.2 关键参数配置

在 `configs/train_config.yaml` 中添加的 SAC 配置：

```yaml
hyperparameters:
  sac:
    learning_rate: 0.0003
    gamma: 0.99
    tau: 0.005
    alpha: 0.2
    automatic_entropy_tuning: true
    buffer_capacity: 1000000
    batch_size: 256
```

### 2.3 训练脚本集成

修改 `src/scripts/agent_lightning_train.py`：

```python
elif algorithm.upper() == 'SAC':
    params = algo_params.get('sac', {})
    agent = SACAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        learning_rate=params.get('learning_rate', 3e-4),
        gamma=params.get('gamma', 0.99),
        tau=params.get('tau', 0.005),
        ...
    )
```

### 2.4 Agent Lightning 集成

修改 `src/agent_lightning_integration.py`，添加 SAC 分支支持：

```python
elif self.algorithm == "SAC":
    flattened_state = state.flatten()
    action = self.agent.select_action(flattened_state)
    # ... 执行 step
    self.agent.store_transition(flattened_state, action, reward, next_state.flatten(), done)
    metrics = self.agent.update()
```

---

## 3. 转换效果对比

### 3.1 训练稳定性

| 指标 | PPO | SAC |
|------|-----|-----|
| 奖励波动 | ±800+ | ±400-600 |
| 收敛速度 | 数千轮 | 约 100-200 轮 |
| Best Reward | ~34 (PPO) | ~3000+ (SAC) |

### 3.2 速度控制

| 指标 | PPO | SAC |
|------|-----|-----|
| 平均速度 | ~0.1 m/s | ~1.0-1.5 m/s |
| 最大速度 | 0.5 m/s | 1.75 m/s |
| 速度稳定性 | 极不稳定 | 相对稳定 |

---

## 4. 遇到的问题与解决

### 4.1 问题 1：SAC 算法不被支持

**错误**: `ValueError: 不支持的算法: SAC`

**原因**: `agent_lightning_integration.py` 中只实现了 PPO 和 DQN 分支

**解决**: 在 `DroneFormationLitAgent.rollout()` 方法中添加 SAC 分支

### 4.2 问题 2：速度计算错误

**问题**: 只使用 episode 最后一步的速度，而非整个 episode 的平均速度

**原因**: `mean_velocity` 只在 rollout 结束时用最终 state 计算

**解决**: 在每步记录 `episode_velocities.append()`，最后取平均

```python
# 修改前
mean_vel = np.mean(np.linalg.norm(state[:, 6:9], axis=1))

# 修改后
episode_velocities.append(np.mean(np.linalg.norm(state[:, 6:9], axis=1)))
mean_velocity = np.mean(episode_velocities)
```

### 4.3 问题 3：动作空间不匹配

**问题**: RPM 动作空间过于底层，学习难度大

**原因**: 原始使用 `ActionType.RPM`，但与 VEL 模式的 PID 控制不匹配

**解决**: 改用 `ActionType.VEL`，让底层 PID 处理姿态控制

---

## 5. 奖励函数优化（按 prompts.md 方案）

### 5.1 优化后的奖励函数

```python
def _calculate_reward(self, obs: np.ndarray) -> float:
    positions = obs[:, :3]
    velocities = obs[:, 6:9]

    reward = 0.0

    # 1. 水平速度奖励（降低权重）
    horizontal_speeds = np.linalg.norm(velocities[:, :2], axis=1)
    mean_horiz = np.mean(horizontal_speeds)
    reward += 8.0 * mean_horiz

    # 2. 垂直速度惩罚（替代奖励）
    vertical_speeds = np.abs(velocities[:, 2])
    mean_vert = np.mean(vertical_speeds)
    reward -= 1.0 * mean_vert

    # 3. 低速强制移动惩罚
    MIN_HORIZ_SPEED = 0.5
    if mean_horiz < MIN_HORIZ_SPEED:
        reward -= 5.0 * (MIN_HORIZ_SPEED - mean_horiz)

    # 4. 高度误差惩罚（略增）
    for i in range(self.num_drones):
        alt_error = abs(positions[i][2] - self.target_altitude)
        reward -= 0.8 * alt_error

        # 边界软惩罚
        if positions[i][2] > 8.0:
            reward -= 2.0 * (positions[i][2] - 8.0)
        if positions[i][2] < 0.2:
            reward -= 1.0 * (0.2 - positions[i][2])

    # 5. 速度超限惩罚
    for i in range(self.num_drones):
        speed = np.linalg.norm(velocities[i])
        if speed > self.max_speed:
            reward -= 0.5 * (speed - self.max_speed)

    # 6. 编队惩罚（大幅增加）
    for i in range(1, self.num_drones):
        dist_to_prev = np.linalg.norm(positions[i] - positions[i-1])
        dist_error = abs(dist_to_prev - self.target_distance)
        reward -= 0.1 * dist_error      # 原 0.01
        speed_diff = np.linalg.norm(velocities[i] - velocities[i-1])
        reward -= 0.02 * speed_diff     # 原 0.005

    # 7. 速度一致性奖励
    if mean_horiz > 0.1:
        mean_horiz_vec = np.mean(velocities[:, :2], axis=0)
        mean_speed_h = np.linalg.norm(mean_horiz_vec)
        if mean_speed_h > 0.01:
            alignment = 0.0
            for i in range(self.num_drones):
                v_xy = velocities[i, :2]
                speed_i = np.linalg.norm(v_xy)
                if speed_i > 0.01:
                    alignment += np.dot(v_xy, mean_horiz_vec) / (speed_i * mean_speed_h)
            reward += 0.5 * alignment / self.num_drones

    # 8. 生存奖励
    reward += 0.05

    # 9. 净位移奖励（替代每步位移奖励）
    center_pos_xy = np.mean(positions[:, :2], axis=0)
    net_displacement = np.linalg.norm(center_pos_xy - self._start_center_xy)
    reward += 1.0 * net_displacement

    # 10. 裁剪到合理范围
    reward = np.clip(reward, -5.0, 25.0)
    return reward
```

### 5.2 关键修改点

| 修改项 | 修改前 | 修改后 | 原因 |
|--------|--------|--------|------|
| 水平速度奖励 | 15.0 | 8.0 | 降低权重，避免过度追求速度 |
| 垂直速度 | +2.0 | -1.0 | 惩罚垂直方向移动，防止爬升 |
| 高度误差惩罚 | -0.5 | -0.8 | 增强高度控制 |
| 编队距离惩罚 | -0.01 | -0.1 | 大幅增加，减少间距误差 |
| 编队速度惩罚 | -0.005 | -0.02 | 减少速度差异 |
| 每步位移奖励 | 每步距离 | 净位移 | 鼓励直线前进 |
| 奖励裁剪 | [-10, 50] | [-5, 25] | 更合理的奖励范围 |

---

## 6. 可视化指标扩展

### 6.1 新增指标

1. **FormationErr（编队误差）**: 无人机间距与目标距离的误差
2. **HeightErr（高度误差）**: 无人机高度与目标高度的误差
3. **Speed（速度）**: episode 平均速度

### 6.2 日志格式

```
Episode  100/1000 | Reward: +1344.37 | Avg10: 1321.32±537.47 | Best: 2717.78 | Loss: -43.9218 | Speed:  1.08 m/s | FormationErr: 2.144 m | HeightErr: 0.878 m
```

### 6.3 训练曲线

更新后的 `plot_training_curve()` 函数现在包含 5 个子图：

1. **Training Reward**: 奖励曲线
2. **Training Loss**: 损失曲线
3. **Average Velocity**: 速度曲线
4. **Formation Error**: 编队误差曲线
5. **Height Error**: 高度误差曲线

---

## 7. 经验总结

### 7.1 算法选择建议

| 场景 | 推荐算法 |
|------|----------|
| 连续动作空间，需要稳定收敛 | SAC |
| 需要快速探索新策略 | PPO |
| 动作空间离散 | DQN |

### 7.2 SAC 调参技巧

1. **learning_rate**: 3e-4 适合大多数任务
2. **tau**: 0.005 是软更新的良好默认值
3. **alpha**: 使用自动熵调整更方便
4. **buffer_capacity**: 足够大（1000000）以容纳丰富经验
5. **batch_size**: 256 是个不错的默认值

### 7.3 关键代码模式

```python
# 每步更新（SAC 特性）
metrics = self.agent.update()
episode_loss += metrics.get('total_loss', 0.0)

# 记录额外指标
episode_formation_errors.append(info.get('formation_error', 0))
episode_height_errors.append(info.get('height_error', 0))
```

---

## 8. 下一步优化方向

1. **编队误差优化**: 当前 1.5-2.5m，需要通过增加编队惩罚权重进一步优化
2. **高度控制**: 0.8m 误差需要更精确的 PID 调参
3. **速度一致性**: 进一步提高无人机间的速度匹配
4. **SAC 超参数**: 尝试更大的 batch_size 或更小的 tau

---

*文档版本: 1.0*
*最后更新: 2026-05-28*
