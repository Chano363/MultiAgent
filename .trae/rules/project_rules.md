# Traffic RL Project 项目规则

本项目使用 gym-pybullet-drones 无人机运动控制仿真器进行多智能体编队控制。

## 1. 环境配置要求

- **运行平台**: WSL2 (Ubuntu 24.04 LTS)，已安装好不要重复安装
- **包管理**: Conda (miniconda3)，所有依赖通过conda环境管理
- **代码规范**: PEP8
- **训练设备**: GPU
- **仿真环境**: 仅使用专业仿真器（gym-pybullet-drones），禁止手动模拟环境
- **训练框架**: Agent Lightning
- **网络访问**: 使用Windows PowerShell

## 2. 训练规范

1. 合理利用检查点，避免重复训练
2. 定期保存模型，防止数据丢失
3. 确保使用真实数据（专业仿真器生成或真实运动数据）
4. 创建的临时脚本在问题解决后及时删除

## 3. 基础工程错误预防规则

1. **Agent Lightning**: `SharedMemoryExecutionStrategy` 必须用 `main_thread="algorithm"`，否则训练完成后脚本永不退出
2. **配置文件**: YAML结构必须与代码`.get()`路径完全匹配，否则参数退回默认值而不报错
3. **日志配置**: 训练脚本必须配置 `logging.basicConfig(level=logging.INFO)`，否则INFO日志不输出
4. **动作存储**: 环境交互用reshape动作，Transition存储用flatten动作
5. **YAML格式**: 禁止用科学计数法（`3e-4`），必须用十进制（`0.0003`），否则可能被解析为字符串
6. **参数验证**: 启动时打印所有关键超参数，验证合理性（如 `batch_size > n_steps` 时警告）