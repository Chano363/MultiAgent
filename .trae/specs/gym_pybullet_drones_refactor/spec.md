# 多智能体编队控制项目重构 - 产品需求文档

## Overview
- **Summary**: 将现有列车编队控制项目重构为基于 gym-pybullet-drones 的多智能体编队控制项目，使用专业物理仿真器替代原有模拟模型
- **Purpose**: 提供真实物理仿真环境，支持多智能体编队控制研究，包括保持稳定时距、抑制扰动放大、编队协调等核心研究目标
- **Target Users**: 学术研究人员、研究生、强化学习开发者

## Goals
- [x] 替换原有模拟仿真器为 gym-pybullet-drones 专业物理仿真器
- [x] 删除所有列车相关代码和配置
- [x] 重新设计多智能体编队控制环境
- [x] 更新技术文档和配置文件
- [x] 确保与 Agent Lightning 集成

## Non-Goals (Out of Scope)
- 保留列车控制相关代码
- 使用商业仿真软件（如 OpenTrack, RailSim）
- 新增未规划的功能特性

## Background & Context
- 原项目基于模拟列车动力学模型，无法提供真实物理数据
- gym-pybullet-drones 是多伦多大学开发的开源多智能体无人机仿真平台
- 使用 MIT 许可证，适合学术研究使用
- 支持 Gymnasium 标准接口，与现有强化学习框架兼容

## Functional Requirements
- **FR-1**: 集成 gym-pybullet-drones 仿真器作为核心环境
- **FR-2**: 实现多智能体编队控制环境（支持 2+ 智能体）
- **FR-3**: 提供稳定时距保持机制
- **FR-4**: 支持扰动抑制和编队协调
- **FR-5**: 与 Agent Lightning 集成进行模型优化
- **FR-6**: 提供可视化输出和结果分析

## Non-Functional Requirements
- **NFR-1**: 使用 GPU 加速训练
- **NFR-2**: 支持检查点保存和恢复
- **NFR-3**: 代码遵循 PEP8 规范
- **NFR-4**: 使用 Conda 进行包管理

## Constraints
- **Technical**: WSL2 Ubuntu 24.04 LTS, Python 3.10+, PyTorch 2.0+
- **Dependencies**: gym-pybullet-drones, gymnasium, stable-baselines3, agentlightning

## Assumptions
- [x] gym-pybullet-drones 已安装并配置完成
- [x] Conda 环境已就绪
- [x] 用户熟悉强化学习基本概念

## Acceptance Criteria

### AC-1: gym-pybullet-drones 集成完成
- **Given**: 项目已重构
- **When**: 运行训练脚本
- **Then**: 成功加载 gym-pybullet-drones 环境并开始训练
- **Verification**: `programmatic`

### AC-2: 多智能体编队环境正常工作
- **Given**: 环境初始化完成
- **When**: 执行多智能体训练
- **Then**: 所有智能体能够协同工作，保持编队队形
- **Verification**: `programmatic`

### AC-3: 旧代码清理完成
- **Given**: 重构完成
- **When**: 检查项目结构
- **Then**: 无列车控制相关代码残留
- **Verification**: `human-judgment`

### AC-4: 技术文档更新完成
- **Given**: 重构完成
- **When**: 查看文档
- **Then**: 文档准确反映新项目结构和使用方法
- **Verification**: `human-judgment`

## Open Questions
- [ ] 具体使用哪种多智能体算法（MA-PPO, MADDPG等）
- [ ] 是否需要可视化界面