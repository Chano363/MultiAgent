# 列车控制强化学习项目 - 产品需求文档

## Overview
- **Summary**: 将现有交通信号控制强化学习项目重构为列车控制强化学习项目，专注于列车自动驾驶控制（加速、减速、停车、巡航），使用专业仿真器生成的数据进行训练。
- **Purpose**: 开发一个基于强化学习的列车自动驾驶控制系统，实现高效、安全、节能的列车运行控制。
- **Target Users**: 铁路运营公司、列车控制系统开发商、学术研究人员

## Goals
- 重构项目架构，移除道路交通相关组件
- 实现列车控制专用环境模块，支持专业仿真器集成
- 定义列车控制专用的状态空间和动作空间
- 实现基于真实/仿真数据的强化学习训练流程
- 支持列车动力学仿真和奖励函数设计

## Non-Goals (Out of Scope)
- 不涉及列车信号控制（信号机、道岔控制）
- 不涉及多列车协同调度
- 不实现完整的物理仿真引擎（使用现有专业工具）
- 不考虑硬件部署（仅软件算法层面）

## Background & Context
- 原有项目基于SUMO交通仿真进行交通信号控制
- 转向列车控制需要完全替换环境模块和数据处理逻辑
- 列车控制涉及牵引/制动模型、能耗优化、准时性等特殊需求
- 需要支持与专业列车仿真器（如OpenTrack、RailSim）的集成

## Functional Requirements
- **FR-1**: 移除道路交通相关代码和数据
- **FR-2**: 实现列车控制环境模块（支持仿真器集成）
- **FR-3**: 定义列车控制状态空间（位置、速度、加速度、能耗等）
- **FR-4**: 定义列车控制动作空间（牵引、制动、巡航等）
- **FR-5**: 实现列车专用奖励函数（准时性、能耗、安全性）
- **FR-6**: 支持从仿真器获取真实训练数据
- **FR-7**: 提供完整的训练和评估流程

## Non-Functional Requirements
- **NFR-1**: 支持GPU加速训练
- **NFR-2**: 训练数据可持久化存储
- **NFR-3**: 支持检查点保存和恢复
- **NFR-4**: 提供训练可视化和评估报告
- **NFR-5**: 代码遵循PEP8规范

## Constraints
- **Technical**: Python 3.10+, PyTorch 2.0+, 需要专业列车仿真器
- **Business**: 基于现有项目架构进行重构
- **Dependencies**: OpenAI Gymnasium, PettingZoo, NumPy, Pandas

## Assumptions
- 专业列车仿真器（如OpenTrack）已安装并可用
- 仿真器提供Python API或可通过脚本控制
- 用户具备基本的列车控制领域知识

## Acceptance Criteria

### AC-1: 项目架构重构完成
- **Given**: 原有交通信号控制项目
- **When**: 执行重构脚本
- **Then**: 所有道路交通相关文件被移除，项目结构符合列车控制需求
- **Verification**: `human-judgment`

### AC-2: 列车控制环境模块正常工作
- **Given**: 列车控制环境已创建
- **When**: 调用环境的reset()和step()方法
- **Then**: 正确返回列车状态和奖励值
- **Verification**: `programmatic`

### AC-3: 训练流程正常执行
- **Given**: 训练脚本已配置
- **When**: 启动训练命令
- **Then**: 训练正常进行，定期保存检查点和日志
- **Verification**: `programmatic`

### AC-4: 评估报告生成
- **Given**: 训练完成的模型
- **When**: 运行评估脚本
- **Then**: 生成包含训练曲线和测试结果的报告
- **Verification**: `human-judgment`

## Open Questions
- [ ] 具体使用哪个列车仿真器（OpenTrack/RailSim/其他）？
- [ ] 是否需要支持多列车控制场景？
- [ ] 奖励函数的具体权重如何设置（准时性vs能耗vs安全性）？