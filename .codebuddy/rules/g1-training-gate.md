---
alwaysApply: false
paths:
  - traffic_rl_project/run_training.py
  - traffic_rl_project/configs/experiments/**
  - traffic_rl_project/scripts/cloud/**
---

# G1 训练闸（触碰训练 / 云端文件时强制注入）

任何训练/评估窗口开跑前：

1. 先读 `traffic_rl_project/docs/PROJECT_PIPELINE.md` §0.8.2，**逐条留痕 G1 六问**（判据锚有文献或 owner 依据 / 机制有文献对标物 / 从头训或奖励面完全不变的纯延长 / 快评协议已进启动脚本 / ADR-070 塌缩护栏在位 / 收账 closer 已以 schtasks 注册且心跳 rc=0）。任一"否" = 不得开训。
2. **开机与注册收账 closer 是同一动作序列**：closer 不在位不得开机（`scripts/cloud/closer_aliyun_ecs.py`，参数红线见 `docs/rules/SERVER_OPS.md` 铁律 12）。
3. owner 原话（2026-11-17）："我需要你从机制层面确保不空转！而不是我提醒一次检查一次！"
