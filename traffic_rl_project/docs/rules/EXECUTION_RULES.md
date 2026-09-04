---
title: 执行规范（贯穿所有阶段）
date: 2026-09-01
status: active
owner: Owner
supersedes: partial（自 PROJECT_PIPELINE.md 抽出，内容零丢失）
---


## 七、执行规范（贯穿所有阶段）

- 环境：WSL2 + conda 环境 `traffic_rl`，GPU 训练，不重复安装
- 代码：PEP 8；临时脚本用后即删
- 训练：检查点定期保存、断点续训、收敛检测；**只使用专业仿真器环境**
- 配置：YAML 用十进制小数（`0.0003` 而非 `3e-4`）；`.get()` 路径与 YAML 严格匹配
- 日志：脚本入口必须 `logging.basicConfig(level=logging.INFO)`

