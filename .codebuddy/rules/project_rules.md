---
description: Traffic RL 项目开发规则——两阶段递进式 RL 研究（无人机→重载列车）
alwaysApply: true
enabled: true
updatedAt: 2026-08-12T15:00:00.000Z
provider:
---

# Traffic RL Project 项目规则

本项目为**两阶段递进式 RL 研究**：
- **阶段一**：无人机编队控制（gym-pybullet-drones，已完成，历史成果）
- **阶段二（当前主战场）**：重载列车群组协同控制（NeTrainSim 动力学 + 自封装 Gym 环境）

> 阶段二核心创新点：**车钩力 + 多列群组分层（Hierarchical）MARL**。详见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md`。

---

## 1. 环境配置要求

- **运行平台**: WSL2 (Ubuntu 24.04 LTS)，已安装好**不要重复安装**
- **包管理**: Conda (miniconda3)，`conda activate traffic_rl`
- **Windows 侧 Python**: `D:\Anaconda\python.exe`（用于 CodeBuddy 原生调用 MCP 等）
- **代码规范**: PEP8
- **训练设备**: GPU
- **仿真环境**: 仅使用专业仿真器（阶段二用 NeTrainSim 动力学 + 多体车钩），**禁止手动/mock 环境**
- **网络下载访问**: 使用 **Windows PowerShell**（不是 WSL）
- **依赖**: 阶段一用 gym-pybullet-drones（保留为历史依赖）；阶段二不依赖它

## 2. 训练规范

1. 合理利用检查点，避免重复训练
2. 定期保存模型，防止数据丢失
3. 确保使用真实数据（专业仿真器生成或真实运动数据）
4. 临时脚本在问题解决后及时删除（`tmp_*.py` / `tmp_*.ps1`）

## 3. 基础工程错误预防规则

1. **配置文件**: YAML 结构必须与代码 `.get()` 路径完全匹配，否则参数静默回退默认值而不报错
2. **日志配置**: 训练脚本入口必须 `logging.basicConfig(level=logging.INFO)`，否则 INFO 日志不输出
3. **动作存储**: 环境交互用 reshape 动作，Transition 存储用 flatten 动作（维度需匹配）
4. **YAML 格式**: 禁止科学计数法（`3e-4`），必须用十进制（`0.0003`），否则可能被解析为字符串
5. **参数验证**: 启动时打印所有关键超参数，验证合理性（如 `batch_size > n_steps` 时警告）

## 4. 列车仿真规则

1. **制动传播延迟**: 空气制动波速传播的延迟按**车辆累计长度/波速**计算（真实重载数百米→数秒延迟），**不要用车钩 free_length**（会被 dt 吞掉）
2. **制动分类**: 电制动（连续，仅机车）+ 空气制动（离散档位 EB/SB + 波速传播），动作 `>0` 牵引（仅机车）、`<0` 制动
3. **安全层**: `SafetyLayer`（规则式 ATP：限速/车钩力 ≤1000kN/间距）在动作喂给动力学前修正，默认启用
4. **车钩力指标**: 车钩力 1000kN 是**双用途**（安全约束 + 最终评估指标），记录峰值/超限次数进 `info`

## 5. 文献与验证规范

1. **论文双重用途**: 既是文献引用，更是**项目正确性验证基准**（`docs/VALIDATION_BASELINE.md`）
2. **P1 前置**: 从论文提取验证数据（制动减压-压钩力、车钩间隙-车钩力等）→ 建立回归测试期望值
3. **文献库**: `docs/papers/` 存放已下载 PDF + arXiv 源码，命名规范 `作者+年份+主题`
4. **MCP 检索**: 用 scholar-search-mcp（Semantic Scholar + arXiv），`.codebuddy/mcp.json` 含 API key 已被 gitignore

## 6. Git 与任务管理

1. **任务列表**: 维护在 `docs/PROJECT_PIPELINE.md` 的 P0/P1/P2/P3 清单。已完成的用 ✅ 标记**保留不删除**，新任务追加，保留全部工作痕迹
2. **git 提交**: **任何 git 提交操作必须经过用户确认**
3. **`.codebuddy/mcp.json`**: 含 API key，已被 `.gitignore` 忽略，**切勿提交**

## 7. 文档风格

- 保持文档风格统一（表格、层级、图标一致）
- 关键文档：`PROJECT_PIPELINE.md`（总览/任务）、`RESEARCH_POSITIONING.md`（定位/文献）、`VALIDATION_BASELINE.md`（验证基准）、`learning_report.md`（阶段一报告）
- 文档更新后同步 AGENTS.md（项目总入口）

## 8. 工作留痕（强制规范）

1. **测试/设计任务必须留痕**：每次测试或设计工作后，必须在文档中追加记录（写入 `VALIDATION_BASELINE.md` 或对应设计文档），包括：
   - **成功的测试**：验证了什么、关键数据/结果
   - **失败的测试**：**失败原因、期望 vs 实际、如何解决**（失败是重要工作痕迹，绝不删除或忽略）
2. **论文引用必须保留出处**：任何从论文借鉴的思想、公式、设计、数据，必须在文档中标注**来源论文**（作者+年份+DOI/文件），禁止"用了不注明"
3. **留痕格式**：新增内容采用**追加式**（`### 小节-日期`），保留历史，不覆盖旧记录
4. **临时脚本**：用后即删，但其结论/验证结果必须已写入文档后才删除