# 无人机编队控制强化学习项目

## 算法说明

**本项目使用 SAC (Soft Actor-Critic) 算法作为默认训练算法。**

### 为什么选择 SAC

1. **连续动作空间支持**: SAC 原生支持连续动作空间，非常适合无人机速度控制
2. **自动熵调节**: SAC 具有自动熵调节机制，可以平衡探索与利用
3. **稳定的训练过程**: 相比 DDPG 等算法，SAC 训练更稳定

### 配置

算法配置位于 `configs/train_config.yaml`:

```yaml
training:
  hyperparameters:
    sac:
      learning_rate: 3e-4
      gamma: 0.99
      tau: 0.005
      alpha: 0.2
      automatic_entropy_tuning: true
      buffer_capacity: 1000000
      batch_size: 256
```

### 训练命令

```bash
# 使用 SAC 算法训练（默认）
python src/main.py --algorithm SAC --episodes 500

# 指定回合数
python src/main.py --algorithm SAC --episodes 1000
```

### 环境配置

环境配置位于 `configs/env_config.yaml`:

```yaml
environment:
  num_drones: 3
  target_distance: 5.0  # 无人机间距
  target_altitude: 1.0   # 目标高度
  max_speed: 3.0         # 最大速度 m/s
  max_steps: 400
```

### 动作空间

- **类型**: 连续速度控制 (VEL)
- **维度**: 12维 (3架无人机 × 4个参数: X方向, Y方向, Z方向, 速度幅度)
- **格式**: `[vx, vy, vz, magnitude]` - 前3维是速度方向(会被归一化)，第4维是速度幅度(0-1)

### 观测空间

- **维度**: 216维 (3架无人机 × 72维状态)
- **内容**: 位置、速度、角度等物理状态

## 关键修复 (2026-05-28)

### 动作空间问题

**问题**: gym-pybullet-drones 的 VEL 模式需要 **4维动作**，不是3维！

- `target[0:3]` - 速度方向向量（会被归一化）
- `target[3]` - 速度幅度（0-1，会被 `SPEED_LIMIT` 放大）

之前代码错误地将动作空间设为3维，导致：
- `IndexError: index 3 is out of bounds for axis 0 with size 3`
- `RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x213 and 216x256)`

**修复**:
1. 将动作空间修正为4维: `shape=(num_drones, 4)`
2. 在step函数中将4维动作转换为 `[vx, vy, vz, magnitude]` 格式
3. 更新所有reshape操作从3改为4

## 最近修复 (2026-05-28)

### 动作空间问题

**问题**: 之前代码中动作空间被错误地设置为12维RPM控制，导致SAC输出的负数动作被截断为0，无人机无法获得升力。

**修复**:
1. 强制将动作空间修正为3维速度控制
2. 在step函数中添加动作缩放逻辑
3. 简化奖励函数，移除复杂的高度门控

### 训练结果

修复后训练结果显著改善:
- 最佳奖励: 从 -13000 提升到 +677
- 无人机能够正常飞行并保持编队