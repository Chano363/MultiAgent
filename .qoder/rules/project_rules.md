---
trigger: always_on
---
# Traffic RL Project 项目规则

本项目使用 gym-pybullet-drones 无人机运动控制仿真器进行多智能体编队控制，目前与列车信号、列车控制无关。

### 3.1. 环境配置要求

## 环境配置要求

### 1. 运行平台要求

**重要**: 本项目必须在 WSL (Windows Subsystem for Linux) 环境中运行。

- 推荐使用 WSL2 以获得更好的性能和兼容性
- 推荐发行版: Ubuntu 24.04 LTS
- 确保 WSL 已正确安装并配置

### 2. 包管理要求

**重要**: 本项目必须使用 Conda 进行包管理和环境配置。

- 不使用系统级 pip 安装（除非要安装到 conda 环境）
- 所有 Python 依赖都应通过 conda 或 conda 环境中的 pip 管理
- 推荐使用 miniconda3 以保持轻量级
3. wsl python conda 都已经安装好，不要重复安装
4. 创建的临时脚本在问题解决之后需要及时删除
5. python的代码规范请遵循PEP8规范
6. 使用gpu而不是cpu进行训练
7. 合理利用检查点，避免重复训练
8. 定期保存模型，防止数据丢失
9. 确保使用真实数据（由专业仿真器生成或者真实运动数据）而不是随机数据或者模拟数据
10. 使用agent lightning进行模型训练和优化
11. 不要创建任何手动模拟的控制环境，只能使用专业仿真器生成的环境
12. 访问网络或下载资源使用Windows powershell