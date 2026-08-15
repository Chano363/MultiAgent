# 长期项目记忆

## 项目核心事实

**两阶段递进式 RL 研究**（根目录 d:\Code\MultiAgent）：
- 阶段一：无人机编队控制（gym-pybullet-drones，已完成，历史成果）
- 阶段二（当前主战场）：**重载列车群组协同控制**

**阶段二论文题目（2026-08-12 确认）**：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法
**研究对象**：一万吨级 1+0 重载列车群组（单机牵引万吨列车，1机+~100节货车，群组由多列组成，每列内部有车钩力）

**阶段二核心创新点**：车钩力 + 多列群组 + 长大下坡 **分层（Hierarchical）MARL**
- 现有长大下坡 RL 工作（Zhang2024 DQN、Liu2021 DDQN、Wang2025 DQN）**均忽略车钩力**
- 本项目在长大下坡循环制动场景下**显式建模车钩力**，并扩展到多列群组协同
- 自动控制 = MARL 训练出的控制器本身（无额外底层控制器）

**【关键架构澄清 2026-08-14，用户纠正，务必遵守】**
- **"0+1" 编组 = 1 台动力机车 + ~100 节拖挂车厢**（不是前后两台动力）
- **"多智能体" 只在列间（多列万吨列车编队）**，每列 = 1 个智能体；列内（1 机车 + 100 拖挂）**不是多智能体**，是单列控制
- **列内控制** = 单列多体动力学最优控制（车钩力作为该列约束/状态/奖励），用单智能体 RL 或规则/最优控制
- **分层框架**：层级一 = 多列编队 MARL（列间协同，每列 obs 含自身车钩力统计）；层级二 = 单列控制（1机车+100拖挂）
- **当前代码 `train_train.py` 的实现是错误的**（`num_drones=101` 把每车厢当智能体），需重构为列间 MARL + 列内单列控制
- 当前卡点"车厢级 101 智能体学不会平稳制动"是**错误实现导致**，非真实定位难点

## 环境与工具

- WSL2 + conda env `traffic_rl`（Python 3.10）；网络下载用 **Windows PowerShell**
- Windows Anaconda: `D:\Anaconda\python.exe`（CodeBuddy 原生调 MCP）
- MAPPO 是唯一收敛算法（阶段一 Best Reward 235.5），阶段二复用；PPO/SAC/DQN 弃用

## 关键技术坑（会反复踩）

1. **制动传播延迟**：按车辆累计长度/波速算，不要用车钩 free_length（会被 dt 吞掉）
2. **mcp 必须 1.9.3**：scholar-search-mcp 需要 `mcp==1.9.3`（2.0 移除 @app.list_tools）
3. **开放获取论文程序化下载被 403**：MDPI/Wiley/IEEE/Hindawi 反爬，需浏览器手动下载
4. **YAML 用十进制**：`0.0003` 非 `3e-4`
5. `.codebuddy/mcp.json` 含 API key，已 gitignore，**切勿提交**

## 关键文档索引

- `docs/PROJECT_PIPELINE.md` — 任务列表（P0.75/P1/P2/P3，已完成✅保留不删）
- `docs/RESEARCH_POSITIONING.md` — 研究定位 + 文献库
- `docs/VALIDATION_BASELINE.md` — 论文→验证基准（P1 前必读）
- `AGENTS.md` — 项目总入口（含所有关键信息）

## 用户偏好

- 任务列表**保持简单、不频繁删除、保留工作痕迹**（已完成✅标记保留，新任务追加）
- 文献作用 = **验证项目正确性**（仿真器/算法对照，非仅引用）
- **任何 git 提交必须经用户确认**
- 临时脚本用后即删
- **【强制】工作留痕**：每次测试/设计任务必须在文档留痕，**含失败的测试**（记录原因/期望vs实际/解决），论文引用必须保留出处（作者+年份+DOI），追加式记录不覆盖旧内容

## 远程仓库（2026-08-13 更新）

- GitHub origin: `https://github.com/Chano363/MultiAgent.git`
- **CNB cnb**: `https://cnb.cool/chano.ccd/multiagent.git`（本仓库已迁移至此）
  - CNB 认证：用户名 `cnb`，密码 = 访问令牌（微信登录无密码）
  - 令牌通过 Windows 凭据管理器存储（credential.helper manager），未明文写入 config
  - 令牌名：`multiagent`（git push 用，仓库读写）；`multiagent-ad`（OpenAPI 用，含 repo-issue:rw，可提 Issue 触发 NPC）

## CNB CodeBuddy NPC（2026-08-13 验证通过）

- NPC 是腾讯云 Cloud Agent，在 CNB 仓库 Issue/PR 评论中 `@CodeBuddy` 触发
- 自定义角色：`.cnb/settings.yml` 定义「列车控制专家」；流水线在 `.cnb.yml` 的 `$` 分支下配 `issue.comment@npc` / `pull_request.comment@npc`
- **API 提 Issue**：POST `https://api.cnb.cool/chano.ccd/multiagent/-/issues`，body JSON 顶层 `title`/`body`/`labels`，body 里 `@CodeBuddy` 触发；用 `multiagent-ad` 令牌（Bearer）
- 已验证：NPC 约 40s 响应，能自主读仓库文档并专业回答
- 注意：Windows PowerShell 直接 `git commit -m "中文"` 会乱码，改用 `git commit -F <utf8文件>` + `i18n.commitEncoding UTF-8`

## 下一步

- P0.75：从论文提取验证数据 → P1：MAPPO 迁移到列车环境
