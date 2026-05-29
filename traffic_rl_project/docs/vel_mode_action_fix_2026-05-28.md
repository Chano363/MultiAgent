# VEL模式动作空间修复经验 | 2026-05-28

## 问题概述

无人机编队控制环境中，将 SAC 的 3D 动作转换为 gym-pybullet-drones VEL 模式所需的 4D 格式时，反复出现无人机无法维持高度、持续坠机、奖励严重为负的问题。

---

## 错误尝试：三次失败的修复方案

### 方案1：抗重力偏置 + 幅度下限

```python
desired_vel[:, 2] += 0.15
magnitude = np.maximum(norms, 0.2)
```

**结果**: `Reward = -3263`，HeightErr = 0.769m。完全失败。

### 方案2：Z轴压缩 + 偏置

```python
desired_vel[:, 2] = desired_vel[:, 2] * 0.5 + 0.3
magnitude = np.maximum(norms, 0.2)
```

**结果**: `Reward = -222`，HeightErr = 0.643m。略有改善但本质问题未解决。

### 方案3：移除偏置，3D动作直接传递给VEL

```python
direction = desired_vel / safe_norms
magnitude = np.clip(norms, 0.0, 1.0)
```

**结果**: `Reward = -563`，HeightErr = 0.724m。反而倒退。

---

## 根因分析

### VEL模式的内部机制

在 `BaseRLAviary._preprocessAction()` 中，VEL 模式的处理逻辑如下：

```python
# target[0:3] = 方向分量, target[3] = 幅度
if np.linalg.norm(target[0:3]) != 0:
    v_unit_vector = target[0:3] / np.linalg.norm(target[0:3])
else:
    v_unit_vector = np.zeros(3)
target_vel = SPEED_LIMIT * np.abs(target[3]) * v_unit_vector
```

关键结论：
1. **方向分量总会归一化为单位向量** — 任何在归一化前添加的偏置都会被稀释
2. **幅度是独立维度** — 幅度 = 0 时，无论方向分量是什么，target_vel = [0, 0, 0]

### 失败的根因

所有三种失败方案的共同问题：

| 问题 | 说明 |
|------|------|
| **偏置被方向归一化稀释** | 当 X/Y 分量较大时，归一化后的 Z 分量变得极小。例如 `action=[1,0,0]` 且 Z 偏置 0.3 时，归一化后 Z 仅 0.287 |
| **幅度下限导致无法悬停** | `magnitude = max(norm, 0.2)` 使 [0,0,0] 动作产生 0.2 m/s 速度，无人机永不能静止 |
| **方向归一化放大微小动作** | `[0.01, 0, 0]` 被归一化为 `[1, 0, 0]`，任何非零动作都变成全速 |

### 被忽略的关键事实

**gym-pybullet-drones 的 PID 控制器已内置重力补偿机制！**

当 target_vel = [0, 0, 0] 时，PID 的积分项会积累重力引起的速度误差，自动调节电机转速以维持悬停。不需要任何人抗重力偏置。

---

## 正确方案：4D动作空间

### 改动

将环境动作空间从 3D `(num_drones, 3)` 改为 4D `(num_drones, 4)`：

```python
# [vx, vy, vz, mag] ∈ [-1, 1]
self.action_space = spaces.Box(
    low=-1.0, high=1.0,
    shape=(self.num_drones, 4),
    dtype=np.float32
)
```

step 函数改为直接传递：

```python
def step(self, action):
    scaled_action = action.copy()
    scaled_action[:, 3] = np.abs(scaled_action[:, 3])  # 确保幅度非负
    obs, ... = self.aviary.step(scaled_action)
```

### 为什么有效

| 动作 | 物理含义 | target_vel |
|------|----------|------------|
| `[0, 0, 0, 0]` | 悬停 | `[0, 0, 0]` — PID 自动补偿重力 |
| `[0, 0, 0.5, 0.5]` | 半速上升 | `[0, 0, 0.5 m/s]` |
| `[1, 0, 0, 1.0]` | 全速前进 | `[1.0, 0, 0 m/s]` |
| `[1, 0, 0.5, 0.7]` | 前上方向70%速度 | `[0.86, 0, 0.43 m/s]`* |

*注：VEL 模式会归一化方向，因此 `[1, 0, 0.5]` 变为单位方向 `[0.894, 0, 0.447]`，乘以 0.7 × 1.0 = 0.7 m/s

### 结果对比 (Episode 10)

| 方案 | Reward | HeightErr | FormationErr |
|------|--------|-----------|--------------|
| 3D + 偏置0.15 + 下限0.2 | -3263 | 0.769 m | 0.995 m |
| 3D + Z压缩 [-0.2, 0.8] | -222 | 0.643 m | 0.807 m |
| 3D + 无偏置 | -563 | 0.724 m | 1.263 m |
| **4D动作空间 (正确方案)** | **-94** | **0.466 m** | **0.395 m** |

Episode 20 持续改善：Reward **-27.41**，Best **-5.24**（即将转正），HeightErr **0.362 m**

---

## 衍生修复：PowerShell的2>&1陷阱

### 问题

PowerShell 中 `command 2>&1` 会将 stderr 输出包装为**错误记录**，显示为**红色**，并附带 PowerShell 的错误格式：

```
wsl.exe : Gym has been unmaintained...
所在位置 行:1 字符: 1
    + wsl.exe bash -c "python ..."
    + ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: ...
    + FullyQualifiedErrorId : NativeCommandError
```

### 修复

将 `2>&1` **放入 bash 内部**，让 bash 自己合并流：

```powershell
# 错误方式 — PowerShell 接管错误流，输出红色
wsl.exe bash -c "python train.py" 2>&1

# 正确方式 — bash 内部合并流，PowerShell 收到干净 stdout
wsl.exe bash -c "python train.py 2>&1"
```

### 对输出的改善

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 红色输出 | PowerShell 错误记录，全红 | 正常白色文本 |
| 中文乱码 | PowerShell 编码转换错误 | UTF-8 正常显示 |
| Gym警告格式 | 夹杂 CategoryInfo/FullyQualifiedErrorId | 纯文本警告信息 |

---

## 经验总结

1. **理解底层机制后再修复**：VEL 模式的 `direction normalization` 是问题的根源，任何在归一化前添加的偏置都会被稀释
2. **PID 控制器已处理重力**：不需要在动作层面添加抗重力偏置，PID 的积分项自动补偿
3. **幅度和方向必须分离**：VEL 模式将方向（归一化）和幅度（独立缩放）分开，动作空间设计应匹配这种分离
4. **PowerShell 的流重定向陷阱**：`2>&1` 在 PowerShell 和 bash 中的行为不同，跨平台命令需注意处理

## 相关文件

- [formation_control_env.py](../src/environments/formation_control_env.py) — 4D动作空间实现
- [BaseRLAviary.py](../../gym_pybullet_drones/gym_pybullet_drones/envs/BaseRLAviary.py) — VEL模式底层实现
- [agent_lightning_train.py](../src/scripts/agent_lightning_train.py) — 训练脚本（动作reshape动态计算，无需修改）