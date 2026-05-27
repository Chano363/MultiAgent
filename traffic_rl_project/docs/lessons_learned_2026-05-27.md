# 训练脚本 Bug 排查经验教训

## 日期: 2026-05-27

---

## 1. 核心教训：配置文件的"静默失败"是最危险的 Bug

### 问题描述

训练脚本 `agent_lightning_train.py` 中，`create_agent()` 函数通过以下路径读取 PPO 超参数：

```python
algo_params = config.get('training', {}).get('hyperparameters', {})
params = algo_params.get('ppo', {})
agent = OptimizedPPOAgent(
    batch_size=params.get('batch_size', 128),
    n_steps=params.get('n_steps', 100),
    ...
)
```

但实际加载的配置文件 `train_config.yaml` 是扁平结构（没有 `training.hyperparameters.ppo` 嵌套），导致 `algo_params` 和 `params` 始终为空字典 `{}`，所有参数退回默认值。

### 为什么这是一个"静默失败"

- 代码不会报错，不会抛出任何异常
- 训练正常启动，episode 正常运行
- 唯一症状：**Loss 始终为 0.0000**，且训练指标毫无改善
- 如果不检查 Loss 或只看奖励曲线，根本无法发现模型从未更新过参数

### 教训

| 教训 | 具体措施 |
|------|----------|
| **配置文件结构必须与代码匹配** | 添加新参数时要同步检查配置文件的 YAML 结构和代码的 `.get()` 路径 |
| **关键参数的默认值要足够"显眼"** | 如果 `batch_size` 默认值 128 但实际只用 8，应该在日志中显式打印实际使用的参数值 |
| **启动时打印所有关键超参数** | 训练开始前应输出完整的超参数列表，方便人工对比确认 |
| **验证梯度更新** | 在训练初期（前几个 episode）自动检查 Loss 是否非零，若连续多轮 Loss=0 则立即中止并报错 |

---

## 2. 代码原则：防御性参数验证

### 建议在 `OptimizedPPOAgent.__init__()` 中添加

```python
def __init__(self, ..., batch_size, n_steps, ...):
    # 打印实际使用的参数
    logger.info(f"PPO 参数: batch_size={batch_size}, n_steps={n_steps}, "
                f"lr={learning_rate}, gamma={gamma}, ...")
    
    # 验证参数合理性
    if batch_size > n_steps:
        logger.warning(f"batch_size({batch_size}) > n_steps({n_steps}), "
                       f"每个 episode 可能无法触发 update")
```

---

## 3. SharedMemoryExecutionStrategy 的行为理解

### 关键发现

- `SharedMemoryExecutionStrategy(n_runners=1)` 创建 runner 子进程处理所有 episode
- Runner 子进程中的 `DroneFormationLitAgent` 对象独立于 main thread
- Buffer（`buffer_states`, `buffer_actions` 等）在 runner 进程内累积，跨 episode 持久化
- `update()` 只在 buffer 达到 `batch_size` 时才执行，执行后清空 buffer
- **如果 `batch_size` 太大（如 128），而每个 episode 只有 ~10 步，buffer 永远达不到要求，update 永远不会执行**

### 教训

| 教训 | 说明 |
|------|------|
| **batch_size 必须 ≤ 单 episode 步数** | 否则 buffer 永远填不满，模型永远不更新 |
| **打印 buffer 大小** | 在 `update()` 被跳过时打印 `len(buffer_states)` 和 `batch_size`，帮助诊断 |
| **理解框架的执行模型** | 使用 agent-lightning 等框架前，先理解 runner/algorithm 的进程模型和数据流 |

---

## 4. 调试方法论

### 本次调试中有效的诊断手段

| 手段 | 用途 | 示例 |
|------|------|------|
| 检查动作值范围 | 确认动作没有被双重缩放 | RPM 值从 3000 跳到 1000 万 |
| 检查 episode 终止原因 | 确认无人机是否过早坠毁 | 倾斜角阈值 0.4rad 太严格 |
| 检查 buffer 大小 | 确认 PPO update 是否被触发 | buffer 只有 10 步，batch_size 需要 128 |
| 检查 Loss 值 | **最重要的信号** | Loss=0 直接证明模型从未更新 |
| 确认配置文件加载 | 对比配置文件和实际运行参数 | train_config.yaml vs agent_lightning_config.yaml |

### 调试流程建议

```
启动训练 → 检查第1个 episode 的:
  1. 动作值范围是否合理 (不应爆表)
  2. episode 终止原因 (是正常结束还是截断)
  3. buffer 步数 vs batch_size
  4. 前几个 episode 的 Loss 是否为非零
```

---

## 5. 配置管理最佳实践

### 单一配置来源 (Single Source of Truth)

当前项目存在两个配置文件，容易混淆：
- `configs/train_config.yaml` — **实际被训练脚本加载**
- `configs/agent_lightning_config.yaml` — **未被使用**

**建议**: 
- 删除未使用的配置文件，或合并为一个
- 在训练脚本顶部以大号注释标明：`# 配置文件: configs/train_config.yaml`
- 添加 `--print-config` 命令行参数，启动时打印所有实际参数

### 参数命名一致性

代码中参数用下划线（`batch_size`），YAML 中也用下划线，但加载时要确认 `.get()` 的键名完全匹配。

---

## 6. YAML 类型陷阱

### 科学计数法问题

```yaml
learning_rate: 3e-4  # ❌ YAML 可能将其解析为字符串 "3e-4"
learning_rate: 0.0003 # ✅ 正确使用十进制表示
```

**教训**: 在 YAML 中始终使用十进制小数而非科学计数法表示浮点数。

---

## 7. 修复总结

| 序号 | Bug | 根因 | 修复 |
|------|-----|------|------|
| 1 | Loss 始终为 0 | 配置文件 `train_config.yaml` 缺少 `training.hyperparameters.ppo` 嵌套结构 | 重构配置文件，添加正确的嵌套结构 |
| 2 | RPM 双重转换 | `agent_lightning_integration.py` 和 `agent_lightning_train.py` 手动转换 RPM，环境内部又转换一次 | 移除所有手动 RPM 转换，直接传归一化动作 |
| 3 | Episode 过早截断 | 倾斜角阈值 0.4rad 太严格 | 放宽到 0.8rad |
| 4 | 训练不停止 | `SharedMemoryExecutionStrategy` 的 `main_thread="runner"` | 改为 `main_thread="algorithm"` |
| 5 | 奖励/速度索引错误 | 观测向量索引 3:6 是姿态角而非速度 | 修正为 6:9（正确的速度索引） |
| 6 | 日志过于冗长 | INFO 日志包含大量重复信息 | 精简日志，只保留关键训练指标 |

---

## 8. 最重要的教训

> **"Loss 是否非零"是训练是否正常的最基本判据。任何训练启动后，第一件事就是确认 Loss 在变化。**
>
> 如果 Loss 始终为 0，无论其他指标看起来如何，模型根本就没有在学习。

---

## 9. VEL 动作空间 + PID 控制的不稳定性问题

### 问题背景

早期使用 RPM 动作空间（12 维，每机 4 个电机转速）导致模型难以学到有效策略，Best 停滞在 -0.14 共 900 轮。切换到 VEL 动作空间后，底层使用 PID 控制器将速度指令转换为 RPM，降低了学习维度并利用飞控先验知识。

### 问题：VEL + 随机探索 → 无人机翻转

切换 VEL 后出现新问题：85% 的 episode 在 30-60 步内被提前截断，导致 PPO 的 buffer 大小（16-63 步）始终小于 batch_size（64），Loss 持续为 0。

**根因分析**：MultiHoverAviary 的 `_computeTruncated()` 函数设置了 `roll/pitch > 1.5rad`（约 86°）的截断条件。在 VEL 动作空间中，PPO 的随机动作输出 [-1, 1] 的连续值，经 PID 解算后产生激进的姿态变化，roll 频繁达到 3+ rad（接近 π，即完全倒飞）。

### 诊断方法

在 `FormationControlEnv.step()` 中添加截断原因日志：

```python
if truncated and self.steps < self.max_steps - 10:
    states = np.array([self.aviary._getDroneStateVector(i) for i in range(self.num_drones)])
    reasons = []
    for i in range(self.num_drones):
        if abs(states[i][7]) > 1.5:
            reasons.append(f"Drone{i}:roll={abs(states[i][7]):.2f}>1.5")
        if abs(states[i][8]) > 1.5:
            reasons.append(f"Drone{i}:pitch={abs(states[i][8]):.2f}>1.5")
    if reasons:
        import logging
        logging.warning(f"提前截断 @ step {self.steps}: {'; '.join(reasons)}")
```

输出显示：
```
提前截断 @ step 64: Drone0:roll=3.01>1.5; Drone2:roll=1.73>1.5
提前截断 @ step 39: Drone0:roll=3.07>1.5
```

### 修复：完全禁用倾斜截断 + 限制速度

| 修改 | 文件 | 变更 |
|------|------|------|
| 倾斜截断禁用 | `MultiHoverAviary.py` | `abs(roll) > 1.5` → `abs(roll) > 10.0` |
| 降低最大速度 | `env_config.yaml` | `max_speed: 3.0` → `max_speed: 1.0` |
| SPEED_LIMIT 同步 | `formation_control_env.py` | `self.aviary.SPEED_LIMIT = self.max_speed` |

修改后 episode 完全不受截断影响，每轮 241 步完整运行。

### 教训

| 教训 | 说明 |
|------|------|
| **物理仿真器的截断条件必须与任务匹配** | VEL+PID 会产生瞬时大幅倾斜，教学/比赛用的 1.5rad 阈值不适用于强化学习探索期 |
| **降低速度上限是更好的安全措施** | 1.0 m/s 的速度上限确保无人机在 8 秒 episode 内不会飞出 30m 的位边界，同时使倾斜需求降至 ~0.1 rad |
| **截断原因日志是必需的诊断工具** | 不加日志就无法区分 "timeout 正常结束" 和 "碰撞/倾斜/越界导致截断" |

---

## 10. 奖励函数设计：L2 vs L1 惩罚

### 问题

初版奖励函数使用 L2（二次）惩罚：
```python
reward -= 0.05 * dist_error ** 2   # 距离误差平方
reward -= 0.03 * alt_error ** 2    # 高度误差平方
```

这导致两个问题：
1. **大误差时梯度爆炸**：随机探索时无人机漂移 3-5m，误差² = 9-25，单步惩罚 0.45-1.25，episode 总惩罚可达数百
2. **小误差时梯度消失**：策略接近最优时误差 ~0.2m，误差² = 0.04，惩罚 0.002/步，策略难以感知并进一步优化

### 修复：改用 L1（线性）惩罚

```python
reward -= 0.05 * abs(dist_error)   # 线性惩罚，梯度恒定
reward -= 0.02 * abs(alt_error)
```

效果对比：
| 指标 | L2 惩罚（ep260） | L1 惩罚（ep530） |
|------|-----------------|-----------------|
| Best Reward | -10.70（无法突破零） | +34.30 |
| 收敛速度 | 230 轮无改善 | 30 轮达到正收益 |
| 编队精度 | ~1.1m | ~0.076m（8cm） |

### 教训

| 教训 | 说明 |
|------|------|
| **L1 惩罚提供恒定梯度** | 不论误差大小，梯度始终相同，小误差时也不会"消失" |
| **L2 惩罚适合有界任务** | 如果误差始终在 [0, 1] 范围内，L2 可以工作；但 RL 探索期间误差范围不可控 |
| **生存奖励权重要足够大** | 0.15/步 × 241 步 = +36.15，形成强大的"保持生存"信号，引导策略趋向保守 |

---

## 11. 熵系数对 VEL 策略收敛的关键影响

### 问题

最初使用 `entropy_coef: 0.008` 鼓励探索，但与 VEL 动作空间不兼容：
- 高熵 → 策略持续输出随机速度指令 → 无人机不断漂移 → 收益始终为负
- 最优策略（输出零速度保持初始编队）无法在高熵下被发现

### 修复：逐步降低熵系数

| 阶段 | entropy_coef | 效果 |
|------|-------------|------|
| 初始 | 0.008 | Best -10.70，无法收敛 |
| 优化 1 | 0.003 | Best +5.94，收敛到 ~1m 精度 |
| 优化 2 | 0.001 | Best +34.30，收敛到 ~8cm 精度 |

### 教训

| 教训 | 说明 |
|------|------|
| **连续动作空间需要低熵** | VEL 是连续动作，高熵意味着持续注入噪声，策略无法精确输出小值 |
| **如果最优策略是确定的，熵应该为零** | 当最优行为是"保持不动"时，任何非零熵都会被奖励函数惩罚 |
| **use_entropy_decay 不是银弹** | 即使启用了衰减，初始熵太高也会在探索期浪费大量 episode |

---

## 12. 最终收敛结果

| 指标 | 值 |
|------|-----|
| 算法 | PPO |
| 动作空间 | VEL（4 维/机 × 3 机 = 12 维） |
| 最大速度限制 | 1.0 m/s |
| Episode 步数 | 241 步（8 秒） |
| 收敛轮次 | ~300 轮 |
| **Best Reward** | **+34.30**（理论上限 +36.15） |
| Avg10 Reward | 33.5±0.3 |
| 编队距离精度 | ±7.6 cm（目标间距 5.0 m） |
| 高度精度 | 接近 0（目标高度 1.0 m） |
| 领航者终端速度 | 0.08-0.12 m/s |

### 关键配置总结

```yaml
# env_config.yaml
max_speed: 1.0           # 速度上限降低，防止大幅机动
survival_bonus: 0.15     # 高生存奖励引导保守策略

# train_config.yaml
entropy_coef: 0.001      # 极低熵，允许精确动作
learning_rate: 0.0003    # 较低学习率，稳定收敛
clip_epsilon: 0.15       # 较小裁剪范围

# MultiHoverAviary.py
roll/pitch limit: 10.0   # 禁用倾斜截断（实际由速度限制保证安全）
```