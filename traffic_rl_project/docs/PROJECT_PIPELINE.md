# 项目工作流程 Pipeline

> 本文档统一定义整个研究项目的执行流程、当前进度与下一步计划，是项目的总览入口。
> 阅读顺序：本文档 → README → project_rules → learning_report。

---

## 一、项目总览

**两阶段递进式研究**：同一套 RL 方法论（MARL + CTDE）先后应用于两个物理场景。

```
阶段一（已完成）          阶段二（进行中）
无人机编队 MAPPO 控制  →  重载列车群组协同控制
```

| | 阶段一：无人机编队 | 阶段二：重载列车编队 |
|:--|:--|:--|
| 状态 | 72 维/机（12 运动学 + 60 动作历史） | 位置、速度、车钩力、制动缸压力、坡度 |
| 动作 | 4 维 VEL 速度指令 `[vx,vy,vz,mag]` | 牵引/制动指令（分级或连续） |
| 奖励 | 高度保持 + 编队间距 + 生存 + 边界 | 纵向冲动最小化 + 间距保持 + 能耗优化 |
| 算法 | MAPPO（CTDE） | MAPPO（复用） |
| 仿真器 | gym-pybullet-drones（PyBullet） | NeTrainSim 动力学 → 自封装 Gym 环境 |
| 状态 | ✅ 已完成（Best Reward 235.5） | ⬜ 环境未搭建 |

---

## 二、阶段一：无人机编队控制（已完成）

### 2.1 Pipeline

```
问题建模 MDP
  └─ 状态/动作/奖励函数设计（4 版迭代，L1 > L2）
       └─ 仿真环境搭建（MultiHoverAviary + VEL 模式）
            └─ 算法选型（PPO ✗ → SAC ✗ → MAPPO ✅）
                 └─ 超参数调优（lr / 熵系数 / KL 早停 / batch_size）
                      └─ 训练 500 轮（Agent Lightning 编排 + 收敛检测 + 定期存档）
                           └─ 评估（确定性推理 vs 随机采样）
                                └─ 消融实验（集中 Critic / KL 早停 / lr / 熵）
                                     └─ 成果固化（报告 + 检查点 + 图表）
```

### 2.2 最终性能（阶段一交付标准）

| 指标 | 结果 |
|:--|:--|
| 平均奖励 | 99.39 ± 47.18（确定性推理 115.31 ± 15.27） |
| 最优奖励 | 235.50（ep430） |
| 高度误差 | 0.383 m |
| 编队误差 | 0.497 m（确定性推理 0.347 m） |
| 策略坍缩率 | 0%（KL 早停，无早停时 11.8%） |

### 2.3 关键产物

- **最佳模型**：`outputs/deploy/mappo_best_ep430.pt`
- **检查点**：`outputs/checkpoints/mappo_formation_ep*.pt`
- **训练曲线**：`outputs/results/mappo_formation_results/charts/`
- **配置快照**：`outputs/deploy/train_config_snapshot.yaml`、`env_config_snapshot.yaml`
- **学术报告**：`docs/training_results_standardized.md`

### 2.4 遗留问题（阶段一的已知不足，供迁移时规避）

1. 高度误差 0.383 m（38% 偏差）仍有优化空间
2. 仅静态编队保持，无避障 / 编队重构 / 动态扰动
3. 未做 Sim-to-Real 验证
4. 超参数手动调优，无 HPO 自动化
5. 单环境串行步进，未向量化

---

## 三、通用开发流程（两个阶段共用）

每阶段遵循同一套方法论，后续任何新任务（列车编队）按此流程执行：

```
① 文献调研        → 明确物理模型与算法选型的依据
② MDP 建模        → 定义状态 / 动作 / 奖励函数
③ 环境搭建        → 基于专业仿真器封装 Gym 接口（禁止手动/mock 环境）
④ 基线训练        → 先用成熟算法跑通链路，验证环境与奖励合理性
⑤ 算法适配        → 按任务特性选型（多智能体用 CTDE）
⑥ 奖励与超参迭代  → 一次只改一个变量，记录结果
⑦ 评估与消融      → 确定性推理、组件贡献度分析
⑧ 成果固化        → 报告 + 检查点 + 图表 + 配置快照
```

**每阶段的验收标准**：训练收敛稳定（无策略坍缩）→ 指标达到阈值 → 消融实验说明组件贡献 → 报告可复现。

---

## 四、阶段二：重载列车群组协同控制（进行中）

### 4.1 当前进度

| 子任务 | 状态 |
|:--|:--|
| 列车动力学文献调研 | ✅ 已完成 |
| 仿真器调研选型（NeTrainSim） | ✅ 已完成 |
| 相关工作调研（MAPPO 列车应用） | ✅ 已完成 |
| 列车动力学 Gym 环境搭建 | ✅ 已完成（2026-08，P0） |
| MAPPO 迁移与奖励重设计 | ⬜ 未开始 |
| 对比分析（无人机 vs 列车） | ⬜ 未开始 |

### 4.2 完整计划 Pipeline

```
① 动力学模型提取（NeTrainSim）
   └─ 从论文 + 源码提取纵向动力学公式
        ├─ 牵引力 / 制动力 / 滚动阻力 / 坡度阻力 / 车钩力
        └─ 多体系统（质量-弹簧-阻尼），Python + NumPy 实现
             └─ ② Gym 环境封装
                  ├─ 状态：位置、速度、车钩力、制动缸压力、坡度
                  ├─ 动作：牵引/制动指令（分级或连续）
                  ├─ 奖励：纵向冲动最小化 + 间距保持 + 能耗优化
                  └─ 验证：单步动力学输出 vs 论文基准数据
                       └─ ③ MAPPO 迁移
                            ├─ 复用 CTDE 架构与 KL 早停
                            ├─ 调整状态/动作维度
                            └─ 奖励函数按列车特性重设计
                                 └─ ④ 训练调参
                                      ├─ lr / 熵系数搜索（从 5e-5 / 0.005 起步）
                                      ├─ batch_size ≤ n_steps 约束
                                      └─ 收敛检测 + 定期存档
                                           └─ ⑤ 评估与对比
                                                ├─ 速度同步、间距保持、冲动指标
                                                └─ 与无人机场景差异的系统对比
                                                     └─ ⑥ 报告与成果固化
```

### 4.3 明确的下一步行动清单（按优先级）

**P0 — 已全部完成 ✅（2026-08）**

1. ✅ 建立 `src/environments/train_env.py`，确定状态（速度误差/间距误差/车钩力/位置）与动作（每车 throttle ∈ [-1,1]）接口
2. ✅ 从 NeTrainSim 源码提取公式并实现 `src/train_dynamics/`（Davis 阻力、牵引、Karwatzki 制动、坡度、车钩）
3. ✅ Gym 环境 `reset/step` 数值闭环跑通，26 个测试全部通过（`tests/test_train_dynamics.py` + `tests/test_train_env.py`）

**P1 — 接下来（1-2 周）**

4. 验证环境：模拟 30 秒列车编队轨迹、确认奖励信号分布合理（当前速度同步权重占主导）
5. 将 MAPPO 从无人机迁移到列车（新状态/动作维度），从 `lr=5e-5, entropy=0.005` 起步跑基线
6. 复用 KL 早停、集中 Critic、收敛检测、定期存档等已验证机制

**P2 — 优化与结论（2-3 周）**

7. 奖励权重消融（冲动 / 间距 / 能耗），参考无人机阶段 L1 优于 L2 的经验
8. 多算法对比（若时间允许：SAC 短训对照）与消融实验
9. 系统对比无人机 vs 列车场景差异，撰写阶段二报告

### 4.4 迁移需注意的差异（来自阶段一经验）

| 经验 | 列车场景的对应调整 |
|:--|:--|
| VEL 模式 PID 补偿重力 | 列车无悬停问题，动作直接映射牵引/制动，注意死区与最大牵引率 |
| 编队间距 5 m 目标 | 列车间距约束更硬（安全距离 + 车钩缓冲），奖励权重需重调 |
| 截断条件 x>20 | 列车纵向里程长，需按运行区间设计终止条件 |
| 3 架无人机组队 | 列车 3-6 节车厢，CTDE 的集中 Critic 输入维度随车厢数增长 |

---

## 五、代码与配置索引

### 阶段一代码结构（`src/`）

| 路径 | 职责 |
|:--|:--|
| `main.py` | 入口：train / continue / test 三模式 |
| `environments/formation_control_env.py` | 编队 Gym 环境（包装 MultiHoverAviary VEL 模式） |
| `algorithms/mappo_agent.py` | MAPPO（CTDE + KL 早停，**唯一收敛算法**） |
| `algorithms/optimized_ppo.py` | PPO（不稳定，不推荐） |
| `algorithms/sac_agent.py` | SAC（后期退化） |
| `algorithms/optimized_dqn.py` | DQN（未验证） |
| `trainer/train_loop.py` | 传统训练循环 + 收敛检测 |
| `agent_lightning_integration.py` | Agent Lightning 编排训练（默认路径） |
| `utils/` | 图表、结果存储、指标跟踪 |

### 阶段二代码结构（新增，P0 已完成）

| 路径 | 职责 |
|:--|:--|
| `train_dynamics/` | 列车纵向动力学（NeTrainSim 公式 + 多体车钩） |
| `train_dynamics/resistance.py` | Davis 阻力公式 |
| `train_dynamics/tractive.py` | 牵引力（功率/粘着约束 + throttle 曲线） |
| `train_dynamics/braking.py` | Karwatzki 制动力 |
| `train_dynamics/coupler.py` | 车钩力（质量-弹簧-阻尼） |
| `train_dynamics/train.py` | 多体动力学积分器（每车独立控制） |
| `train_dynamics/params.py` | 机车/货车/车钩参数 |
| `environments/train_env.py` | 列车编队 Gym 环境 |
| `tests/test_train_dynamics.py` | 动力学数值验证（18 测试） |
| `tests/test_train_env.py` | 环境闭环验证（8 测试） |

### 配置文件

| 文件 | 用途 |
|:--|:--|
| `configs/train_config.yaml` | 每算法超参数（`training.hyperparameters.<algo>`） |
| `configs/env_config.yaml` | 环境参数（num_drones / 间距 / 奖励权重） |
| `configs/agent_lightning_config.yaml` | Agent Lightning 调优配置 |

### 输出目录

| 路径 | 内容 |
|:--|:--|
| `outputs/checkpoints/` | 训练检查点（ep*.pt，已 gitignore） |
| `outputs/results/<algo>_formation_results/` | results.json/yaml + charts |
| `outputs/deploy/` | 最佳模型 + 配置快照 + 标注曲线 |

---

## 六、文档索引

| 文档 | 定位 | 何时读 |
|:--|:--|:--|
| **本文档** | 全项目 Pipeline 总览 + 下一步 | 任何任务开始前 |
| `README.md` | 快速上手命令 + 易错点速查 | 首次接触项目 |
| `.trae/rules/project_rules.md` | 工程规范（环境、训练、代码约束） | 写代码前 |
| `docs/learning_report.md` | 阶段一完整技术报告（理论 + 实现 + 调试） | 深入理解阶段一 |
| `docs/training_results_standardized.md` | 阶段一学术成果报告 | 引用指标/写论文 |
| `docs/ppt_plan.md` | 导师汇报 PPT 提纲 | 做汇报时 |
| `../.learnings/LEARNINGS.md` | 踩坑记录（调试经验） | 遇到对应问题时 |

---

## 七、执行规范（贯穿所有阶段）

- 环境：WSL2 + conda 环境 `traffic_rl`，GPU 训练，不重复安装
- 代码：PEP 8；临时脚本用后即删
- 训练：检查点定期保存、断点续训、收敛检测；**只使用专业仿真器环境**
- 配置：YAML 用十进制小数（`0.0003` 而非 `3e-4`）；`.get()` 路径与 YAML 严格匹配
- 日志：脚本入口必须 `logging.basicConfig(level=logging.INFO)`
