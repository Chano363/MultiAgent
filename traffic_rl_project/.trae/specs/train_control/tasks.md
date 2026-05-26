# 列车控制强化学习项目 - 实现计划

## [ ] Task 1: 移除道路交通相关文件
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 删除RESCO道路交通数据集
  - 删除交通信号控制环境代码
  - 删除sumo-rl相关代码和配置
- **Acceptance Criteria Addressed**: [AC-1]
- **Test Requirements**:
  - `human-judgment` TR-1.1: 确认data/RESCO目录已删除
  - `human-judgment` TR-1.2: 确认src/environments/traffic_env.py已删除
  - `human-judgment` TR-1.3: 确认sumo-rl目录已删除
- **Notes**: 保留通用算法代码（PPO/DQN）和工具函数

## [ ] Task 2: 创建列车控制环境模块
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 创建src/environments/train_env.py
  - 实现列车动力学模型（牵引/制动）
  - 支持与外部仿真器集成的接口
  - 实现reset()和step()方法
- **Acceptance Criteria Addressed**: [AC-2]
- **Test Requirements**:
  - `programmatic` TR-2.1: 环境reset()方法返回有效状态
  - `programmatic` TR-2.2: 环境step()方法正确更新状态和奖励
  - `programmatic` TR-2.3: 状态空间维度正确（至少包含位置、速度、加速度）
- **Notes**: 提供仿真模式和真实数据模式两种运行模式

## [ ] Task 3: 定义列车控制状态空间和动作空间
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 
  - 定义状态空间：位置、速度、加速度、能耗、目标位置等
  - 定义动作空间：牵引级别、制动级别、巡航模式等
  - 实现状态归一化处理
- **Acceptance Criteria Addressed**: [AC-2]
- **Test Requirements**:
  - `programmatic` TR-3.1: 状态空间维度符合预期
  - `programmatic` TR-3.2: 动作空间维度符合预期
  - `programmatic` TR-3.3: 状态归一化在[0,1]范围内
- **Notes**: 使用gymnasium的Space类定义

## [ ] Task 4: 实现列车专用奖励函数
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 
  - 实现准时性奖励（到达时间与计划时间的偏差）
  - 实现能耗奖励（基于牵引/制动能量消耗）
  - 实现安全性奖励（防止超速、碰撞）
  - 组合奖励函数（可配置权重）
- **Acceptance Criteria Addressed**: [AC-2]
- **Test Requirements**:
  - `programmatic` TR-4.1: 准时性奖励在正点时最大
  - `programmatic` TR-4.2: 能耗奖励在节能操作时更高
  - `programmatic` TR-4.3: 安全违规时奖励为负
- **Notes**: 奖励权重可通过配置文件调整

## [ ] Task 5: 更新配置文件
- **Priority**: P0
- **Depends On**: Task 2, Task 3, Task 4
- **Description**: 
  - 更新configs/env_config.yaml（列车环境配置）
  - 更新configs/train_config.yaml（训练超参数）
  - 更新configs/reward_config.yaml（奖励权重配置）
- **Acceptance Criteria Addressed**: [AC-3]
- **Test Requirements**:
  - `human-judgment` TR-5.1: 配置文件格式正确
  - `programmatic` TR-5.2: 配置文件能正确加载
  - `programmatic` TR-5.3: 配置参数能正确应用到训练
- **Notes**: 使用YAML格式，保持向后兼容

## [ ] Task 6: 修改训练脚本
- **Priority**: P0
- **Depends On**: Task 2, Task 5
- **Description**: 
  - 修改src/scripts/train.py支持列车控制
  - 修改src/scripts/agent_lightning_train.py支持列车环境
  - 实现数据收集和保存逻辑
- **Acceptance Criteria Addressed**: [AC-3]
- **Test Requirements**:
  - `programmatic` TR-6.1: 训练脚本能正常启动
  - `programmatic` TR-6.2: 检查点能正确保存
  - `programmatic` TR-6.3: 训练日志能正常记录
- **Notes**: 保留原有的PPO训练框架

## [ ] Task 7: 实现数据采集模块（仿真器集成）
- **Priority**: P1
- **Depends On**: Task 2
- **Description**: 
  - 实现与OpenTrack的接口
  - 实现数据采集脚本
  - 支持批量生成训练数据
- **Acceptance Criteria Addressed**: [AC-2, AC-3]
- **Test Requirements**:
  - `programmatic` TR-7.1: 能从仿真器获取状态数据
  - `programmatic` TR-7.2: 数据格式与环境期望一致
  - `human-judgment` TR-7.3: 数据采集效率合理
- **Notes**: 如果仿真器不可用，提供内置动力学模型作为备用

## [ ] Task 8: 更新评估脚本和可视化
- **Priority**: P1
- **Depends On**: Task 6
- **Description**: 
  - 修改src/scripts/evaluate.py支持列车评估
  - 修改可视化脚本支持列车数据展示
  - 生成训练报告模板
- **Acceptance Criteria Addressed**: [AC-4]
- **Test Requirements**:
  - `programmatic` TR-8.1: 评估脚本能正常运行
  - `human-judgment` TR-8.2: 训练曲线图表清晰可读
  - `human-judgment` TR-8.3: 评估报告内容完整
- **Notes**: 添加列车专用指标（能耗、准时性等）

## [ ] Task 9: 更新技术文档
- **Priority**: P2
- **Depends On**: All
- **Description**: 
  - 更新docs/technical_report.md
  - 添加列车控制相关文档
  - 更新README.md
- **Acceptance Criteria Addressed**: [AC-4]
- **Test Requirements**:
  - `human-judgment` TR-9.1: 文档内容准确反映新架构
  - `human-judgment` TR-9.2: 文档格式规范
- **Notes**: 保持文档与代码同步更新

## [ ] Task 10: 代码清理和优化
- **Priority**: P2
- **Depends On**: All
- **Description**: 
  - 删除未使用的代码和导入
  - 优化代码结构
  - 确保符合PEP8规范
- **Acceptance Criteria Addressed**: [NFR-5]
- **Test Requirements**:
  - `human-judgment` TR-10.1: 代码无冗余
  - `programmatic` TR-10.2: flake8检查通过
- **Notes**: 使用flake8进行代码检查